"""生成された Asset Binary を Browser から取得可能なURLへ公開する。

**Asset Binary Storage方式は【未決定】**（AGENTS.md §3.3 / skills/backend）。
決まるまでの暫定として Local Directory へ書き出し、静的配信するだけの実装を置く。
決まったら `AssetStore` の別実装を足して差し替える。**API境界（Asset Manifestの形）は変えない。**

Product APIの `/api/v1` 配下へAsset用Endpointを生やさない。
`GET /api/v1/assets/{assetId}` は【検討中】であり、先回りで作らない（AGENTS.md §4）。
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol

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
