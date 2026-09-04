"""EfficientSAM-Ti ONNXのbox-prompt adapter。RuntimeではWeightをdownloadしない。"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import onnxruntime as ort
from PIL import Image

from ai.errors import AiError, AiNotConfiguredError
from ai.image_ops import BoxPx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SegmentationTimings:
    """EfficientSAMの1 prompt attempt内訳。公開Responseには含めない。"""

    resize_elapsed_ms: float | None = None
    tensor_preparation_elapsed_ms: float | None = None
    onnx_inference_elapsed_ms: float | None = None
    encoder_inference_elapsed_ms: float | None = None
    decoder_inference_elapsed_ms: float | None = None
    mask_restore_elapsed_ms: float | None = None


@dataclass(frozen=True)
class PreparedSegmentationImage:
    """同一source photoで共有できるresize済みEfficientSAM入力。"""

    original_size: tuple[int, int]
    resized_size: tuple[int, int]
    scale_x: float
    scale_y: float
    input_image: np.ndarray
    timings: SegmentationTimings


@dataclass(frozen=True)
class SegmentationResult:
    mask: np.ndarray
    score: float | None
    prompt_box_px: BoxPx
    timings: SegmentationTimings = SegmentationTimings()


@dataclass(frozen=True)
class PreparedSplitSegmentationImage:
    """分離encoderが作った、request内で再利用可能なimage embedding。"""

    original_size: tuple[int, int]
    resized_size: tuple[int, int]
    scale_x: float
    scale_y: float
    image_embedding: np.ndarray
    timings: SegmentationTimings


class Segmenter(Protocol):
    def segment(self, image: Image.Image, box_px: BoxPx) -> SegmentationResult: ...

    def prepare(self, image: Image.Image) -> PreparedSegmentationImage: ...

    def segment_prepared(
        self, prepared: PreparedSegmentationImage, box_px: BoxPx
    ) -> SegmentationResult: ...


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
        prepared = self.prepare(image)
        result = self.segment_prepared(prepared, box_px)
        return SegmentationResult(
            mask=result.mask,
            score=result.score,
            prompt_box_px=result.prompt_box_px,
            timings=SegmentationTimings(
                resize_elapsed_ms=prepared.timings.resize_elapsed_ms,
                tensor_preparation_elapsed_ms=prepared.timings.tensor_preparation_elapsed_ms,
                onnx_inference_elapsed_ms=result.timings.onnx_inference_elapsed_ms,
                mask_restore_elapsed_ms=result.timings.mask_restore_elapsed_ms,
            ),
        )

    def prepare(self, image: Image.Image) -> PreparedSegmentationImage:
        resize_started = time.perf_counter()
        resized, scale_x, scale_y = self._resize(image)
        resize_elapsed_ms = _elapsed_ms(resize_started)

        tensor_started = time.perf_counter()
        input_image = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        return PreparedSegmentationImage(
            original_size=image.size,
            resized_size=resized.size,
            scale_x=scale_x,
            scale_y=scale_y,
            input_image=input_image,
            timings=SegmentationTimings(
                resize_elapsed_ms=resize_elapsed_ms,
                tensor_preparation_elapsed_ms=_elapsed_ms(tensor_started),
            ),
        )

    def segment_prepared(
        self, prepared: PreparedSegmentationImage, box_px: BoxPx
    ) -> SegmentationResult:
        x0, y0, x1, y1 = box_px
        points = np.array(
            [
                [
                    [
                        [x0 * prepared.scale_x, y0 * prepared.scale_y],
                        [x1 * prepared.scale_x, y1 * prepared.scale_y],
                    ]
                ]
            ],
            dtype=np.float32,
        )
        labels = np.array([[[2, 3]]], dtype=np.float32)
        inference_started = time.perf_counter()
        try:
            logits, predicted_iou, *_ = self._session.run(
                None,
                {
                    self._INPUT_IMAGE: prepared.input_image,
                    self._INPUT_POINTS: points,
                    self._INPUT_LABELS: labels,
                },
            )
        except Exception as exc:
            logger.info(
                "ai.performance stage=efficient_sam.onnx_inference elapsed_ms=%.1f outcome=error",
                _elapsed_ms(inference_started),
            )
            raise AiError("EfficientSAMの推論に失敗しました") from exc
        onnx_inference_elapsed_ms = _elapsed_ms(inference_started)

        restore_started = time.perf_counter()
        scores = np.asarray(predicted_iou)[0, 0]
        index = int(np.argmax(scores))
        mask = np.asarray(logits)[0, 0, index] >= 0
        if mask.shape != (prepared.resized_size[1], prepared.resized_size[0]):
            mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        else:
            mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        restored = mask_image.resize(prepared.original_size, Image.Resampling.NEAREST)
        return SegmentationResult(
            mask=np.asarray(restored, dtype=np.uint8) > 0,
            score=float(scores[index]),
            prompt_box_px=box_px,
            timings=SegmentationTimings(
                onnx_inference_elapsed_ms=onnx_inference_elapsed_ms,
                mask_restore_elapsed_ms=_elapsed_ms(restore_started),
            ),
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


class EfficientSamSplitOnnxSegmenter:
    """公式EfficientSAM-Tiの分離ONNXを使う、embedding再利用可能なadapter。"""

    _INPUT_IMAGE = "batched_images"
    _INPUT_EMBEDDINGS = "image_embeddings"
    _INPUT_POINTS = "batched_point_coords"
    _INPUT_LABELS = "batched_point_labels"
    _INPUT_ORIGINAL_SIZE = "orig_im_size"

    def __init__(self, encoder_model_path: Path, decoder_model_path: Path, max_side: int) -> None:
        if not encoder_model_path.is_file() or not decoder_model_path.is_file():
            raise AiNotConfiguredError(
                "EfficientSAM分離ONNX modelが見つかりません。設定を確認してください"
            )
        self._max_side = max_side
        try:
            self._encoder_session = ort.InferenceSession(
                str(encoder_model_path), providers=["CPUExecutionProvider"]
            )
            self._decoder_session = ort.InferenceSession(
                str(decoder_model_path), providers=["CPUExecutionProvider"]
            )
        except Exception as exc:
            raise AiNotConfiguredError("EfficientSAM分離ONNX modelをloadできません") from exc
        encoder_inputs = {item.name for item in self._encoder_session.get_inputs()}
        decoder_inputs = {item.name for item in self._decoder_session.get_inputs()}
        if (
            self._INPUT_IMAGE not in encoder_inputs
            or not {
                self._INPUT_EMBEDDINGS,
                self._INPUT_POINTS,
                self._INPUT_LABELS,
                self._INPUT_ORIGINAL_SIZE,
            }
            <= decoder_inputs
        ):
            raise AiNotConfiguredError("EfficientSAM分離ONNX modelの入力形式が一致しません")

    def segment(self, image: Image.Image, box_px: BoxPx) -> SegmentationResult:
        prepared = self.prepare(image)
        result = self.segment_prepared(prepared, box_px)
        return SegmentationResult(
            mask=result.mask,
            score=result.score,
            prompt_box_px=result.prompt_box_px,
            timings=SegmentationTimings(
                resize_elapsed_ms=prepared.timings.resize_elapsed_ms,
                tensor_preparation_elapsed_ms=prepared.timings.tensor_preparation_elapsed_ms,
                encoder_inference_elapsed_ms=prepared.timings.encoder_inference_elapsed_ms,
                decoder_inference_elapsed_ms=result.timings.decoder_inference_elapsed_ms,
                mask_restore_elapsed_ms=result.timings.mask_restore_elapsed_ms,
            ),
        )

    def prepare(self, image: Image.Image) -> PreparedSplitSegmentationImage:
        resize_started = time.perf_counter()
        resized, scale_x, scale_y = self._resize(image)
        resize_elapsed_ms = _elapsed_ms(resize_started)
        tensor_started = time.perf_counter()
        input_image = np.asarray(resized, dtype=np.float32).transpose(2, 0, 1)[None] / 255.0
        tensor_preparation_elapsed_ms = _elapsed_ms(tensor_started)
        encoder_started = time.perf_counter()
        try:
            image_embedding, *_ = self._encoder_session.run(None, {self._INPUT_IMAGE: input_image})
        except Exception as exc:
            logger.info(
                "ai.performance stage=efficient_sam.encoder_inference "
                "elapsed_ms=%.1f outcome=error",
                _elapsed_ms(encoder_started),
            )
            raise AiError("EfficientSAM encoderの推論に失敗しました") from exc
        return PreparedSplitSegmentationImage(
            original_size=image.size,
            resized_size=resized.size,
            scale_x=scale_x,
            scale_y=scale_y,
            image_embedding=np.asarray(image_embedding),
            timings=SegmentationTimings(
                resize_elapsed_ms=resize_elapsed_ms,
                tensor_preparation_elapsed_ms=tensor_preparation_elapsed_ms,
                encoder_inference_elapsed_ms=_elapsed_ms(encoder_started),
            ),
        )

    def segment_prepared(
        self, prepared: PreparedSplitSegmentationImage, box_px: BoxPx
    ) -> SegmentationResult:
        x0, y0, x1, y1 = box_px
        points = np.array(
            [
                [
                    [
                        [x0 * prepared.scale_x, y0 * prepared.scale_y],
                        [x1 * prepared.scale_x, y1 * prepared.scale_y],
                    ]
                ]
            ],
            dtype=np.float32,
        )
        labels = np.array([[[2, 3]]], dtype=np.float32)
        decoder_started = time.perf_counter()
        try:
            logits, predicted_iou, *_ = self._decoder_session.run(
                None,
                {
                    self._INPUT_EMBEDDINGS: prepared.image_embedding,
                    self._INPUT_POINTS: points,
                    self._INPUT_LABELS: labels,
                    self._INPUT_ORIGINAL_SIZE: np.array(
                        [prepared.resized_size[1], prepared.resized_size[0]], dtype=np.int64
                    ),
                },
            )
        except Exception as exc:
            logger.info(
                "ai.performance stage=efficient_sam.decoder_inference "
                "elapsed_ms=%.1f outcome=error",
                _elapsed_ms(decoder_started),
            )
            raise AiError("EfficientSAM decoderの推論に失敗しました") from exc

        restore_started = time.perf_counter()
        scores = np.asarray(predicted_iou)[0, 0]
        index = int(np.argmax(scores))
        mask = np.asarray(logits)[0, 0, index] >= 0
        mask_image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        restored = mask_image.resize(prepared.original_size, Image.Resampling.NEAREST)
        return SegmentationResult(
            mask=np.asarray(restored, dtype=np.uint8) > 0,
            score=float(scores[index]),
            prompt_box_px=box_px,
            timings=SegmentationTimings(
                decoder_inference_elapsed_ms=_elapsed_ms(decoder_started),
                mask_restore_elapsed_ms=_elapsed_ms(restore_started),
            ),
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
        return self._get_delegate().segment(image, box_px)

    def prepare(self, image: Image.Image) -> PreparedSegmentationImage:
        return self._get_delegate().prepare(image)

    def segment_prepared(
        self, prepared: PreparedSegmentationImage, box_px: BoxPx
    ) -> SegmentationResult:
        return self._get_delegate().segment_prepared(prepared, box_px)

    def _get_delegate(self) -> EfficientSamOnnxSegmenter:
        if self._delegate is None:
            if self._model_path is None:
                raise AiNotConfiguredError("EFFICIENTSAM_MODEL_PATHが未設定です")
            self._delegate = EfficientSamOnnxSegmenter(self._model_path, self._max_side)
        return self._delegate


class LazyEfficientSamSplitOnnxSegmenter:
    """分離ONNXを最初のReal生成までloadしないadapter。"""

    def __init__(
        self,
        encoder_model_path: Path | None,
        decoder_model_path: Path | None,
        max_side: int,
    ) -> None:
        self._encoder_model_path = encoder_model_path
        self._decoder_model_path = decoder_model_path
        self._max_side = max_side
        self._delegate: EfficientSamSplitOnnxSegmenter | None = None

    def segment(self, image: Image.Image, box_px: BoxPx) -> SegmentationResult:
        return self._get_delegate().segment(image, box_px)

    def prepare(self, image: Image.Image) -> PreparedSplitSegmentationImage:
        return self._get_delegate().prepare(image)

    def segment_prepared(
        self, prepared: PreparedSplitSegmentationImage, box_px: BoxPx
    ) -> SegmentationResult:
        return self._get_delegate().segment_prepared(prepared, box_px)

    def _get_delegate(self) -> EfficientSamSplitOnnxSegmenter:
        if self._delegate is None:
            if self._encoder_model_path is None or self._decoder_model_path is None:
                raise AiNotConfiguredError("EFFICIENTSAM分離ONNX model pathが未設定です")
            self._delegate = EfficientSamSplitOnnxSegmenter(
                self._encoder_model_path,
                self._decoder_model_path,
                self._max_side,
            )
        return self._delegate


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000
