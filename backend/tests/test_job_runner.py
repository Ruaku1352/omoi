"""JobRunner / InlineTaskQueueのRetry判定テスト。

非同期化方針Doc §6:
「Retry対象: 429/503/504/timeout等」「Retryしない: 認証・権限エラー / 実装バグ等」
がJob単位の実際のRetry回数を左右するため、Endpoint Levelの契約テストとは別に
ユニットレベルで確認する。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ai.errors import AiNotConfiguredError, AiTimeoutError
from ai.types import GenerationResult, InputPhoto
from app.errors import ApiError
from app.services.asset_store import LocalDirAssetStore
from app.services.job_runner import JobRunner
from app.services.job_store import InMemoryJobStore
from app.services.task_queue import InlineTaskQueue


class _RaisingGenerator:
    def __init__(self, exc: Exception) -> None:
        self._exc = exc

    async def generate(self, photos, memory_text) -> GenerationResult:  # noqa: ANN001
        del photos, memory_text
        raise self._exc


@pytest.fixture
def photos() -> list[InputPhoto]:
    return [InputPhoto(filename="p.jpg", mime_type="image/jpeg", data=b"x")]


async def _run_with(tmp_path: Path, exc: Exception, photos: list[InputPhoto], *, allow_retry: bool):
    job_store = InMemoryJobStore()
    asset_store = LocalDirAssetStore(root=tmp_path, mount_path="/dev/assets")
    runner = JobRunner(
        generator=_RaisingGenerator(exc), asset_store=asset_store, job_store=job_store
    )
    await job_store.create("job-1", memory_text=None)
    await runner.run("job-1", photos, None, base_url="http://testserver", allow_retry=allow_retry)
    return await job_store.get("job-1")


@pytest.mark.anyio
async def test_not_configured_error_is_not_retryable(tmp_path: Path, photos) -> None:
    """AiNotConfiguredError(AiErrorのSubclass)は設定ミスなのでRetryしても改善しない。

    以前は汎用except AiErrorに落ちてAI_FAILED(retryable=True)になっていた
    (=非同期Workerが最大試行回数まで無駄にRetryしてしまうBug)。
    """

    job = await _run_with(
        tmp_path, AiNotConfiguredError("GEMINI_API_KEY未設定"), photos, allow_retry=True
    )

    assert job.status == "failed"
    assert job.error["code"] == "AI_FAILED"
    assert job.error["retryable"] is False


@pytest.mark.anyio
async def test_inline_task_queue_finalizes_retryable_failure_instead_of_raising(
    tmp_path: Path, photos
) -> None:
    """InlineTaskQueue(ローカル/テスト用)にはCloud Tasksの再配送が無いので、
    Retryable失敗でも例外を伝播させず即failedへ確定する。

    以前はJobRunner.run()がRetryable失敗をそのまま再送出しており、
    InlineTaskQueue経由でPOST /api/v1/artworks/generateまで伝播して
    202ではなく500になってしまっていた(=Bug)。
    """

    job_store = InMemoryJobStore()
    asset_store = LocalDirAssetStore(root=tmp_path, mount_path="/dev/assets")
    runner = JobRunner(
        generator=_RaisingGenerator(AiTimeoutError("timeout")),
        asset_store=asset_store,
        job_store=job_store,
    )
    queue = InlineTaskQueue(runner)
    await job_store.create("job-2", memory_text=None)

    # 例外を投げずに完了すること自体がテスト対象(投げたら即fail)。
    await queue.enqueue("job-2", photos, None, base_url="http://testserver")

    job = await job_store.get("job-2")
    assert job.status == "failed"
    assert job.error["code"] == "AI_TIMEOUT"
    assert job.error["retryable"] is True  # 種類としては元来Retryable。今回はもう試行しないだけ。


@pytest.mark.anyio
async def test_cloud_tasks_style_retryable_failure_still_propagates(tmp_path: Path, photos) -> None:
    """`allow_retry=True`(Cloud Tasks Worker Endpointの既定)ではRetryable失敗を
    そのまま伝播させる。Retryするかどうかの最終判断はWorker Endpoint側
    (X-CloudTasks-TaskRetryCount)に委ねる。
    """

    job_store = InMemoryJobStore()
    asset_store = LocalDirAssetStore(root=tmp_path, mount_path="/dev/assets")
    runner = JobRunner(
        generator=_RaisingGenerator(AiTimeoutError("timeout")),
        asset_store=asset_store,
        job_store=job_store,
    )
    await job_store.create("job-3", memory_text=None)

    with pytest.raises(ApiError) as excinfo:
        await runner.run("job-3", photos, None, base_url="http://testserver")

    assert excinfo.value.retryable is True
    job = await job_store.get("job-3")
    assert job.status == "processing"  # まだfailedへ確定していない
