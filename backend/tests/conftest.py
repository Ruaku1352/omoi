from __future__ import annotations

import json
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.main import create_app

CONTRACTS_DIR = REPO_ROOT / "contracts"


def wait_for_job(client: TestClient, job_id: str, *, timeout_s: float = 5.0):
    """`GET /api/v1/jobs/{jobId}`をcompleted/failedになるまでPollingする。

    テストで使うTask Queueは既定で`inline`（同一Process内で即実行）なので、
    実際には最初の1回で終わっている。将来Backendを差し替えてもテストが
    壊れないよう、念のため短いPolling Loopにしてある。
    """

    deadline = time.monotonic() + timeout_s
    response = client.get(f"/api/v1/jobs/{job_id}")
    while response.status_code == 200 and response.json()["status"] in ("pending", "processing"):
        if time.monotonic() > deadline:
            raise TimeoutError(f"job {job_id} did not finish within {timeout_s}s")
        time.sleep(0.05)
        response = client.get(f"/api/v1/jobs/{job_id}")
    return response


def generate_and_wait(client: TestClient, **post_kwargs):
    """`POST /api/v1/artworks/generate` → `GET /api/v1/jobs/{jobId}`をまとめて行う。

    202以外（Validation Error等）が返った場合はPOSTのResponseをそのまま返す
    （呼び出し側でError系のAssertionをできるように）。
    """

    submitted = client.post("/api/v1/artworks/generate", **post_kwargs)
    if submitted.status_code != 202:
        return submitted
    job_id = submitted.json()["jobId"]
    return wait_for_job(client, job_id)


@pytest.fixture(scope="session")
def mock_artwork() -> dict:
    return json.loads((CONTRACTS_DIR / "mock" / "artwork.json").read_text(encoding="utf-8"))


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        app_env="test",
        mock_ai=True,
        contracts_dir=CONTRACTS_DIR,
        cors_origins="http://localhost:5173",
        asset_dir=tmp_path / "assets",
        _env_file=None,
    )


@pytest.fixture
def app(settings: Settings) -> FastAPI:
    return create_app(settings)


@pytest.fixture
def client(app: FastAPI) -> Iterator[TestClient]:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def photo_upload() -> tuple[str, tuple[str, bytes, str]]:
    jpeg = (CONTRACTS_DIR / "assets" / "source-p1.jpg").read_bytes()
    return ("photos", ("p1.jpg", jpeg, "image/jpeg"))
