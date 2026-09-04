"""GET /api/v1/jobs/{jobId}

Frontendのポーリング先。ポーリング間隔は2秒を初期値とする
（非同期化方針Doc §3。Frontend側の実装事項でありBackendはEndpointを提供するだけ）。

存在しないjobId、および将来API上の有効期限を過ぎたjobIdはどちらも
`JOB_NOT_FOUND`（404）として一律扱う。物理削除タイミング（Firestore TTL Policy等）と
API上の有効期限判定は分離する方針のため、Backend側で個別の期限ロジックは持たない
（非同期化方針Doc §5）。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from app.errors import ApiError, ErrorCode
from app.models.job import (
    JobCompletedStatus,
    JobErrorBody,
    JobFailedStatus,
    JobPendingStatus,
    JobProcessingStatus,
    JobStatusResponse,
)
from app.services.job_store import JobStore

router = APIRouter(prefix="/jobs", tags=["jobs"])


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: str,
    job_store: Annotated[JobStore, Depends(get_job_store)],
) -> JobStatusResponse:
    job = await job_store.get(job_id)
    if job is None:
        raise ApiError(
            ErrorCode.JOB_NOT_FOUND,
            "指定された作品生成は見つかりませんでした。",
            log_message=f"job not found: {job_id}",
        )

    if job.status == "completed":
        assert job.result is not None
        return JobCompletedStatus(job_id=job_id, status="completed", result=job.result)

    if job.status == "failed":
        assert job.error is not None
        return JobFailedStatus(
            job_id=job_id,
            status="failed",
            error=JobErrorBody.model_validate(job.error),
        )

    if job.status == "pending":
        return JobPendingStatus(job_id=job_id, status="pending")

    assert job.stage is not None  # processingはJobRunner.run()が必ずstageとセットで進める
    return JobProcessingStatus(job_id=job_id, status="processing", stage=job.stage)
