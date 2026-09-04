"""生成された Asset Binary を Browser から取得可能なURLへ公開する。

**Asset Binary Storage方式は【未決定】**（AGENTS.md §3.3 / skills/backend）。
決まるまでの暫定として Local Directory へ書き出し、静的配信するだけの実装を置く。
決まったら `AssetStore` の別実装を足して差し替える。**API境界（Asset Manifestの形）は変えない。**

`GcsAssetStore` はGCS化する場合の実装。Bucket名・公開/署名付きURL方式・保持期間は
チーム確認してから`ASSET_BACKEND=gcs`を有効にする（AGENTS.md: 単独でFIXしない範囲）。

Product APIの `/api/v1` 配下へAsset用Endpointを生やさない。
`GET /api/v1/assets/{assetId}` は【検討中】であり、先回りで作らない（AGENTS.md §4）。
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from ai.types import AssetBlob
from app.models.asset_manifest import AssetManifest, AssetManifestEntry

_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


class AssetStore(Protocol):
    def publish(
        self,
        artwork_id: str,
        assets: Sequence[AssetBlob],
        request_base_url: str,
    ) -> AssetManifest: ...


class LocalDirAssetStore:
    """Local Directoryへ書き出し、静的配信でURLを返す。開発用の暫定実装。

    Cloud Runの複数Instance / 揮発Diskを前提にしていないので、
    Storage方式が決まるまでの繋ぎとして扱う。
    """

    def __init__(
        self,
        root: Path,
        mount_path: str,
        public_base_url: str | None = None,
    ) -> None:
        self._root = root
        self._mount_path = "/" + mount_path.strip("/")
        self._public_base_url = public_base_url.rstrip("/") if public_base_url else None

    def publish(
        self,
        artwork_id: str,
        assets: Sequence[AssetBlob],
        request_base_url: str,
    ) -> AssetManifest:
        target_dir = self._root / artwork_id
        if target_dir.exists():
            shutil.rmtree(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        base = self._public_base_url or f"{request_base_url.rstrip('/')}{self._mount_path}"

        entries: list[AssetManifestEntry] = []
        for asset in assets:
            ext = _EXT_BY_MIME.get(asset.mime_type)
            if ext is None:
                raise ValueError(f"未対応のmimeType: {asset.mime_type}")
            filename = f"{asset.asset_id}.{ext}"
            (target_dir / filename).write_bytes(asset.data)
            entries.append(
                AssetManifestEntry(
                    asset_id=asset.asset_id,
                    url=f"{base}/{artwork_id}/{filename}",
                    mime_type=asset.mime_type,
                    width_px=asset.width_px,
                    height_px=asset.height_px,
                )
            )

        return AssetManifest(assets=entries)


class GcsAssetStore:
    """Google Cloud Storageへ書き出す。複数Instance / Scale to Zeroでも正本が消えない。

    `public=True` はBucket自体が公開設定である前提（objectのURLがそのまま到達可能）。
    `public=False` は署名付きURL（`signed_url_ttl_seconds`で有効期限を切る）。
    """

    def __init__(
        self,
        *,
        bucket: str,
        prefix: str,
        public: bool,
        signed_url_ttl_seconds: int,
    ) -> None:
        self._bucket_name = bucket
        self._prefix = prefix.strip("/")
        self._public = public
        self._signed_url_ttl_seconds = signed_url_ttl_seconds

    def _client(self) -> Any:
        from google.cloud import storage  # noqa: PLC0415

        return storage.Client()

    def publish(
        self,
        artwork_id: str,
        assets: Sequence[AssetBlob],
        request_base_url: str,
    ) -> AssetManifest:
        del request_base_url  # GCS実装ではURLの起点はBucket。Requestに依存しない。
        bucket = self._client().bucket(self._bucket_name)

        entries: list[AssetManifestEntry] = []
        for asset in assets:
            ext = _EXT_BY_MIME.get(asset.mime_type)
            if ext is None:
                raise ValueError(f"未対応のmimeType: {asset.mime_type}")
            blob_path = f"{self._prefix}/{artwork_id}/{asset.asset_id}.{ext}"
            blob = bucket.blob(blob_path)
            blob.upload_from_string(asset.data, content_type=asset.mime_type)

            if self._public:
                url = blob.public_url
            else:
                url = blob.generate_signed_url(
                    version="v4",
                    expiration=self._signed_url_ttl_seconds,
                    method="GET",
                )

            entries.append(
                AssetManifestEntry(
                    asset_id=asset.asset_id,
                    url=url,
                    mime_type=asset.mime_type,
                    width_px=asset.width_px,
                    height_px=asset.height_px,
                )
            )

        return AssetManifest(assets=entries)


def build_asset_store(settings: Any) -> AssetStore:
    if settings.asset_backend == "local":
        return LocalDirAssetStore(
            root=settings.asset_dir,
            mount_path=settings.asset_mount_path,
            public_base_url=settings.asset_public_base_url,
        )
    if settings.asset_backend == "gcs":
        if not settings.gcs_bucket:
            raise ValueError("ASSET_BACKEND=gcsにはGCS_BUCKETが要る")
        return GcsAssetStore(
            bucket=settings.gcs_bucket,
            prefix=settings.gcs_asset_prefix,
            public=settings.gcs_asset_public,
            signed_url_ttl_seconds=settings.gcs_signed_url_ttl_seconds,
        )
    raise ValueError(f"未対応のASSET_BACKENDです: {settings.asset_backend}")
