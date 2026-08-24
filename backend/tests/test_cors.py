"""CORS設定の回帰テスト。

CORSの失敗はServer側から見えない。許可Originが一致しなくてもHTTPは200で返り、
足りないのは Access-Control-Allow-Origin だけなので、curl や Health Check では
正常に見えて**ブラウザだけが失敗する**。ここを固定して再発を防ぐ。
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import REPO_ROOT, Settings, classify_origins
from app.main import create_app

DEPLOYED = "https://omoi-manami-test-77989.web.app"


def build_client(cors_origins: str, tmp_path: Path) -> TestClient:
    settings = Settings(
        mock_ai=True,
        contracts_dir=REPO_ROOT / "contracts",
        cors_origins=cors_origins,
        asset_dir=tmp_path / "assets",
        _env_file=None,
    )
    return TestClient(create_app(settings), raise_server_exceptions=False)


def post_photo(client: TestClient, origin: str):
    jpeg = (REPO_ROOT / "contracts" / "assets" / "source-p1.jpg").read_bytes()
    return client.post(
        "/api/v1/artworks/generate",
        files=[("photos", ("p1.jpg", jpeg, "image/jpeg"))],
        headers={"Origin": origin},
    )


# ---- パース ----


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        pytest.param(
            f"http://localhost:5173,http://localhost:5174,{DEPLOYED}",
            ["http://localhost:5173", "http://localhost:5174", DEPLOYED],
            id="カンマ区切り",
        ),
        pytest.param(
            f" http://localhost:5173 , {DEPLOYED} ",
            ["http://localhost:5173", DEPLOYED],
            id="前後の空白",
        ),
        pytest.param(f"{DEPLOYED}/", [DEPLOYED], id="末尾スラッシュ"),
        pytest.param(f"{DEPLOYED}///", [DEPLOYED], id="末尾スラッシュ複数"),
        pytest.param("HTTPS://Omoi-Manami-Test-77989.web.app", [DEPLOYED], id="大文字"),
        pytest.param("http://a:1,,http://b:2,", ["http://a:1", "http://b:2"], id="空要素"),
        pytest.param("", [], id="未設定"),
        pytest.param("   ", [], id="空白のみ"),
        pytest.param("*", ["*"], id="ワイルドカードは保持"),
    ],
)
def test_origin_parsing(raw: str, expected: list[str]) -> None:
    valid, invalid = classify_origins(raw)
    assert valid == expected
    assert invalid == []


@pytest.mark.parametrize(
    "raw",
    [
        pytest.param('"http://localhost:5173"', id="クォート混入"),
        pytest.param("localhost:5173", id="scheme無し"),
        pytest.param(f"{DEPLOYED}/api/v1", id="Pathつき"),
        pytest.param("ftp://example.com", id="非HTTP"),
    ],
)
def test_invalid_origins_are_reported_not_silently_dropped(raw: str) -> None:
    valid, invalid = classify_origins(raw)
    assert valid == []
    assert invalid  # 握り潰さず、起動時に警告できる形で残す


# ---- 実際のCORS挙動 ----


@pytest.mark.parametrize(
    "configured",
    [
        pytest.param(DEPLOYED, id="そのまま"),
        pytest.param(f"{DEPLOYED}/", id="末尾スラッシュでも通る"),
        pytest.param(f" {DEPLOYED} ", id="空白入りでも通る"),
        pytest.param(f"http://localhost:5173,{DEPLOYED}", id="複数指定でも通る"),
    ],
)
def test_allowed_origin_gets_cors_header(configured: str, tmp_path: Path) -> None:
    response = post_photo(build_client(configured, tmp_path), DEPLOYED)

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEPLOYED


def test_multipart_post_preflight_allows_content_type(tmp_path: Path) -> None:
    client = build_client(DEPLOYED, tmp_path)

    response = client.options(
        "/api/v1/artworks/generate",
        headers={
            "Origin": DEPLOYED,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEPLOYED
    assert "POST" in response.headers["access-control-allow-methods"]
    assert "content-type" in response.headers["access-control-allow-headers"].lower()


def test_credentials_are_not_allowed(tmp_path: Path) -> None:
    """P0はCookie / 認証情報を使わない。誤って有効化されていないことを固定する。"""

    response = post_photo(build_client(DEPLOYED, tmp_path), DEPLOYED)

    assert "access-control-allow-credentials" not in response.headers


def test_asset_url_is_readable_cross_origin(tmp_path: Path) -> None:
    """3D Preview がLayer画像をWebGL Textureとして読むにはAsset側にもCORSが要る。"""

    client = build_client(DEPLOYED, tmp_path)
    manifest = post_photo(client, DEPLOYED).json()["assetManifest"]
    path = "/dev/assets" + manifest["assets"][0]["url"].split("/dev/assets")[1]

    response = client.get(path, headers={"Origin": DEPLOYED})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == DEPLOYED


def test_unlisted_origin_gets_no_cors_header(tmp_path: Path) -> None:
    response = post_photo(build_client(DEPLOYED, tmp_path), "https://evil.example")

    assert "access-control-allow-origin" not in response.headers


# ---- 設定ミスに気づけること ----


def test_empty_cors_origins_logs_actionable_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.main"):
        build_client("", tmp_path)

    message = "\n".join(r.message for r in caplog.records)
    assert "CORS_ORIGINS" in message
    assert "docs/deploy.md" in message


def test_invalid_cors_origins_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.main"):
        build_client('"http://localhost:5173"', tmp_path)

    assert "解釈できない" in "\n".join(r.message for r in caplog.records)


def test_health_exposes_effective_cors_config(tmp_path: Path) -> None:
    """ブラウザを開かずに `curl /health` で許可Originを確認できること。"""

    client = build_client(f"{DEPLOYED}/, bogus", tmp_path)

    body = client.get("/health").json()

    assert body["status"] == "ok"
    assert body["corsOrigins"] == [DEPLOYED]
    assert body["corsOriginsInvalid"] == ["bogus"]
