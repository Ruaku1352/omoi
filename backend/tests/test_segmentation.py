from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ai.segmentation import EfficientSamOnnxSegmenter


class _FakeSession:
    def get_inputs(self):
        return [
            type("Input", (), {"name": "batched_images"})(),
            type("Input", (), {"name": "batched_point_coords"})(),
            type("Input", (), {"name": "batched_point_labels"})(),
        ]

    def run(self, _outputs, inputs):
        assert inputs["batched_images"].shape == (1, 3, 5, 10)
        logits = np.full((1, 1, 3, 5, 10), -1.0, dtype=np.float32)
        logits[0, 0, 2, 1:4, 2:8] = 1.0
        scores = np.array([[[0.1, 0.2, 0.9]]], dtype=np.float32)
        return logits, scores


def test_efficient_sam_returns_stage_timings(monkeypatch, tmp_path: Path) -> None:
    model_path = tmp_path / "efficient-sam.onnx"
    model_path.write_bytes(b"test")
    monkeypatch.setattr(
        "ai.segmentation.ort.InferenceSession", lambda *_args, **_kwargs: _FakeSession()
    )

    result = EfficientSamOnnxSegmenter(model_path, max_side=10).segment(
        Image.new("RGB", (20, 10), "white"), (2, 2, 16, 8)
    )

    assert result.mask.shape == (10, 20)
    assert result.score == pytest.approx(0.9)
    assert result.mask.any()
    assert result.timings.resize_elapsed_ms is not None
    assert result.timings.tensor_preparation_elapsed_ms is not None
    assert result.timings.onnx_inference_elapsed_ms is not None
    assert result.timings.mask_restore_elapsed_ms is not None
    assert all(
        value >= 0
        for value in (
            result.timings.resize_elapsed_ms,
            result.timings.tensor_preparation_elapsed_ms,
            result.timings.onnx_inference_elapsed_ms,
            result.timings.mask_restore_elapsed_ms,
        )
    )
