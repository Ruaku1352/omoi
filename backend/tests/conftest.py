from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.main import create_app

CONTRACTS_DIR = REPO_ROOT / "contracts"


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
