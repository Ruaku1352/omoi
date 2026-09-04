"""Job実行までの間、入力写真を一時保持するStore。

Cloud TasksのHTTP Target Payloadは小さく（1MiB程度）、写真Binaryを
直接乗せられない。そのため`CloudTasksQueue`はEnqueue前に写真をここへ保存し、
Task Payloadには`jobId`だけを乗せる。Worker Endpointは`jobId`からここへ
写真を読みに行く。

`InlineTaskQueue`（ローカル/テスト用）は同一Process内でPhotosをそのまま
Python Objectとして渡すため、このStoreを使わない。

保持期間の初期案（非同期化方針Doc §1）: 入力元写真は24時間。
実際のTTLはInfra側（GCS Object Lifecycle）に任せる。ここでは成功後に
明示的に`delete()`するだけで、TTLそのものは実装しない。
"""

from __future__ import annotations

import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from ai.types import InputPhoto


class JobInputStore(Protocol):
    async def save(self, job_id: str, photos: Sequence[InputPhoto]) -> None: ...

    async def load(self, job_id: str) -> list[InputPhoto]: ...

    async def delete(self, job_id: str) -> None: ...


class LocalDirJobInputStore:
    """ローカル/テスト用。Local Directoryへ書き出すだけ。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    async def save(self, job_id: str, photos: Sequence[InputPhoto]) -> None:
        target = self._root / job_id
        target.mkdir(parents=True, exist_ok=True)
        for i, photo in enumerate(photos):
            (target / f"{i}-{photo.filename or 'photo'}").write_bytes(photo.data)
            (target / f"{i}.meta").write_text(photo.mime_type, encoding="utf-8")

    async def load(self, job_id: str) -> list[InputPhoto]:
        target = self._root / job_id
        if not target.is_dir():
            return []
        photos: list[InputPhoto] = []
        for meta_path in sorted(target.glob("*.meta"), key=lambda p: int(p.stem)):
            index = meta_path.stem
            data_path = next(target.glob(f"{index}-*"))
            photos.append(
                InputPhoto(
                    filename=data_path.name.split("-", 1)[1],
                    mime_type=meta_path.read_text(encoding="utf-8"),
                    data=data_path.read_bytes(),
                )
            )
        return photos

    async def delete(self, job_id: str) -> None:
        target = self._root / job_id
        if target.is_dir():
            shutil.rmtree(target)


class GcsJobInputStore:
    """本番用。写真BinaryをGCSへ一時保存する。"""

    def __init__(self, *, bucket: str, prefix: str) -> None:
        self._bucket_name = bucket
        self._prefix = prefix.strip("/")

    def _client(self) -> Any:
        from google.cloud import storage  # noqa: PLC0415

        return storage.Client()

    def _blob_path(self, job_id: str, index: int) -> str:
        return f"{self._prefix}/{job_id}/{index}"

    async def save(self, job_id: str, photos: Sequence[InputPhoto]) -> None:
        import asyncio  # noqa: PLC0415

        def _upload() -> None:
            bucket = self._client().bucket(self._bucket_name)
            for i, photo in enumerate(photos):
                blob = bucket.blob(self._blob_path(job_id, i))
                blob.metadata = {"filename": photo.filename, "mimeType": photo.mime_type}
                blob.upload_from_string(photo.data, content_type=photo.mime_type)

        await asyncio.to_thread(_upload)

    async def load(self, job_id: str) -> list[InputPhoto]:
        import asyncio  # noqa: PLC0415

        def _download() -> list[InputPhoto]:
            bucket = self._client().bucket(self._bucket_name)
            blobs = sorted(
                bucket.list_blobs(prefix=f"{self._prefix}/{job_id}/"),
                key=lambda b: int(b.name.rsplit("/", 1)[-1]),
            )
            photos = []
            for blob in blobs:
                blob.reload()
                meta = blob.metadata or {}
                photos.append(
                    InputPhoto(
                        filename=meta.get("filename", ""),
                        mime_type=meta.get("mimeType", "application/octet-stream"),
                        data=blob.download_as_bytes(),
                    )
                )
            return photos

        return await asyncio.to_thread(_download)

    async def delete(self, job_id: str) -> None:
        import asyncio  # noqa: PLC0415

        def _delete() -> None:
            bucket = self._client().bucket(self._bucket_name)
            for blob in bucket.list_blobs(prefix=f"{self._prefix}/{job_id}/"):
                blob.delete()

        await asyncio.to_thread(_delete)


def build_job_input_store(settings: Any) -> JobInputStore:
    if settings.job_input_backend == "local":
        return LocalDirJobInputStore(settings.job_input_dir)
    if settings.job_input_backend == "gcs":
        if not settings.gcs_bucket:
            raise ValueError("JOB_INPUT_BACKEND=gcsにはGCS_BUCKETが要る")
        return GcsJobInputStore(bucket=settings.gcs_bucket, prefix=settings.gcs_job_input_prefix)
    raise ValueError(f"未対応のJOB_INPUT_BACKENDです: {settings.job_input_backend}")
