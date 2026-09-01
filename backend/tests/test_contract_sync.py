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
from fastapi import FastAPI
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


def _patch_generator(app: FastAPI, generator) -> None:
    """app.state.generatorを差し替え、依存するjob_runner/task_queueも作り直す。

    `create_app()`はgeneratorをJobRunnerへ固定Referenceで渡すため、
    差し替えるにはjob_runner/task_queueごと作り直す必要がある
    （`app.dependency_overrides`はHTTP Request経路のDependsにしか効かず、
    JobRunnerが直接持つReferenceには効かない）。
    """

    from app.services.job_runner import JobRunner
    from app.services.task_queue import InlineTaskQueue

    app.state.generator = generator
    app.state.job_runner = JobRunner(
        generator=generator,
        asset_store=app.state.asset_store,
        job_store=app.state.job_store,
    )
    app.state.task_queue = InlineTaskQueue(app.state.job_runner)


def _asset_blobs_for(artwork: dict) -> list:
    from ai.types import AssetBlob

    ext_by_mime = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
    refs = [p["asset"] for p in artwork["sourcePhotos"]]
    for layer in artwork["layers"]:
        refs.append(layer["asset"])
        refs.extend(c["asset"] for c in layer.get("replacementCandidates", []))
    return [
        AssetBlob(
            asset_id=ref["assetId"],
            mime_type=ref["mimeType"],
            width_px=ref["widthPx"],
            height_px=ref["heightPx"],
            data=(
                CONTRACTS_DIR / "assets" / f"{ref['assetId']}.{ext_by_mime[ref['mimeType']]}"
            ).read_bytes(),
        )
        for ref in refs
    ]


def test_job_completed_without_physical_output_satisfies_schema_via_endpoint(
    app: FastAPI, client: TestClient, photo_upload, mock_artwork: dict
) -> None:
    """Real AI経路(physicalOutputを持たない)を非同期Endpoint経由で再現する。

    `Artwork`の`model_serializer`がphysicalOutputをNoneのとき省くこと自体は
    `test_real_shape_contract.py`がModel単体で検証しているが、実際に
    POST→GETのEndpointを通した結果がSchemaを満たすかはここで検証する
    （Route側の`response_model_exclude_none`付け忘れが再発してもここで拾えるように、
    Model側の対応そのものをEndpoint経由で確認する）。
    """

    from ai.types import GenerationResult

    artwork = json.loads(json.dumps(mock_artwork))
    artwork.pop("physicalOutput", None)
    assets = _asset_blobs_for(artwork)

    class _FakeGenerator:
        async def generate(self, photos, memory_text):
            del photos, memory_text
            return GenerationResult(artwork=artwork, assets=tuple(assets))

    _patch_generator(app, _FakeGenerator())

    body = generate_and_wait(client, files=[photo_upload]).json()

    assert body["status"] == "completed"
    assert "physicalOutput" not in body["result"]["artwork"]
    _validator("job-status-response.schema.json").validate(body)


def test_job_failed_error_details_stays_null_via_endpoint(
    app: FastAPI, client: TestClient, photo_upload
) -> None:
    """failedの`error.details`はNoneでも省略されず`null`のまま残ること
    （AGENTS.md §4のError形式、`job-status-response.schema.json`のerror定義どおり）。

    physicalOutputの省略をRoute単位の`response_model_exclude_none`でやると
    こちらの`details`まで一緒に消えてしまう（別の回帰）。Artwork model側だけで
    physicalOutputを省く実装にしたことをEndpoint経由で確認する。
    """

    from ai.errors import AiTimeoutError

    class _FailingGenerator:
        async def generate(self, photos, memory_text):
            del photos, memory_text
            raise AiTimeoutError("timeout")

    _patch_generator(app, _FailingGenerator())

    body = generate_and_wait(client, files=[photo_upload]).json()

    assert body["status"] == "failed"
    assert "details" in body["error"]
    assert body["error"]["details"] is None
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
