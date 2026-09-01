"""Mock / Real Generator の選択。

`MOCK_AI=true` は**明示的に有効化する開発・デモ用Mode**。
Real処理が失敗したときに黙ってMockへ落ちる経路をここへ作らない（AGENTS.md §9・§11-12）。
"""

from __future__ import annotations

from ai.errors import AiNotConfiguredError
from ai.gemini import GeminiArtworkGenerator, GenerationObserver
from ai.quality import QualityPolicy
from ai.segmentation import LazyEfficientSamOnnxSegmenter
from ai.types import ArtworkGenerator
from app.config import Settings
from app.services.mock_generator import MockArtworkGenerator


def build_generator(
    settings: Settings,
    observer: GenerationObserver | None = None,
) -> ArtworkGenerator:
    if settings.mock_ai:
        return MockArtworkGenerator(settings.contracts_dir)
    if settings.segmentation_backend != "efficient_sam_onnx":
        raise AiNotConfiguredError("未対応のSEGMENTATION_BACKENDです")
    return GeminiArtworkGenerator(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        segmenter=LazyEfficientSamOnnxSegmenter(
            settings.efficientsam_model_path,
            settings.segmentation_max_side,
        ),
        candidate_count=settings.candidate_count,
        target_layer_min=settings.target_layer_min,
        target_layer_max=settings.target_layer_max,
        segmentation_max_retries=settings.segmentation_max_retries,
        analysis_max_side=settings.gemini_analysis_max_side,
        layer_padding_px=settings.layer_padding_px,
        layout_min_scale=settings.layout_min_scale,
        layout_max_scale=settings.layout_max_scale,
        canvas_aspect_ratio=settings.artwork_canvas_aspect_ratio,
        gemini_request_timeout_ms=settings.gemini_request_timeout_ms,
        semantic_profile=settings.semantic_profile,
        quality_policy=QualityPolicy(
            mode=settings.quality_gate_mode,
            max_component_count=settings.quality_max_component_count,
            min_largest_component_ratio=settings.quality_min_largest_component_ratio,
            min_bbox_coverage=settings.quality_min_bbox_coverage,
            reject_border_touch=settings.quality_reject_border_touch,
        ),
        quality_diagnostics_max_side=settings.quality_diagnostics_max_side,
        physical_scene_anchor_min_scale=settings.physical_scene_anchor_min_scale,
        physical_max_bottom_gap=settings.physical_max_bottom_gap,
        architecture_micro_island_max_area_ratio=settings.architecture_micro_island_max_area_ratio,
        mask_micro_island_max_area_ratio=settings.mask_micro_island_max_area_ratio,
        observer=observer,
    )
