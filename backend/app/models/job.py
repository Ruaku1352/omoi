"""非同期化のJob状態Model。

正本Schema化（`contracts/`配下への追加）は横断支援担当（だいちゃん）が行う。
ここはBackend実装が実際に返す形を、依頼された契約どおりに定義したもの
（jobId / status / stage / result / error）。`result` は既存の
`GenerateSuccessResponse` とまったく同じ形をそのまま同梱する（新しい形を作らない）。

status: pending / processing / completed / failed
stage:  analyzing / extracting / composing / finalizing
        （Retry中も直前に到達していたstageを保持する。"retrying"は公開Statusに追加しない）
"""

from __future__ import annotations

from typing import Any, Literal

from app.models.api import GenerateSuccessResponse
from app.models.artwork import ContractModel, OpaqueId

JobStage = Literal["analyzing", "extracting", "composing", "finalizing"]


class JobAccepted(ContractModel):
    """POST /api/v1/artworks/generate の202 Response。"""

    job_id: OpaqueId


class JobActiveStatus(ContractModel):
    """status: pending / processing のときのGET /api/v1/jobs/{jobId}。"""

    job_id: OpaqueId
    status: Literal["pending", "processing"]
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


JobStatusResponse = JobActiveStatus | JobCompletedStatus | JobFailedStatus
