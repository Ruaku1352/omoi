"""JobStageObserverの検証。

`ai/`側は一切変更せず、既存のGenerationObserver(`semantic_plan`コールバック)経由で
`analyzing`→`extracting`のstage遷移を拾えることを確認する。
"""

from __future__ import annotations

import asyncio

import pytest

from app.services.job_store import InMemoryJobStore
from app.services.stage_observer import JobStageObserver, current_job_id


@pytest.mark.anyio
async def test_semantic_plan_callback_advances_stage_to_extracting() -> None:
    job_store = InMemoryJobStore()
    await job_store.create("job-1", memory_text=None)
    await job_store.set_stage("job-1", "analyzing")

    observer = JobStageObserver(job_store)
    token = current_job_id.set("job-1")
    try:
        observer.semantic_plan(plan=None, images=[])
        # Callbackは同期(create_taskでFire-and-forget)なので、
        # 次のTick(sleep(0))でTaskが実行される猶予を与える。
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    finally:
        current_job_id.reset(token)

    job = await job_store.get("job-1")
    assert job.stage == "extracting"


@pytest.mark.anyio
async def test_concurrent_jobs_do_not_cross_contaminate_stage() -> None:
    """asyncio Task LocalなContextVarなので、同時に走る複数Jobでも取り違えない
    （Cloud Run concurrency>1で複数Jobが並行実行される想定）。
    """

    job_store = InMemoryJobStore()
    await job_store.create("job-a", memory_text=None)
    await job_store.create("job-b", memory_text=None)
    observer = JobStageObserver(job_store)

    async def _run(job_id: str, should_fire: bool) -> None:
        token = current_job_id.set(job_id)
        try:
            if should_fire:
                observer.semantic_plan(plan=None, images=[])
            await asyncio.sleep(0)
            await asyncio.sleep(0)
        finally:
            current_job_id.reset(token)

    await asyncio.gather(_run("job-a", should_fire=True), _run("job-b", should_fire=False))

    job_a = await job_store.get("job-a")
    job_b = await job_store.get("job-b")
    assert job_a.stage == "extracting"
    assert job_b.stage is None  # semantic_planを呼んでいないので未着手のまま


@pytest.mark.anyio
async def test_no_current_job_id_is_a_safe_noop() -> None:
    """内部Debug経路(`/internal/artworks/generate-sync`)はJobRunnerを経由しないため
    current_job_idがNoneのまま。observerが呼ばれても何もしない（Crashしない）。
    """

    job_store = InMemoryJobStore()
    observer = JobStageObserver(job_store)

    observer.semantic_plan(plan=None, images=[])
    await asyncio.sleep(0)
    # 例外が飛ばないことがテスト対象。
