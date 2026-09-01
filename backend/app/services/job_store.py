"""非同期化のJob状態を持つStore。

`AssetStore`と同じ設計方針: Protocolで抽象化し、`JOB_STORE_BACKEND`で
実装を差し替える。既定は`memory`（ローカル/テスト用、Firestore不要）。
本番は`firestore`。API境界（GET /api/v1/jobs/{jobId}が返す形）は実装を
差し替えても変えない。

物理削除タイミングとAPI上の有効期限判定は分離する（非同期化方針Doc §5）。
このStore自体はTTLを持たず、Firestore TTL Policy / GCS Object Lifecycle等
インフラ側の削除に任せる。削除された・元から無いjobIdは`get()`がNoneを返し、
呼び出し側が一律 `JOB_NOT_FOUND` として扱う。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

JobStatus = Literal["pending", "processing", "completed", "failed"]
JobStage = Literal["analyzing", "extracting", "composing", "finalizing"]


@dataclass
class JobRecord:
    job_id: str
    status: JobStatus
    stage: JobStage
    memory_text: str | None
    #: `GenerateSuccessResponse.model_dump(by_alias=True, exclude_none=True)` の結果。
    result: dict[str, Any] | None = None
    #: {"code", "message", "retryable", "details"}
    error: dict[str, Any] | None = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobStore(Protocol):
    async def create(self, job_id: str, *, memory_text: str | None) -> None: ...

    async def get(self, job_id: str) -> JobRecord | None: ...

    async def set_stage(self, job_id: str, stage: JobStage) -> None:
        """statusをprocessingへ進めつつstageを更新する（Retry中も直前stageを保持する用途）。"""
        ...

    async def mark_completed(self, job_id: str, result: dict[str, Any]) -> None: ...

    async def mark_failed(
        self,
        job_id: str,
        *,
        code: str,
        message: str,
        retryable: bool,
        details: Any = None,
    ) -> None: ...


class InMemoryJobStore:
    """ローカル開発・テスト用。Process内Dictで完結する（Firestore不要）。

    Cloud Runは複数Instanceを持ちうるため本番では使わない
    （`docs/deploy.md` §4のLocalDirAssetStoreと同じ制約）。
    """

    def __init__(self) -> None:
        self._jobs: dict[str, JobRecord] = {}

    async def create(self, job_id: str, *, memory_text: str | None) -> None:
        self._jobs[job_id] = JobRecord(
            job_id=job_id,
            status="pending",
            stage="analyzing",
            memory_text=memory_text,
        )

    async def get(self, job_id: str) -> JobRecord | None:
        return self._jobs.get(job_id)

    async def set_stage(self, job_id: str, stage: JobStage) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = "processing"
        job.stage = stage
        job.updated_at = time.time()

    async def mark_completed(self, job_id: str, result: dict[str, Any]) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = "completed"
        job.result = result
        job.updated_at = time.time()

    async def mark_failed(
        self,
        job_id: str,
        *,
        code: str,
        message: str,
        retryable: bool,
        details: Any = None,
    ) -> None:
        job = self._jobs.get(job_id)
        if job is None:
            return
        job.status = "failed"
        job.error = {
            "code": code,
            "message": message,
            "retryable": retryable,
            "details": details,
        }
        job.updated_at = time.time()


class FirestoreJobStore:
    """本番用。Google Cloud Firestore (Native mode) へ1 Document = 1 Jobで保持する。

    Documentは `created_at` を Firestore TTL Policy 用のFieldとしても使える形にしておく
    （実際のTTL Policy設定はチームでBucket名・保持期間と合わせてInfra側に作る。
    `docs/deploy.md` 参照）。
    """

    def __init__(self, *, project_id: str | None, collection: str) -> None:
        # google-cloud-firestoreは`job_store_backend=firestore`のときだけ要るので
        # 遅延Importにして、`memory`運用時に依存が無くても壊れないようにする。
        from google.cloud import firestore  # noqa: PLC0415

        self._client = firestore.AsyncClient(project=project_id)
        self._collection = self._client.collection(collection)

    def _doc(self, job_id: str):  # noqa: ANN202
        return self._collection.document(job_id)

    async def create(self, job_id: str, *, memory_text: str | None) -> None:
        now = time.time()
        await self._doc(job_id).set(
            {
                "jobId": job_id,
                "status": "pending",
                "stage": "analyzing",
                "memoryText": memory_text,
                "result": None,
                "error": None,
                "createdAt": now,
                "updatedAt": now,
            }
        )

    async def get(self, job_id: str) -> JobRecord | None:
        snapshot = await self._doc(job_id).get()
        if not snapshot.exists:
            return None
        data = snapshot.to_dict() or {}
        return JobRecord(
            job_id=job_id,
            status=data["status"],
            stage=data["stage"],
            memory_text=data.get("memoryText"),
            result=data.get("result"),
            error=data.get("error"),
            created_at=data.get("createdAt", 0.0),
            updated_at=data.get("updatedAt", 0.0),
        )

    async def set_stage(self, job_id: str, stage: JobStage) -> None:
        await self._doc(job_id).update(
            {"status": "processing", "stage": stage, "updatedAt": time.time()}
        )

    async def mark_completed(self, job_id: str, result: dict[str, Any]) -> None:
        await self._doc(job_id).update(
            {"status": "completed", "result": result, "updatedAt": time.time()}
        )

    async def mark_failed(
        self,
        job_id: str,
        *,
        code: str,
        message: str,
        retryable: bool,
        details: Any = None,
    ) -> None:
        await self._doc(job_id).update(
            {
                "status": "failed",
                "error": {
                    "code": code,
                    "message": message,
                    "retryable": retryable,
                    "details": details,
                },
                "updatedAt": time.time(),
            }
        )


def build_job_store(settings: Any) -> JobStore:
    if settings.job_store_backend == "memory":
        return InMemoryJobStore()
    if settings.job_store_backend == "firestore":
        return FirestoreJobStore(
            project_id=settings.firestore_project_id,
            collection=settings.firestore_collection,
        )
    raise ValueError(f"未対応のJOB_STORE_BACKENDです: {settings.job_store_backend}")
