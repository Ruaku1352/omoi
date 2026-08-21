"""Pydantic Model が `contracts/` の正本Schemaとズレていないことを検証する。

Backend側のModelは正本の写像であって別の正本ではない（AGENTS.md §3）。
Real生成結果も同じSchemaを満たすことが接続条件なので、
Backendが返すArtworkを正本JSON Schemaへ直接掛ける。
"""

from __future__ import annotations

import json

import jsonschema
import pytest
from fastapi.testclient import TestClient

from tests.conftest import CONTRACTS_DIR


def _validator(name: str) -> jsonschema.Draft202012Validator:
    schema = json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema)


def test_response_satisfies_contract_schemas(client: TestClient, photo_upload) -> None:
    body = client.post("/api/v1/artworks/generate", files=[photo_upload]).json()

    _validator("artwork.schema.json").validate(body["artwork"])
    _validator("asset-manifest.schema.json").validate(body["assetManifest"])


def test_model_roundtrip_preserves_mock(mock_artwork: dict) -> None:
    from app.models.artwork import Artwork

    dumped = Artwork.model_validate(mock_artwork).model_dump(by_alias=True, exclude_none=True)
    assert dumped == mock_artwork


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
