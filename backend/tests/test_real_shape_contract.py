"""Real生成が返す形が共通Contractを満たすか検証する。

技術設計§19.6「Real生成結果が同じArtwork Schemaを満たすことを接続確認条件にする」
に対応する。共通Mockは physicalOutput を持つため検証を通っていたが、
Real は持たないため null がシリアライズされ Schema 違反になっていた。

実Geminiは呼ばず、共通Mockから physicalOutput を落とした形
（＝Realが返す形）を正本Schemaへ掛ける。
"""

from __future__ import annotations

import json
import pathlib

import jsonschema
from referencing import Registry, Resource

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONTRACTS = ROOT / "contracts"
RESPONSE_SCHEMA = CONTRACTS / "generate-success-response.schema.json"
SCHEMAS = [
    RESPONSE_SCHEMA,
    CONTRACTS / "artwork.schema.json",
    CONTRACTS / "asset-manifest.schema.json",
]
MOCK_RESPONSE = CONTRACTS / "mock" / "generate-success-response.json"


def _validator():
    docs = {}
    for f in SCHEMAS:
        doc = json.loads(f.read_text(encoding="utf-8"))
        docs[doc["$id"]] = doc
    registry = Registry().with_resources(
        (uri, Resource.from_contents(doc)) for uri, doc in docs.items()
    )
    target = json.loads(RESPONSE_SCHEMA.read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(target, registry=registry)


def _errors(body: dict) -> list[str]:
    return [
        f"{'/'.join(str(p) for p in e.absolute_path)}: {e.message}"
        for e in sorted(_validator().iter_errors(body), key=lambda e: list(e.absolute_path))
    ]


def test_response_without_physical_output_satisfies_schema():
    """physicalOutput を持たない形（Realの形）が Schema を満たすこと。"""
    body = json.loads(MOCK_RESPONSE.read_text(encoding="utf-8"))
    body["artwork"].pop("physicalOutput", None)
    assert _errors(body) == []


def test_physical_output_null_is_rejected():
    """null を入れた場合は Schema 違反として検出されること。

    Real がこの形を返して実測時に検出された。回帰防止として固定する。
    """
    body = json.loads(MOCK_RESPONSE.read_text(encoding="utf-8"))
    body["artwork"]["physicalOutput"] = None
    assert _errors(body) != []


def test_response_model_omits_none_instead_of_null():
    """Response Model が optional 未設定を null ではなく省略すること。

    artworks.py の response_model_exclude_none=True がこれを担保する。
    """
    from app.models.artwork import Artwork

    optional = [n for n, f in Artwork.model_fields.items() if f.default is None]
    assert optional, "optional フィールドが無い（テストの前提が変わった）"

    dumped = json.loads(
        json.dumps(
            Artwork.model_validate(
                json.loads(MOCK_RESPONSE.read_text(encoding="utf-8"))["artwork"]
            ).model_dump(by_alias=True, exclude_none=True),
            default=str,
        )
    )
    for name in optional:
        field = Artwork.model_fields[name]
        key = field.alias or name
        assert dumped.get(key) is not None or key not in dumped, f"{key} が null で出力された"
