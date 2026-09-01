"""非同期Workerの実処理（stage/status更新 + AI生成 + Asset公開）。

`app/api/internal/jobs.py`（Cloud Tasks Worker Endpoint）と
`app/services/task_queue.py`の`InlineTaskQueue`の両方から呼ばれる。

Retry判定はここでは行わない。`ApiError.retryable`をそのまま呼び出し側へ伝える
（非retryableはここでfailedへ確定し、retryableは例外を伝播させて呼び出し側に
Retryするかどうかを委ねる。Cloud Tasks経路は`X-CloudTasks-TaskRetryCount`を見て
最大試行回数を判断する。InlineTaskQueue経路はRetryしない — ローカル/テストで
Cloud Tasksの再配送を再現する必要はない）。
"""

from __future__ import annotations

from collections.abc import Sequence

from ai.types import ArtworkGenerator, InputPhoto
from app.errors import ApiError
from app.services.asset_store import AssetStore
from app.services.generation import generate_and_publish
from app.services.job_store import JobStore


class JobRunner:
    def __init__(
        self,
        *,
        generator: ArtworkGenerator,
        asset_store: AssetStore,
        job_store: JobStore,
    ) -> None:
        self._generator = generator
        self._asset_store = asset_store
        self._job_store = job_store

    async def run(
        self,
        job_id: str,
        photos: Sequence[InputPhoto],
        memory_text: str | None,
        *,
        base_url: str,
    ) -> None:
        await self._job_store.set_stage(job_id, "analyzing")

        async def _on_stage(stage: str) -> None:
            await self._job_store.set_stage(job_id, stage)  # type: ignore[arg-type]

        try:
            response = await generate_and_publish(
                photos,
                memory_text,
                generator=self._generator,
                asset_store=self._asset_store,
                base_url=base_url,
                on_stage=_on_stage,
            )
        except ApiError as exc:
            if not exc.retryable:
                await self._job_store.mark_failed(
                    job_id,
                    code=str(exc.code),
                    message=exc.message,
                    retryable=False,
                    details=exc.details,
                )
                return
            raise

        await self._job_store.mark_completed(
            job_id, response.model_dump(by_alias=True, exclude_none=True)
        )
