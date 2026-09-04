"""POST /internal/jobs/{jobId}/run — Cloud Tasksから叩かれるWorker Endpoint。

Product API Contract（`/api/v1`）ではない。OpenAPI Schemaにも載せない。
`GET /health`や `/dev/assets` と同じく、`app/main.py`で`/api/v1`の外側にMountする。

認証: `X-Omoi-Task-Token`と`TASK_WORKER_TOKEN`の一致を見る簡易共有Secret方式。
Cloud TasksのOIDC token検証まではやらない（Bucket名同様、チームと相談の上で
より堅い方式（OIDC token検証）に差し替えられる。Manifest / Job Contractへは影響しない）。

Idempotency: 既にcompleted/failedのJob、または存在しないJobは即200（何もしない）。
Cloud Tasksの再配送で同じ作品を二重生成しない（非同期化方針Doc §6）。

Retry: `X-CloudTasks-TaskRetryCount`（初回0）を見て、
`JOB_MAX_ATTEMPTS`未満ならRetryable失敗を503で返しCloud Tasks自身のRetryに任せる。
上限到達後もRetryable失敗ならここでfailedへ確定する。
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response

from app.api.v1.artworks import public_base_url
from app.config import Settings
from app.errors import ApiError
from app.services.job_input_store import JobInputStore
from app.services.job_runner import JobRunner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/jobs", tags=["internal"])


def _verify_task_token(request: Request, settings: Settings) -> None:
    if not settings.task_worker_token:
        # ローカル開発でTASK_WORKER_TOKEN未設定なら検証しない。
        # APP_ENV=deployedなのに未設定は設定ミスなので拒否する。
        if settings.app_env == "deployed":
            raise HTTPException(status_code=503, detail="TASK_WORKER_TOKEN not configured")
        return
    if request.headers.get("X-Omoi-Task-Token") != settings.task_worker_token:
        raise HTTPException(status_code=403, detail="invalid task token")


@router.post("/{job_id}/run", include_in_schema=False)
async def run_job(job_id: str, request: Request) -> Response:
    settings: Settings = request.app.state.settings
    _verify_task_token(request, settings)

    job_store = request.app.state.job_store
    job_input_store: JobInputStore = request.app.state.job_input_store
    runner: JobRunner = request.app.state.job_runner

    job = await job_store.get(job_id)
    if job is None or job.status in ("completed", "failed"):
        # 存在しない・既に終端状態: 再配送されても何もしない（Idempotency）。
        return Response(status_code=200)

    retry_count = int(request.headers.get("X-CloudTasks-TaskRetryCount", "0"))
    photos = await job_input_store.load(job_id)
    base_url = public_base_url(request, settings)

    try:
        await runner.run(job_id, photos, job.memory_text, base_url=base_url)
    except ApiError as exc:
        # exc.retryable=Falseは runner.run() 内で既にfailedへ確定済み。
        if retry_count < settings.job_max_attempts - 1:
            logger.warning(
                "job_retry job_id=%s attempt=%d code=%s", job_id, retry_count + 1, exc.code
            )
            raise HTTPException(status_code=503, detail="transient failure, will retry") from exc
        logger.error("job_retries_exhausted job_id=%s attempts=%d", job_id, retry_count + 1)
        await job_store.mark_failed(
            job_id,
            code=str(exc.code),
            message=exc.message,
            retryable=False,
            details=exc.details,
        )
        return Response(status_code=200)

    await job_input_store.delete(job_id)
    return Response(status_code=200)
