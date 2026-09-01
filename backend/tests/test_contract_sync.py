"""Pydantic Model が `contracts/` の正本Schemaとズレていないことを検証する。

Backend側のModelは正本の写像であって別の正本ではない（AGENTS.md §3）。
Real生成結果も同じSchemaを満たすことが接続条件なので、
Backendが返すArtworkを正本JSON Schemaへ直接掛ける。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from tests.conftest import CONTRACTS_DIR, generate_and_wait

SCHEMA_FILES = (
    "artwork.schema.json",
    "asset-manifest.schema.json",
    "generate-success-response.schema.json",
    "generate-accepted-response.schema.json",
    "job-status-response.schema.json",
)


def _validator(name: str) -> jsonschema.Draft202012Validator:
    """generate-success-response.schema.json は他2つを $ref するので Registry で解決する。"""

    from referencing import Registry, Resource

    schemas = {f: json.loads((CONTRACTS_DIR / f).read_text(encoding="utf-8")) for f in SCHEMA_FILES}
    registry = Registry().with_resources(
        (s["$id"], Resource.from_contents(s)) for s in schemas.values()
    )
    return jsonschema.Draft202012Validator(schemas[name], registry=registry)


def test_response_satisfies_contract_schemas(client: TestClient, photo_upload) -> None:
    body = generate_and_wait(client, files=[photo_upload]).json()

    # completed時のresultは既存generate-success-responseの正本Schemaと同じ形
    # （非同期化方針Doc: 新しい形を作らずそのまま同梱する）。
    assert body["status"] == "completed"
    _validator("generate-success-response.schema.json").validate(body["result"])


def test_generate_returns_accepted_response_satisfying_contract(
    client: TestClient, photo_upload
) -> None:
    body = client.post("/api/v1/artworks/generate", files=[photo_upload]).json()

    _validator("generate-accepted-response.schema.json").validate(body)


def test_job_pending_status_satisfies_contract_schema() -> None:
    """`pending`はstageを持たない（Schema側の`allOf`制約）。

    以前は`pending`/`processing`を同じModelで表現していて、`pending`でも
    stageを常に含めてしまいSchema違反になっていた（実際のCloud Tasks経路で
    POST直後・Worker着手前のpendingを踏むと発生する）。
    """

    from app.models.job import JobPendingStatus

    body = JobPendingStatus(job_id="job-1", status="pending").model_dump(
        by_alias=True, exclude_none=True
    )
    _validator("job-status-response.schema.json").validate(body)


def test_job_processing_status_satisfies_contract_schema() -> None:
    from app.models.job import JobProcessingStatus

    body = JobProcessingStatus(job_id="job-1", status="processing", stage="analyzing").model_dump(
        by_alias=True, exclude_none=True
    )
    _validator("job-status-response.schema.json").validate(body)


def test_job_failed_status_satisfies_contract_schema() -> None:
    from app.models.job import JobErrorBody, JobFailedStatus

    status = JobFailedStatus(
        job_id="job-1",
        status="failed",
        error=JobErrorBody(code="AI_TIMEOUT", message="失敗しました。", retryable=True),
    )
    body = status.model_dump(by_alias=True, exclude_none=True)
    _validator("job-status-response.schema.json").validate(body)


def test_job_completed_status_satisfies_contract_schema(client: TestClient, photo_upload) -> None:
    body = generate_and_wait(client, files=[photo_upload]).json()

    assert body["status"] == "completed"
    _validator("job-status-response.schema.json").validate(body)


def test_mock_mode_matches_shared_mock_response(client: TestClient, photo_upload) -> None:
    """MOCK_AI Modeの返す形が共通Mock Fixtureと一致すること。

    url は Runtime依存なので比較対象から外す。Artworkは完全一致を要求する。
    """

    body = generate_and_wait(client, files=[photo_upload]).json()["result"]
    expected = json.loads(
        (CONTRACTS_DIR / "mock" / "generate-success-response.json").read_text(encoding="utf-8")
    )

    assert body["artwork"] == expected["artwork"]

    def without_url(manifest: dict) -> list[dict]:
        return sorted(
            ({k: v for k, v in a.items() if k != "url"} for a in manifest["assets"]),
            key=lambda a: a["assetId"],
        )

    assert without_url(body["assetManifest"]) == without_url(expected["assetManifest"])


def test_model_roundtrip_preserves_mock(mock_artwork: dict) -> None:
    from app.models.artwork import Artwork

    dumped = Artwork.model_validate(mock_artwork).model_dump(by_alias=True, exclude_none=True)
    assert dumped == mock_artwork


def test_real_artwork_does_not_require_replacement_candidates(mock_artwork: dict) -> None:
    """差し替え候補はMock UI検証には有用だが、Artwork Schema上は空配列を許す。"""

    path = CONTRACTS_DIR.parent / "scripts" / "validate_contracts.py"
    spec = importlib.util.spec_from_file_location("validate_contracts", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    artwork = json.loads(json.dumps(mock_artwork))
    for layer in artwork["layers"]:
        layer["replacementCandidates"] = []

    assert not module.check_rules(artwork)
    assert module.check_mock_fixture_rules(artwork)


def test_contract_validator_allows_opaque_rgba_scene_range(tmp_path: Path) -> None:
    """背景範囲Cropは透過pixelを持たないRGBA PNGでもContract外へ出さない。"""

    path = CONTRACTS_DIR.parent / "scripts" / "validate_contracts.py"
    spec = importlib.util.spec_from_file_location("validate_contracts_opaque", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    Image.new("RGBA", (8, 6), "green").save(tmp_path / "scene-anchor.png")
    artwork = {
        "sourcePhotos": [],
        "layers": [
            {
                "layerId": "layer-1",
                "asset": {
                    "assetId": "scene-anchor",
                    "mimeType": "image/png",
                    "widthPx": 8,
                    "heightPx": 6,
                },
                "replacementCandidates": [],
            }
        ],
    }

    assert not module.check_assets(artwork, tmp_path)


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda a: a["layers"][0].update(rotation=15), id="rotation"),
        pytest.param(lambda a: a["layers"][0].update(layerIndex=99), id="layerIndex-gap"),
        pytest.param(lambda a: a["layers"][0].update(sourcePhotoId="unknown"), id="dangling-photo"),
    ],
)
def test_rule_violations_are_rejected(mock_artwork: dict, mutate) -> None:
    from app.models.artwork import Artwork
    from app.services.validation import check_artwork_rules

    artwork = json.loads(json.dumps(mock_artwork))
    mutate(artwork)

    assert check_artwork_rules(Artwork.model_validate(artwork))
