"""Semantic transport診断のprivate安全性とcase選択を固定する。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def _module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "probe_gemini_semantic_transport.py"
    sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location("semantic_transport_probe", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_load_case_selects_exactly_one_case_from_private_dataset(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "dataset.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {"id": "first", "photos": ["a.png"] * 5, "memoryText": "first"},
                    {"id": "second", "photos": ["b.png"] * 5, "memoryText": "second"},
                ]
            }
        ),
        encoding="utf-8",
    )

    case_id, photos, memory_text = module._load_case(path, "second")

    assert case_id == "second"
    assert photos == ["b.png"] * 5
    assert memory_text == "second"


def test_safe_error_metadata_excludes_provider_message_and_headers() -> None:
    module = _module()

    class FakeResponse:
        headers = {"x-goog-request-id": "private-request-id", "authorization": "secret"}

    class ProviderError(Exception):
        code = 503
        response = FakeResponse()

    outer = RuntimeError("safe outer")
    outer.__cause__ = ProviderError("private provider detail")

    metadata = module._safe_error_metadata(outer)

    assert metadata == {
        "errorType": "RuntimeError",
        "providerErrorType": "ProviderError",
        "httpStatus": 503,
        "requestIdPresent": True,
        "causeDepth": 1,
    }
    assert "private" not in json.dumps(metadata)
    assert "secret" not in json.dumps(metadata)
