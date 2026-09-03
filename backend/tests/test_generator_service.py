from __future__ import annotations

from pathlib import Path

from app.config import BACKEND_DIR, Settings
from app.services import generator as generator_service


def test_build_generator_resolves_relative_efficientsam_path_from_backend(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    class FakeSegmenter:
        def __init__(self, model_path: Path, max_side: int) -> None:
            captured["model_path"] = model_path
            captured["max_side"] = max_side

    class FakeGenerator:
        def __init__(self, **kwargs: object) -> None:
            captured["segmenter"] = kwargs["segmenter"]
            captured.update(kwargs)

    monkeypatch.setattr(generator_service, "LazyEfficientSamOnnxSegmenter", FakeSegmenter)
    monkeypatch.setattr(generator_service, "GeminiArtworkGenerator", FakeGenerator)
    settings = Settings(
        gemini_api_key="test-key",
        gemini_model="gemini-3.5-flash-lite",
        efficientsam_model_path=Path(".models/efficientsam_ti.onnx"),
    )

    generator_service.build_generator(settings)

    assert captured["model_path"] == BACKEND_DIR / ".models/efficientsam_ti.onnx"
    assert captured["closed_hole_fill_enabled"] is True
    assert captured["micro_island_cleanup_enabled"] is True
    assert captured["composition_overlap_instruction_enabled"] is False
    assert captured["composition_foreground_bottom_instruction_enabled"] is True
