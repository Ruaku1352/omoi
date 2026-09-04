"""非同期化のJob状態Model。

正本Schemaは `contracts/job-status-response.schema.json` /
`contracts/generate-accepted-response.schema.json`（横断支援担当・だいちゃんが追加）。
ここはその写像であって別の正本ではない。

status: pending / processing / completed / failed
stage:  analyzing / extracting / composing / finalizing
        （Retry中も直前に到達していたstageを保持する。"retrying"は公開Statusに追加しない）

正本Schemaは `status=pending` のとき `stage` を持つことを禁止している
（受付済みだがWorkerがまだ着手していない状態なので、直前の到達段階も無い）。
そのため`pending`と`processing`を同じModelにせず分ける。
"""

from __future__ import annotations

from typing import Any, Literal

from app.models.api import GenerateSuccessResponse
from app.models.artwork import ContractModel, OpaqueId

JobStage = Literal["analyzing", "extracting", "composing", "finalizing"]


class JobAccepted(ContractModel):
    """POST /api/v1/artworks/generate の202 Response。"""

    job_id: OpaqueId


class JobPendingStatus(ContractModel):
    """status: pending。Task投入済み・Worker着手前。stageを持たない。"""

    job_id: OpaqueId
    status: Literal["pending"]


class JobProcessingStatus(ContractModel):
    """status: processing。stageは必須（Workerが着手した時点で必ず値が入る）。"""

    job_id: OpaqueId
    status: Literal["processing"]
    stage: JobStage


class JobCompletedStatus(ContractModel):
    job_id: OpaqueId
    status: Literal["completed"]
    #: 既存 contracts/generate-success-response.schema.json とまったく同じ形。
    result: GenerateSuccessResponse


class JobErrorBody(ContractModel):
    code: str
    message: str
    retryable: bool
    details: Any | None = None


class JobFailedStatus(ContractModel):
    job_id: OpaqueId
    status: Literal["failed"]
    error: JobErrorBody


JobStatusResponse = JobPendingStatus | JobProcessingStatus | JobCompletedStatus | JobFailedStatus
