"""POST /api/v1/artworks/generate の契約テスト。"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings
from app.main import create_app


def _keys(value: Any) -> set[str]:
    """入れ子を含む全Key名を集める。"""

    if isinstance(value, dict):
        return set(value) | {k for v in value.values() for k in _keys(v)}
    if isinstance(value, list):
        return {k for v in value for k in _keys(v)}
    return set()


def test_mock_mode_returns_artwork_and_asset_manifest(client: TestClient, photo_upload) -> None:
    response = client.post(
        "/api/v1/artworks/generate",
        files=[photo_upload],
        data={"memoryText": "海に行った日"},
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"artwork", "assetManifest"}

    artwork = body["artwork"]
    assert artwork["schemaVersion"] == "1.0"
    # Artwork Data 本体へ Runtime依存URLもBase64 Binaryも埋め込まない（AGENTS.md §3.3）
    assert not _keys(artwork) & {"url", "data", "base64", "src"}

    manifest_ids = {a["assetId"] for a in body["assetManifest"]["assets"]}
    referenced = {layer["asset"]["assetId"] for layer in artwork["layers"]}
    referenced |= {p["asset"]["assetId"] for p in artwork["sourcePhotos"]}
    assert referenced <= manifest_ids


def test_memory_text_is_optional(client: TestClient, photo_upload) -> None:
    response = client.post("/api/v1/artworks/generate", files=[photo_upload])
    assert response.status_code == 200


def test_published_asset_url_is_fetchable(client: TestClient, photo_upload) -> None:
    body = client.post("/api/v1/artworks/generate", files=[photo_upload]).json()
    url = body["assetManifest"]["assets"][0]["url"]

    fetched = client.get(url)
    assert fetched.status_code == 200
    assert fetched.headers["content-type"].startswith("image/")


def test_generate_logs_elapsed_time(
    client: TestClient, photo_upload, caplog: pytest.LogCaptureFixture
) -> None:
    """同期/非同期判断(【PoC後FIX】)の実測材料。Responseの形は変えず、Log行だけで残す。"""

    with caplog.at_level(logging.INFO, logger="app.api.v1.artworks"):
        response = client.post("/api/v1/artworks/generate", files=[photo_upload])

    assert response.status_code == 200
    messages = [r.message for r in caplog.records]
    assert any(m.startswith("ai_generate elapsed=") for m in messages)
    assert any(m.startswith("generate_artwork elapsed=") for m in messages)


def test_asset_url_scheme_is_https_when_deployed(tmp_path: Path, photo_upload) -> None:
    """Cloud RunはTLSをFrontendで終端するため、Container内のRequestはhttpに見える。
    APP_ENV=deployed のときはAsset ManifestのURLをhttpsへ補正する（Mixed Content対策）。
    ローカル開発（APP_ENV=local既定値）はこの補正をしない。conftest.pyのclientで確認済み。
    """

    settings = Settings(
        app_env="deployed",
        mock_ai=True,
        contracts_dir=REPO_ROOT / "contracts",
        cors_origins="http://localhost:5173",
        asset_dir=tmp_path / "assets",
        _env_file=None,
    )
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post("/api/v1/artworks/generate", files=[photo_upload])

    assert response.status_code == 200
    urls = [asset["url"] for asset in response.json()["assetManifest"]["assets"]]
    assert urls
    assert all(url.startswith("https://") for url in urls)


def test_photos_are_variable_length(client: TestClient, photo_upload) -> None:
    """固定5枚の契約ではない。1枚でも通る。"""

    response = client.post("/api/v1/artworks/generate", files=[photo_upload] * 3)
    assert response.status_code == 200


def test_unsupported_media_type(client: TestClient) -> None:
    response = client.post(
        "/api/v1/artworks/generate",
        files=[("photos", ("memo.txt", b"not an image", "text/plain"))],
    )

    assert response.status_code == 415
    error = response.json()["error"]
    assert error["code"] == "UNSUPPORTED_MEDIA_TYPE"
    assert error["retryable"] is False
    assert set(error) == {"code", "message", "retryable", "details"}


def test_missing_photos_is_invalid_input(client: TestClient) -> None:
    response = client.post("/api/v1/artworks/generate", data={"memoryText": "x"})

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_error_body_does_not_leak_internals(client: TestClient) -> None:
    response = client.post(
        "/api/v1/artworks/generate",
        files=[("photos", ("memo.txt", b"x", "text/plain"))],
    )

    text = response.text
    for leak in ("Traceback", "/home/", "backend/app", "content_type"):
        assert leak not in text
