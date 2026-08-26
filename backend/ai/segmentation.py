"""EfficientSAM-Ti ONNXのbox-prompt adapter。RuntimeではWeightをdownloadしない。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import onnxruntime as ort
from PIL import Image

from ai.errors import AiError, AiNotConfiguredError
from ai.image_ops import BoxPx


@dataclass(frozen=True)
class SegmentationResult:
    mask: np.ndarray
    score: float | None
    prompt_box_px: BoxPx


class Segmenter(Protocol):
    def segment(self, image: Image.Image, box_px: BoxPx) -> SegmentationResult: ...


class EfficientSamOnnxSegmenter:
    """Official yformer/EfficientSAM の単一ONNX artifactをCPUで実行する。

    Box promptは公式demoと同様に2 corner pointsとlabels ``2, 3`` に変換する。
    Sessionはgenerator生成時に1回だけloadされ、requestごとにloadしない。
    """

    _INPUT_IMAGE = "batched_images"
    _INPUT_POINTS = "batched_point_coords"
    _INPUT_LABELS = "batched_point_labels"

    def __init__(self, model_path: Path, max_side: int) -> None:
        if not model_path.is_file():
            raise AiNotConfiguredError(
                "EfficientSAM ONNX modelが見つかりません。設定を確認してください"
            )
        self._max_side = max_side
        try:
            self._session = ort.InferenceSession(
                str(model_path), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise AiNotConfiguredError("EfficientSAM ONNX modelをloadできません") from exc
        input_names = {item.name for item in self._session.get_inputs()}
        required = {self._INPUT_IMAGE, self._INPUT_POINTS, self._INPUT_LABELS}
        if not required <= input_names:
            raise AiNotConfiguredError("EfficientSAM ONNX modelの入力形式が一致しません")

    def segment(self, image: Image.Image, box_px: BoxPx) -> SegmentationResult:
        resized, scale_x, scale_y = self._resize(image)
        x0, y0, x1, y1 = box_px
        points = np.array(
            [[[[x0 * scale_x, y0 * scale_y], [x1 * scale_x, y1 * scale_y]]]], dtype=np.float32
        )
        labels = np.array([[[2, 3]]], dtype=np.float32)
        input_image = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        try:
            logits, predicted_iou, *_ = self._session.run(
                None,
                {
                    self._INPUT_IMAGE: input_image,
                    self._INPUT_POINTS: points,
                    self._INPUT_LABELS: labels,
                },
            )
        except Exception as exc:
            raise AiError("EfficientSAMの推論に失敗しました") from exc

        scores = np.asarray(predicted_iou)[0, 0]
        index = int(np.argmax(scores))
        mask = np.asarray(logits)[0, 0, index] >= 0
        if mask.shape != (resized.height, resized.width):
            mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        else:
            mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        restored = mask_image.resize(image.size, Image.Resampling.NEAREST)
        return SegmentationResult(
            mask=np.asarray(restored, dtype=np.uint8) > 0,
            score=float(scores[index]),
            prompt_box_px=box_px,
        )

    def _resize(self, image: Image.Image) -> tuple[Image.Image, float, float]:
        longest = max(image.size)
        if longest <= self._max_side:
            return image, 1.0, 1.0
        scale = self._max_side / longest
        width = max(1, round(image.width * scale))
        height = max(1, round(image.height * scale))
        return (
            image.resize((width, height), Image.Resampling.BILINEAR),
            width / image.width,
            height / image.height,
        )


class LazyEfficientSamOnnxSegmenter:
    """App起動をModel設定に依存させず、最初のReal生成で明確にfail fastする。"""

    def __init__(self, model_path: Path | None, max_side: int) -> None:
        self._model_path = model_path
        self._max_side = max_side
        self._delegate: EfficientSamOnnxSegmenter | None = None

    def segment(self, image: Image.Image, box_px: BoxPx) -> SegmentationResult:
        if self._delegate is None:
            if self._model_path is None:
                raise AiNotConfiguredError("EFFICIENTSAM_MODEL_PATHが未設定です")
            self._delegate = EfficientSamOnnxSegmenter(self._model_path, self._max_side)
        return self._delegate.segment(image, box_px)
