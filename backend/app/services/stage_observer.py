"""AI GeneratorのGenerationObserverを使い、`analyzing`→`extracting`のstage遷移を拾う。

`ai/gemini.py`の`GenerationObserver`（"PoC用の任意observer"）は元々Semantic Planningと
Segmentationの節目を通知する仕組みとして既に存在する。`ai/`側は一切変更せず、
Backend側でこのObserverを実装して`build_generator(settings, observer=...)`へ渡すだけで
`extracting`遷移が拾える。

Job単位のstage更新にはJob IDが要るが、Generator Instanceはapp起動時に1つだけ構築され
全Jobで共有される。Requestごとに専用のGeneratorを作り直すコストを避けるため、
`contextvars.ContextVar`で「今実行中のJob ID」をTask Local（asyncioのTask単位で
独立）に保持する。JobRunner.run()の実行中だけTask上でセットされるので、
Cloud Run concurrency>1で複数Jobが同時実行されても取り違えない。

Callback自体は同期（`ai/gemini.py`が`await`せず直接呼ぶ）なので、
Firestore書き込みは`asyncio.create_task`でFire-and-forgetする
（進捗表示の更新が多少遅れても実害が無いため、生成処理自体をブロックしない）。
"""

from __future__ import annotations

import asyncio
import contextvars
import logging

from app.services.job_store import JobStore

logger = logging.getLogger(__name__)

current_job_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "current_job_id", default=None
)


class JobStageObserver:
    """`semantic_plan()`が呼ばれた時点で`extracting`へ進める。

    `segmentation_attempt()`は候補ごとに何度も呼ばれる（12候補 x 最大retry回数分）が、
    stageとしては既にextractingなので使わない（Firestore書き込みを無駄に増やさない）。
    """

    def __init__(self, job_store: JobStore) -> None:
        self._job_store = job_store

    def semantic_plan(self, plan: object, images: object) -> None:
        del plan, images
        self._schedule_stage("extracting")

    def segmentation_attempt(self, **kwargs: object) -> None:
        del kwargs

    def _schedule_stage(self, stage: str) -> None:
        job_id = current_job_id.get()
        if job_id is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self._safe_set_stage(job_id, stage))

    async def _safe_set_stage(self, job_id: str, stage: str) -> None:
        try:
            await self._job_store.set_stage(job_id, stage)  # type: ignore[arg-type]
        except Exception:
            logger.exception("stage update failed job_id=%s stage=%s", job_id, stage)
