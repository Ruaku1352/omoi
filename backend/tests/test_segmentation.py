from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from ai.segmentation import EfficientSamOnnxSegmenter, EfficientSamSplitOnnxSegmenter


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


class _FakeSplitEncoderSession:
    def get_inputs(self):
        return [type("Input", (), {"name": "batched_images"})()]

    def run(self, _outputs, inputs):
        assert inputs["batched_images"].shape == (1, 3, 5, 10)
        return (np.zeros((1, 256, 64, 64), dtype=np.float32),)


class _FakeSplitDecoderSession:
    def get_inputs(self):
        return [
            type("Input", (), {"name": "image_embeddings"})(),
            type("Input", (), {"name": "batched_point_coords"})(),
            type("Input", (), {"name": "batched_point_labels"})(),
            type("Input", (), {"name": "orig_im_size"})(),
        ]

    def run(self, _outputs, inputs):
        assert inputs["image_embeddings"].shape == (1, 256, 64, 64)
        assert np.array_equal(inputs["orig_im_size"], np.array([5, 10], dtype=np.int64))
        logits = np.full((1, 1, 3, 5, 10), -1.0, dtype=np.float32)
        logits[0, 0, 1, 1:4, 2:8] = 1.0
        scores = np.array([[[0.1, 0.9, 0.2]]], dtype=np.float32)
        return logits, scores


def test_efficient_sam_returns_stage_timings(monkeypatch, tmp_path: Path) -> None:
    model_path = tmp_path / "efficient-sam.onnx"
    model_path.write_bytes(b"test")
    monkeypatch.setattr(
        "ai.segmentation.ort.InferenceSession", lambda *_args, **_kwargs: _FakeSession()
    )

    segmenter = EfficientSamOnnxSegmenter(model_path, max_side=10)
    image = Image.new("RGB", (20, 10), "white")
    result = segmenter.segment(image, (2, 2, 16, 8))
    prepared = segmenter.prepare(image)
    cached_result = segmenter.segment_prepared(prepared, (2, 2, 16, 8))

    assert result.mask.shape == (10, 20)
    assert result.score == pytest.approx(0.9)
    assert result.mask.any()
    assert np.array_equal(result.mask, cached_result.mask)
    assert result.score == cached_result.score
    assert prepared.input_image.shape == (1, 3, 5, 10)
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
    assert cached_result.timings.resize_elapsed_ms is None
    assert cached_result.timings.tensor_preparation_elapsed_ms is None


def test_split_efficient_sam_reuses_encoder_embedding(monkeypatch, tmp_path: Path) -> None:
    encoder_path = tmp_path / "encoder.onnx"
    decoder_path = tmp_path / "decoder.onnx"
    encoder_path.write_bytes(b"encoder")
    decoder_path.write_bytes(b"decoder")

    def fake_session(path, **_kwargs):
        return (
            _FakeSplitEncoderSession()
            if str(path).endswith("encoder.onnx")
            else _FakeSplitDecoderSession()
        )

    monkeypatch.setattr("ai.segmentation.ort.InferenceSession", fake_session)
    segmenter = EfficientSamSplitOnnxSegmenter(encoder_path, decoder_path, max_side=10)
    prepared = segmenter.prepare(Image.new("RGB", (20, 10), "white"))
    first = segmenter.segment_prepared(prepared, (2, 2, 16, 8))
    second = segmenter.segment_prepared(prepared, (4, 2, 18, 8))

    assert prepared.timings.encoder_inference_elapsed_ms is not None
    assert first.timings.decoder_inference_elapsed_ms is not None
    assert second.timings.decoder_inference_elapsed_ms is not None
    assert np.array_equal(first.mask, second.mask)
