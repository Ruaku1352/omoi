"""POST /api/v1/artworks/generate の契約テスト。"""

from __future__ import annotations

from fastapi.testclient import TestClient


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
    # Artwork Data 本体へ Runtime依存URLを埋め込まない
    assert "url" not in response.text.split('"assetManifest"')[0]

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
