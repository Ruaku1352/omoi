"""Jobの実行を投入する。

`InlineTaskQueue`: ローカル/テスト用。Cloud Tasksを使わず、同一Process内で
即座に`JobRunner`を実行する（Photosはメモリ上でそのまま渡すので
`JobInputStore`を経由しない）。

`CloudTasksQueue`: 本番用。Photosを`JobInputStore`（GCS）へ保存し、
Cloud TasksへjobIdだけの小さいPayloadでTaskを積む。実処理は同一Cloud Runの
Internal Worker Endpoint（`app/api/internal/jobs.py`）が後から呼ばれて行う。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol

from ai.types import InputPhoto
from app.services.job_input_store import JobInputStore
from app.services.job_runner import JobRunner


class TaskQueue(Protocol):
    async def enqueue(
        self,
        job_id: str,
        photos: Sequence[InputPhoto],
        memory_text: str | None,
        *,
        base_url: str,
    ) -> None: ...


class InlineTaskQueue:
    """`JobRunner.run()`をその場で実行する。Cloud Tasksの非同期性は再現しない
    （ローカル開発・テストで202直後にGET /jobsした瞬間completedになっていて構わない）。
    """

    def __init__(self, runner: JobRunner) -> None:
        self._runner = runner

    async def enqueue(
        self,
        job_id: str,
        photos: Sequence[InputPhoto],
        memory_text: str | None,
        *,
        base_url: str,
    ) -> None:
        await self._runner.run(job_id, photos, memory_text, base_url=base_url)


class CloudTasksQueue:
    def __init__(
        self,
        *,
        job_input_store: JobInputStore,
        project_id: str,
        location: str,
        queue: str,
        worker_base_url: str,
        service_account_email: str | None,
        worker_token: str | None,
    ) -> None:
        self._job_input_store = job_input_store
        self._project_id = project_id
        self._location = location
        self._queue = queue
        self._worker_base_url = worker_base_url.rstrip("/")
        self._service_account_email = service_account_email
        self._worker_token = worker_token

    def _client(self) -> Any:
        from google.cloud import tasks_v2  # noqa: PLC0415

        return tasks_v2.CloudTasksClient()

    async def enqueue(
        self,
        job_id: str,
        photos: Sequence[InputPhoto],
        memory_text: str | None,
        *,
        base_url: str,
    ) -> None:
        del memory_text  # 既にJobStore.create()でJob Documentへ保存済み
        del base_url  # WorkerがOwn Requestから自分のbase_urlを取り直す
        import asyncio  # noqa: PLC0415
        import json  # noqa: PLC0415

        from google.cloud import tasks_v2  # noqa: PLC0415

        await self._job_input_store.save(job_id, photos)

        def _create_task() -> None:
            client = self._client()
            parent = client.queue_path(self._project_id, self._location, self._queue)
            url = f"{self._worker_base_url}/internal/jobs/{job_id}/run"
            headers = {"Content-Type": "application/json"}
            if self._worker_token:
                headers["X-Omoi-Task-Token"] = self._worker_token

            http_request: dict[str, Any] = {
                "http_method": tasks_v2.HttpMethod.POST,
                "url": url,
                "headers": headers,
                "body": json.dumps({"jobId": job_id}).encode("utf-8"),
            }
            if self._service_account_email:
                http_request["oidc_token"] = {"service_account_email": self._service_account_email}
            client.create_task(request={"parent": parent, "task": {"http_request": http_request}})

        await asyncio.to_thread(_create_task)


def build_task_queue(settings: Any, runner: JobRunner, job_input_store: JobInputStore) -> TaskQueue:
    if settings.task_queue_backend == "inline":
        return InlineTaskQueue(runner)
    if settings.task_queue_backend == "cloud_tasks":
        missing = [
            name
            for name, value in (
                ("CLOUD_TASKS_PROJECT_ID", settings.cloud_tasks_project_id),
                ("CLOUD_TASKS_LOCATION", settings.cloud_tasks_location),
                ("CLOUD_TASKS_WORKER_BASE_URL", settings.cloud_tasks_worker_base_url),
            )
            if not value
        ]
        if missing:
            raise ValueError(f"TASK_QUEUE_BACKEND=cloud_tasksには{', '.join(missing)}が要る")
        return CloudTasksQueue(
            job_input_store=job_input_store,
            project_id=settings.cloud_tasks_project_id,
            location=settings.cloud_tasks_location,
            queue=settings.cloud_tasks_queue,
            worker_base_url=settings.cloud_tasks_worker_base_url,
            service_account_email=settings.cloud_tasks_service_account_email,
            worker_token=settings.task_worker_token,
        )
    raise ValueError(f"未対応のTASK_QUEUE_BACKENDです: {settings.task_queue_backend}")
