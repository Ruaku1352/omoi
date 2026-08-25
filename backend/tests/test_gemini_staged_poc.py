"""段階的Gemini PoCの副作用なしUnit Test。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError


def _module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_gemini_staged_poc.py"
    spec = importlib.util.spec_from_file_location("gemini_staged_poc", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_provisional_selection_is_p0_supported_formats() -> None:
    module = _module()
    assert len(module.PROVISIONAL_SELECTED_FILES) == 5
    assert all(
        Path(name).suffix.lower() in module.P0_MIME_TYPES
        for name in module.PROVISIONAL_SELECTED_FILES
    )


def test_interactions_image_input_uses_content_blocks() -> None:
    module = _module()
    photo = module.InputPhoto("sample.jpg", "image/jpeg", b"image-bytes")

    blocks = module._image_input("describe", [photo])

    assert blocks[0] == {"type": "text", "text": "describe"}
    assert blocks[1]["type"] == "image"
    assert blocks[1]["mime_type"] == "image/jpeg"
    assert blocks[1]["data"] == "aW1hZ2UtYnl0ZXM="


def test_error_classifier_distinguishes_observable_causes() -> None:
    module = _module()

    class HttpError(Exception):
        def __init__(self, code: int) -> None:
            self.code = code

    class ReadTimeout(Exception):
        pass

    assert module.classify_error(HttpError(429)) == ("rate_limited", "http_429")
    assert module.classify_error(HttpError(503)) == ("service_unavailable", "http_503")
    assert module.classify_error(HttpError(504)) == ("gateway_timeout", "http_504")
    assert module.classify_error(ReadTimeout()) == ("client_timeout", "client_read_timeout")

    class Example(BaseModel):
        value: int

    try:
        Example.model_validate({"value": "not-an-int"})
    except ValidationError as exc:
        assert module.classify_error(exc) == ("schema_validation_failure", "no_http_response")

    assert module.classify_error(module.AiNotConfiguredError()) == (
        "local_configuration_error",
        "no_http_request",
    )
