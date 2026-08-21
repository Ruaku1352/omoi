"""P0で「作らないもの」を作っていないことを固定する（AGENTS.md §4）。

取得 / 更新 / finalize / bundle / jobs / assets Endpoint は
必要性が確定するまで生やさない。増やすときは公開チャンネルで共有してから。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_product_api_surface_is_only_generate(app: FastAPI) -> None:
    paths = set(app.openapi()["paths"])
    assert {p for p in paths if p.startswith("/api/v1")} == {"/api/v1/artworks/generate"}
    assert app.openapi()["paths"]["/api/v1/artworks/generate"].keys() == {"post"}


def test_health_check_is_outside_product_contract(app: FastAPI, client: TestClient) -> None:
    # Health Checkは担当裁量。Product API Contractには含めない。
    assert "/health" not in app.openapi()["paths"]

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
