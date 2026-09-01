"""P0で「作らないもの」を作っていないことを固定する（AGENTS.md §4）。

取得 / 更新 / finalize / bundle / assets Endpoint は
必要性が確定するまで生やさない。増やすときは公開チャンネルで共有してから。

`GET /api/v1/jobs/{jobId}` は非同期化にあたって正式追加されたPublic Contract
（非同期化方針Doc §3）。`/internal/*`（Worker Endpoint・同期Debug経路）は
`include_in_schema=False`なのでOpenAPIには出ない — ここでの検証対象外。
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def test_product_api_surface_is_only_generate_and_jobs(app: FastAPI) -> None:
    paths = set(app.openapi()["paths"])
    assert {p for p in paths if p.startswith("/api/v1")} == {
        "/api/v1/artworks/generate",
        "/api/v1/jobs/{job_id}",
    }
    assert app.openapi()["paths"]["/api/v1/artworks/generate"].keys() == {"post"}
    assert app.openapi()["paths"]["/api/v1/jobs/{job_id}"].keys() == {"get"}


def test_internal_endpoints_are_not_in_public_schema(app: FastAPI) -> None:
    paths = set(app.openapi()["paths"])
    assert not any(p.startswith("/internal") for p in paths)


def test_health_check_is_outside_product_contract(app: FastAPI, client: TestClient) -> None:
    # Health Checkは担当裁量。Product API Contractには含めない。
    assert "/health" not in app.openapi()["paths"]

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
