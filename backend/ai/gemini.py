"""Gemini Structured OutputとEfficientSAMを結ぶReal Artwork Generator。"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from io import BytesIO
from typing import Any, Protocol
from uuid import uuid4

import numpy as np
from google import genai
from google.genai import types
from PIL import Image

from ai.assembly import (
    AcceptedLayer,
    SourcePhotoAsset,
    assemble_artwork,
    bottom_gaps,
    clamp_bottom_gaps,
    diagnose_composition_layers,
    diagnose_subject_overlaps,
    normalize_composition,
)
from ai.errors import AiError, AiNotConfiguredError, AiRateLimitedError, AiTimeoutError
from ai.image_ops import (
    close_narrow_mask_gaps,
    crop_to_rgba_png,
    decode_photo,
    expand_box,
    fill_closed_mask_holes,
    gemini_box_to_px,
    mask_to_rgba_png,
    thumbnail,
    union_masks,
)
from ai.internal_models import (
    CompositionPlan,
    SegmentationComponent,
    SemanticPlan,
    VisualElementCandidate,
)
from ai.quality import (
    MaskQuality,
    QualityPolicy,
    assess_mask,
    clean_micro_islands,
)
from ai.segmentation import SegmentationResult, Segmenter
from ai.types import AssetBlob, GenerationResult, InputPhoto

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CandidateMetric:
    candidate_id: str
    label: str
    segmentation_elapsed_ms: float
    layer_build_elapsed_ms: float
    mask_score: float | None
    mask_area_ratio: float | None
    success: bool
    failure_reason: str | None = None
    mask_component_count: int | None = None
    mask_largest_component_ratio: float | None = None
    mask_top_component_area_ratios: tuple[float, ...] | None = None
    mask_tail_component_area_ratio: float | None = None
    mask_interior_hole_count: int | None = None
    mask_interior_hole_area_ratio: float | None = None
    mask_diagnostics_analysis_scale: int | None = None
    mask_bbox_coverage: float | None = None
    mask_border_touch: bool | None = None
    coherent_group_required_component_count: int | None = None
    coherent_group_required_component_accepted_count: int | None = None
    coherent_group_component_exclusive_area_ratios: tuple[tuple[str, float], ...] | None = None
    candidate_kind: str = "subject"
    semantic_role: str | None = None
    layer_build_mode: str = "segmented_mask"
    mask_cleanup: str = "not_applicable"


@dataclass(frozen=True)
class PhysicalReadyDiagnostics:
    """physical_layer_v2専用のprivate PoC診断。公開Responseには含めない。"""

    scene_anchor_candidate_id: str | None
    background_missing: bool
    initial_bottom_gaps: tuple[tuple[str, float], ...]
    recomposed: bool
    final_bottom_gaps: tuple[tuple[str, float], ...]
    y_corrections: tuple[tuple[str, float], ...]
    subject_overlap_pairs: tuple[dict[str, object], ...] = ()
    composition_layers: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class GenerationMetrics:
    semantic_planning_elapsed_ms: float = 0
    composition_elapsed_ms: float = 0
    total_elapsed_ms: float = 0
    candidates: tuple[CandidateMetric, ...] = field(default_factory=tuple)
    physical_ready: PhysicalReadyDiagnostics | None = None


class SemanticPlanner(Protocol):
    async def plan(
        self, images: Sequence[Image.Image], memory_text: str | None
    ) -> SemanticPlan: ...


class Composer(Protocol):
    async def compose(self, layers: Sequence[AcceptedLayer]) -> CompositionPlan: ...

    async def recompose(
        self, layers: Sequence[AcceptedLayer], *, max_bottom_gap: float
    ) -> CompositionPlan: ...


class GenerationObserver(Protocol):
    """PoC用の任意observer。通常APIのGenerationResult境界へdebug情報を混ぜない。"""

    def semantic_plan(self, plan: SemanticPlan, images: Sequence[Image.Image]) -> None: ...

    def segmentation_attempt(
        self,
        *,
        candidate: VisualElementCandidate,
        component: SegmentationComponent,
        source_photo_index: int,
        image: Image.Image,
        result: SegmentationResult,
        quality: MaskQuality,
        attempt: int,
        stage: str = "normalized",
        normalization: dict[str, object] | None = None,
    ) -> None: ...


class GeminiSemanticPlanner:
    def __init__(
        self,
        client: genai.Client,
        model: str,
        analysis_max_side: int,
        request_timeout_ms: int,
        candidate_count: int = 12,
        target_layer_count: int = 4,
        semantic_profile: str = "baseline",
    ) -> None:
        self._client = client
        self._model = model
        self._analysis_max_side = analysis_max_side
        self._request_timeout_ms = request_timeout_ms
        self._candidate_count = candidate_count
        self._target_layer_count = target_layer_count
        self._semantic_profile = semantic_profile

    async def plan(self, images: Sequence[Image.Image], memory_text: str | None) -> SemanticPlan:
        photo_parts = [_image_part(thumbnail(image, self._analysis_max_side)) for image in images]
        prompt = (
            "You are planning a layered physical-memory artwork from a group of photos. "
            "Study every photo together and treat the memory text as a primary signal "
            "when present. "
            f"Return {self._candidate_count} distinct candidates so the pipeline can produce "
            f"exactly {self._target_layer_count} strong final layers. "
            "Each candidate must identify source_photo_index (zero based), have components, "
            "and give every "
            "component a tight complete bbox in 0..1000 coordinates as y_min, x_min, y_max, x_max. "
            "Choose meaningful memories, not merely easy-to-segment objects. "
            "Avoid duplicate meanings. "
            "The P0 asset pipeline uses binary alpha masks. When equally meaningful opaque "
            "alternatives exist, do not prioritize transparent, reflective, smoky, or water-spray "
            "subjects whose visible pixels contain background scenery. "
            "Multiple components are allowed only when they should be one visual layer. "
            + _semantic_profile_instruction(self._semantic_profile)
            + "Do not include commentary outside the schema."
        )
        if memory_text:
            prompt += f"\nMemory text: {memory_text}"
        response = await _generate_structured(
            self._client,
            self._model,
            [prompt, *photo_parts],
            SemanticPlan,
            _semantic_plan_schema(
                require_semantic_role=self._semantic_profile == "physical_layer_v3_architecture",
                require_extraction_plan=self._semantic_profile == "coherent_group_planning",
            ),
            self._request_timeout_ms,
        )
        return SemanticPlan.model_validate(response)


class GeminiComposer:
    def __init__(
        self,
        client: genai.Client,
        model: str,
        request_timeout_ms: int,
        canvas_aspect_ratio: float,
        composition_overlap_instruction_enabled: bool = False,
        composition_foreground_bottom_instruction_enabled: bool = True,
    ) -> None:
        self._client = client
        self._model = model
        self._request_timeout_ms = request_timeout_ms
        self._canvas_aspect_ratio = canvas_aspect_ratio
        self._composition_overlap_instruction_enabled = composition_overlap_instruction_enabled
        self._composition_foreground_bottom_instruction_enabled = (
            composition_foreground_bottom_instruction_enabled
        )

    async def compose(self, layers: Sequence[AcceptedLayer]) -> CompositionPlan:
        return await self._compose(layers, max_bottom_gap=None)

    async def recompose(
        self, layers: Sequence[AcceptedLayer], *, max_bottom_gap: float
    ) -> CompositionPlan:
        return await self._compose(layers, max_bottom_gap=max_bottom_gap)

    async def _compose(
        self, layers: Sequence[AcceptedLayer], *, max_bottom_gap: float | None
    ) -> CompositionPlan:
        parts: list[object] = [
            "Create an initial composition for supplied transparent artwork layers. "
            f"The landscape canvas width/height ratio is {self._canvas_aspect_ratio:.9f}. "
            "Return exactly one placement for every candidate_id. x and y are centers in 0..1; "
            "scale is layer width divided by canvas width; order is back-to-front. "
            "Compose a balanced keepsake, not literal scene depth. "
            + (
                "Keep foreground subject layers visually distinct: "
                "avoid excessive overlap that hides "
                "a substantial part of one subject behind another. A scene anchor may sit behind "
                "foreground subjects, but do not use foreground-overlap merely to fill the canvas. "
                if self._composition_overlap_instruction_enabled
                else ""
            )
            + (
                "Use vertical depth as a gentle compositional cue: when appropriate, "
                "place subjects intended for the front lower in the canvas than background "
                "or middle-depth subjects. Preserve each subject's visual identity, keep every "
                "layer within the canvas, and treat this as a preference rather than a hard rule. "
                if self._composition_foreground_bottom_instruction_enabled
                else ""
            )
            + "Do not add commentary outside the schema.\n\nLayers:"
        ]
        if max_bottom_gap is not None:
            parts.append(
                "This is a constrained recomposition. For every layer, calculate its displayed "
                f"lower edge from its aspect ratio and keep it no more than {max_bottom_gap:.2f} "
                "of the canvas height above the canvas bottom. Recompose all layers together."
            )
        for layer in layers:
            parts.append(
                f"candidate_id={layer.candidate_id}; label={layer.label}; "
                f"kind={layer.kind}; importance={layer.importance:.3f}; "
                f"width_px={layer.asset.width_px}; "
                f"height_px={layer.asset.height_px}"
            )
            parts.append(_image_part(_asset_thumbnail(layer.asset)))
        response = await _generate_structured(
            self._client,
            self._model,
            parts,
            CompositionPlan,
            _composition_schema(),
            self._request_timeout_ms,
        )
        return CompositionPlan.model_validate(response)


class GeminiArtworkGenerator:
    """Real P0 pipeline。テストではplanner/composer/segmenterをFakeへ差し替えられる。"""

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        segmenter: Segmenter,
        candidate_count: int,
        target_layer_min: int,
        target_layer_max: int,
        segmentation_max_retries: int,
        analysis_max_side: int,
        layer_padding_px: int,
        layout_min_scale: float,
        layout_max_scale: float,
        canvas_aspect_ratio: float,
        gemini_request_timeout_ms: int,
        semantic_profile: str = "baseline",
        quality_policy: QualityPolicy | None = None,
        quality_diagnostics_max_side: int = 1024,
        physical_scene_anchor_min_scale: float = 0.60,
        physical_max_bottom_gap: float = 0.30,
        architecture_micro_island_max_area_ratio: float = 0.001,
        mask_micro_island_max_area_ratio: float = 0.005,
        closed_hole_fill_enabled: bool = False,
        micro_island_cleanup_enabled: bool = False,
        composition_overlap_instruction_enabled: bool = False,
        composition_foreground_bottom_instruction_enabled: bool = True,
        coherent_group_gap_closure_px: int = 0,
        subject_overlap_diagnostics: bool = False,
        semantic_planner: SemanticPlanner | None = None,
        composer: Composer | None = None,
        observer: GenerationObserver | None = None,
    ) -> None:
        if target_layer_min < 1 or target_layer_max < target_layer_min:
            raise AiNotConfiguredError("Target Layer数の設定が不正です")
        if candidate_count < target_layer_min:
            raise AiNotConfiguredError("Candidate数がTarget Layer数より少ない設定です")
        if quality_diagnostics_max_side < 1:
            raise AiNotConfiguredError("Quality診断の最大辺が不正です")
        if not 0 < physical_scene_anchor_min_scale <= 1:
            raise AiNotConfiguredError("背景Layerの最小表示幅設定が不正です")
        if not 0 <= physical_max_bottom_gap <= 1:
            raise AiNotConfiguredError("Layer浮遊量の設定が不正です")
        if not 0 <= architecture_micro_island_max_area_ratio <= 1:
            raise AiNotConfiguredError("建造物Maskの微小孤立成分設定が不正です")
        if not 0 <= mask_micro_island_max_area_ratio <= 1:
            raise AiNotConfiguredError("Maskの微小孤立成分設定が不正です")
        if coherent_group_gap_closure_px < 0:
            raise AiNotConfiguredError("coherent_groupのgap閉鎖設定が不正です")
        self._segmenter = segmenter
        self._candidate_count = candidate_count
        self._target_layer_min = target_layer_min
        self._target_layer_max = target_layer_max
        self._segmentation_max_retries = segmentation_max_retries
        self._layer_padding_px = layer_padding_px
        self._layout_min_scale = layout_min_scale
        self._layout_max_scale = layout_max_scale
        self._canvas_aspect_ratio = canvas_aspect_ratio
        self._quality_policy = quality_policy or QualityPolicy()
        self._quality_diagnostics_max_side = quality_diagnostics_max_side
        self._semantic_profile = semantic_profile
        self._physical_ready = semantic_profile in {
            "physical_layer_v2",
            "physical_layer_v3_architecture",
        }
        self._architecture_ready = semantic_profile == "physical_layer_v3_architecture"
        self._physical_scene_anchor_min_scale = physical_scene_anchor_min_scale
        self._physical_max_bottom_gap = physical_max_bottom_gap
        self._architecture_micro_island_max_area_ratio = architecture_micro_island_max_area_ratio
        self._mask_micro_island_max_area_ratio = mask_micro_island_max_area_ratio
        self._closed_hole_fill_enabled = closed_hole_fill_enabled
        self._micro_island_cleanup_enabled = micro_island_cleanup_enabled
        self._composition_overlap_instruction_enabled = composition_overlap_instruction_enabled
        self._composition_foreground_bottom_instruction_enabled = (
            composition_foreground_bottom_instruction_enabled
        )
        self._coherent_group_gap_closure_px = coherent_group_gap_closure_px
        self._subject_overlap_diagnostics = subject_overlap_diagnostics
        self._observer = observer
        self._api_key = api_key
        self._model = model
        if semantic_planner is None or composer is None:
            if not api_key or not model:
                # App起動ではなくReal request開始時に明確な設定Errorへする。
                self._planner = None
                self._composer = None
            else:
                client = genai.Client(api_key=api_key)
                self._planner = semantic_planner or GeminiSemanticPlanner(
                    client,
                    model,
                    analysis_max_side,
                    gemini_request_timeout_ms,
                    candidate_count,
                    target_layer_max,
                    semantic_profile,
                )
                self._composer = composer or GeminiComposer(
                    client,
                    model,
                    gemini_request_timeout_ms,
                    canvas_aspect_ratio,
                    composition_overlap_instruction_enabled,
                    composition_foreground_bottom_instruction_enabled,
                )
        else:
            self._planner = semantic_planner
            self._composer = composer
        self.last_metrics = GenerationMetrics()

    async def generate(
        self, photos: Sequence[InputPhoto], memory_text: str | None
    ) -> GenerationResult:
        if not photos:
            raise AiError("入力写真がありません")
        if self._planner is None or self._composer is None:
            missing = [
                name
                for name, value in (
                    ("GEMINI_API_KEY", self._api_key),
                    ("GEMINI_MODEL", self._model),
                )
                if not value
            ]
            raise AiNotConfiguredError(f"未設定の環境変数: {', '.join(missing)}")
        started = time.perf_counter()
        decoded = [decode_photo(photo) for photo in photos]
        source_assets = _build_source_assets(decoded)

        semantic_started = time.perf_counter()
        try:
            semantic_plan = await self._planner.plan([item.image for item in decoded], memory_text)
        except AiError:
            self.last_metrics = GenerationMetrics(
                semantic_planning_elapsed_ms=_elapsed_ms(semantic_started),
                total_elapsed_ms=_elapsed_ms(started),
            )
            raise
        semantic_elapsed_ms = _elapsed_ms(semantic_started)
        if self._observer is not None:
            self._observer.semantic_plan(semantic_plan, [item.image for item in decoded])
        logger.info(
            "ai.semantic_plan elapsed_ms=%.1f candidates=%d",
            semantic_elapsed_ms,
            len(semantic_plan.candidates),
        )

        usable_layers: list[AcceptedLayer] = []
        candidate_metrics: list[CandidateMetric] = []
        candidates = sorted(
            semantic_plan.candidates, key=lambda item: item.importance, reverse=True
        )
        seen_candidate_ids: set[str] = set()
        prepared_images: dict[int, object] = {}
        for candidate in candidates[: self._candidate_count]:
            if candidate.candidate_id in seen_candidate_ids:
                candidate_metrics.append(
                    CandidateMetric(
                        candidate.candidate_id,
                        candidate.label,
                        0,
                        0,
                        None,
                        None,
                        False,
                        "duplicate_candidate_id",
                        candidate_kind=candidate.kind,
                    )
                )
                continue
            seen_candidate_ids.add(candidate.candidate_id)
            if candidate.source_photo_index >= len(decoded):
                candidate_metrics.append(
                    CandidateMetric(
                        candidate.candidate_id,
                        candidate.label,
                        0,
                        0,
                        None,
                        None,
                        False,
                        "source_photo_out_of_range",
                        candidate_kind=candidate.kind,
                    )
                )
                continue
            image = decoded[candidate.source_photo_index].image
            prepared_image = await self._prepare_source_image(
                candidate.source_photo_index,
                image,
                prepared_images,
            )
            layer, metric = await self._build_candidate(
                candidate,
                image,
                prepared_image=prepared_image,
            )
            candidate_metrics.append(metric)
            if layer is not None:
                usable_layers.append(layer)

        architecture_primary_planned = self._architecture_ready and any(
            candidate.semantic_role == "architecture_primary"
            for candidate in semantic_plan.candidates
        )
        accepted, scene_anchor_candidate_id = self._select_layers(usable_layers)

        if len(accepted) < self._target_layer_min or (
            architecture_primary_planned
            and not any(layer.semantic_role == "architecture_primary" for layer in accepted)
        ):
            self.last_metrics = GenerationMetrics(
                semantic_planning_elapsed_ms=semantic_elapsed_ms,
                total_elapsed_ms=_elapsed_ms(started),
                candidates=tuple(candidate_metrics),
            )
            raise AiError("品質基準を満たすLayerを十分に生成できませんでした")

        composition_started = time.perf_counter()
        composition_plan = await self._composer.compose(accepted)
        layout = normalize_composition(
            accepted,
            composition_plan,
            canvas_aspect_ratio=self._canvas_aspect_ratio,
            min_scale=self._layout_min_scale,
            max_scale=self._layout_max_scale,
            minimum_scales=(
                {scene_anchor_candidate_id: self._physical_scene_anchor_min_scale}
                if scene_anchor_candidate_id is not None
                else None
            ),
        )
        initial_gaps = (
            bottom_gaps(accepted, layout, canvas_aspect_ratio=self._canvas_aspect_ratio)
            if self._physical_ready
            else {}
        )
        recomposed = False
        corrections: dict[str, float] = {}
        if self._physical_ready and any(
            gap > self._physical_max_bottom_gap for gap in initial_gaps.values()
        ):
            recomposed = True
            recompose = getattr(self._composer, "recompose", None)
            constrained_plan = (
                await recompose(accepted, max_bottom_gap=self._physical_max_bottom_gap)
                if callable(recompose)
                else await self._composer.compose(accepted)
            )
            layout = normalize_composition(
                accepted,
                constrained_plan,
                canvas_aspect_ratio=self._canvas_aspect_ratio,
                min_scale=self._layout_min_scale,
                max_scale=self._layout_max_scale,
                minimum_scales=(
                    {scene_anchor_candidate_id: self._physical_scene_anchor_min_scale}
                    if scene_anchor_candidate_id is not None
                    else None
                ),
            )
            if any(
                gap > self._physical_max_bottom_gap
                for gap in bottom_gaps(
                    accepted, layout, canvas_aspect_ratio=self._canvas_aspect_ratio
                ).values()
            ):
                layout, corrections = clamp_bottom_gaps(
                    accepted,
                    layout,
                    canvas_aspect_ratio=self._canvas_aspect_ratio,
                    max_bottom_gap=self._physical_max_bottom_gap,
                )
        composition_elapsed_ms = _elapsed_ms(composition_started)
        physical_ready = (
            PhysicalReadyDiagnostics(
                scene_anchor_candidate_id=scene_anchor_candidate_id,
                background_missing=scene_anchor_candidate_id is None,
                initial_bottom_gaps=tuple(sorted(initial_gaps.items())),
                recomposed=recomposed,
                final_bottom_gaps=tuple(
                    sorted(
                        bottom_gaps(
                            accepted,
                            layout,
                            canvas_aspect_ratio=self._canvas_aspect_ratio,
                        ).items()
                    )
                ),
                y_corrections=tuple(sorted(corrections.items())),
                subject_overlap_pairs=(
                    tuple(
                        diagnostic.__dict__
                        for diagnostic in diagnose_subject_overlaps(
                            accepted,
                            layout,
                            canvas_aspect_ratio=self._canvas_aspect_ratio,
                        )
                    )
                    if self._subject_overlap_diagnostics
                    else ()
                ),
                composition_layers=tuple(
                    diagnostic.__dict__
                    for diagnostic in diagnose_composition_layers(
                        accepted,
                        layout,
                        canvas_aspect_ratio=self._canvas_aspect_ratio,
                    )
                ),
            )
            if self._physical_ready
            else None
        )
        self._notify_composition(accepted, physical_ready)
        artwork = assemble_artwork(
            source_assets,
            accepted,
            layout,
            canvas_aspect_ratio=self._canvas_aspect_ratio,
        )
        self.last_metrics = GenerationMetrics(
            semantic_planning_elapsed_ms=semantic_elapsed_ms,
            composition_elapsed_ms=composition_elapsed_ms,
            total_elapsed_ms=_elapsed_ms(started),
            candidates=tuple(candidate_metrics),
            physical_ready=physical_ready,
        )
        logger.info(
            "ai.composition elapsed_ms=%.1f ai.total elapsed_ms=%.1f layers=%d",
            composition_elapsed_ms,
            self.last_metrics.total_elapsed_ms,
            len(accepted),
        )
        return GenerationResult(
            artwork=artwork,
            assets=tuple(
                [*(item.asset for item in source_assets), *(item.asset for item in accepted)]
            ),
        )

    def _select_layers(
        self, usable_layers: list[AcceptedLayer]
    ) -> tuple[list[AcceptedLayer], str | None]:
        """scene anchorは最大1件だけ優先し、残りをsubjectで満たす。"""

        if not self._physical_ready:
            return usable_layers[: self._target_layer_max], None
        anchors = sorted(
            (layer for layer in usable_layers if layer.kind == "scene_anchor"),
            key=lambda layer: layer.importance,
            reverse=True,
        )
        subjects = sorted(
            (layer for layer in usable_layers if layer.kind != "scene_anchor"),
            key=lambda layer: layer.importance,
            reverse=True,
        )
        selected: list[AcceptedLayer] = []
        anchor_id: str | None = None
        if anchors:
            selected.append(anchors[0])
            anchor_id = anchors[0].candidate_id
        primaries = [layer for layer in subjects if layer.semantic_role == "architecture_primary"]
        if self._architecture_ready and primaries:
            selected.append(primaries[0])
        remaining_subjects = [layer for layer in subjects if layer not in selected]
        selected.extend(remaining_subjects[: self._target_layer_max - len(selected)])
        return selected, anchor_id

    def _notify_composition(
        self,
        accepted: Sequence[AcceptedLayer],
        diagnostics: PhysicalReadyDiagnostics | None,
    ) -> None:
        if self._observer is None:
            return
        callback = getattr(self._observer, "composition_result", None)
        if callable(callback):
            callback(accepted=accepted, diagnostics=diagnostics)

    async def _prepare_source_image(
        self,
        source_photo_index: int,
        image: Image.Image,
        prepared_images: dict[int, object],
    ) -> object | None:
        if source_photo_index in prepared_images:
            return prepared_images[source_photo_index]
        prepare = getattr(self._segmenter, "prepare", None)
        segment_prepared = getattr(self._segmenter, "segment_prepared", None)
        if not callable(prepare) or not callable(segment_prepared):
            return None
        prepared = await asyncio.to_thread(prepare, image)
        prepared_images[source_photo_index] = prepared
        return prepared

    def _segment(
        self,
        image: Image.Image,
        box_px,
        prepared_image: object | None,
    ) -> SegmentationResult:
        if prepared_image is not None:
            segment_prepared = getattr(self._segmenter, "segment_prepared", None)
            if callable(segment_prepared):
                return segment_prepared(prepared_image, box_px)
        return self._segmenter.segment(image, box_px)

    async def _build_candidate(
        self, candidate, image: Image.Image, *, prepared_image: object | None = None
    ) -> tuple[AcceptedLayer | None, CandidateMetric]:
        if self._physical_ready and candidate.kind == "scene_anchor":
            return self._build_scene_anchor(candidate, image)
        segmentation_started = time.perf_counter()
        masks = []
        accepted_components = []
        scores: list[float] = []
        component_qualities: list[MaskQuality] = []
        diagnostics_max_side = (
            self._quality_diagnostics_max_side
            if (
                self._physical_ready
                or self._observer is not None
                or self._quality_policy.diagnostics_required
            )
            else None
        )
        for component in candidate.components:
            prompt_box = gemini_box_to_px(component.box_2d, image.size)
            result = None
            quality: MaskQuality | None = None
            for attempt in range(self._segmentation_max_retries + 1):
                current_box = prompt_box if attempt == 0 else expand_box(prompt_box, image.size)
                raw_result = await asyncio.to_thread(
                    self._segment,
                    image,
                    current_box,
                    prepared_image,
                )
                raw_quality = assess_mask(
                    raw_result.mask,
                    current_box,
                    raw_result.score,
                    diagnostics_max_side=diagnostics_max_side,
                )
                if self._observer is not None:
                    self._observer.segmentation_attempt(
                        candidate=candidate,
                        component=component,
                        source_photo_index=candidate.source_photo_index,
                        image=image,
                        result=raw_result,
                        quality=raw_quality,
                        attempt=attempt,
                        stage="raw",
                    )
                normalized_mask = raw_result.mask
                normalization: dict[str, object] = {
                    "closedHoleFillEnabled": self._closed_hole_fill_enabled,
                    "closedHoleFillAddedPixels": 0,
                }
                if self._closed_hole_fill_enabled:
                    normalized_mask = fill_closed_mask_holes(raw_result.mask)
                    normalization["closedHoleFillAddedPixels"] = int(
                        np.count_nonzero(normalized_mask & ~raw_result.mask)
                    )
                result = SegmentationResult(
                    mask=normalized_mask,
                    score=raw_result.score,
                    prompt_box_px=raw_result.prompt_box_px,
                )
                quality = assess_mask(
                    result.mask,
                    current_box,
                    result.score,
                    diagnostics_max_side=diagnostics_max_side,
                )
                if self._observer is not None:
                    self._observer.segmentation_attempt(
                        candidate=candidate,
                        component=component,
                        source_photo_index=candidate.source_photo_index,
                        image=image,
                        result=result,
                        quality=quality,
                        attempt=attempt,
                        stage="normalized",
                        normalization=normalization,
                    )
                logger.info(
                    "ai.segmentation candidate=%s component=%s elapsed_ms=%.1f score=%s "
                    "area_ratio=%.5f accepted=%s",
                    candidate.candidate_id,
                    component.component_id,
                    _elapsed_ms(segmentation_started),
                    result.score,
                    quality.area_ratio,
                    quality.accepted,
                )
                if quality.accepted:
                    break
            if quality is None or result is None or not quality.accepted:
                if component.required:
                    return None, CandidateMetric(
                        candidate.candidate_id,
                        candidate.label,
                        _elapsed_ms(segmentation_started),
                        0,
                        result.score if result else None,
                        quality.area_ratio if quality else None,
                        False,
                        quality.reason if quality else "segmentation_failed",
                    )
                continue
            masks.append(result.mask)
            accepted_components.append(component)
            component_qualities.append(quality)
            if result.score is not None:
                scores.append(result.score)

        if not masks:
            return None, CandidateMetric(
                candidate.candidate_id,
                candidate.label,
                _elapsed_ms(segmentation_started),
                0,
                None,
                None,
                False,
                "no_accepted_components",
            )
        combined_mask = union_masks(masks)
        is_coherent_group = candidate.extraction_intent == "coherent_group"
        coherent_group_metrics = (
            _coherent_group_component_metrics(candidate, accepted_components, masks)
            if is_coherent_group
            else None
        )
        if self._closed_hole_fill_enabled:
            # component単位では開いていた領域が、union後に閉じることがある。
            # その場合も窓・開口部と同じく、外部とつながらない穴として埋める。
            combined_mask = fill_closed_mask_holes(combined_mask)
        if is_coherent_group and self._coherent_group_gap_closure_px:
            combined_mask = close_narrow_mask_gaps(
                combined_mask,
                max_gap_px=self._coherent_group_gap_closure_px,
            )
            if self._closed_hole_fill_enabled:
                # closingが外部へ通じる細い通路を閉じると、新しい閉鎖穴が生じ得る。
                # 最終Layerの穴を残さないため、形状変更後にも同じ規則を適用する。
                combined_mask = fill_closed_mask_holes(combined_mask)
        combined_quality = assess_mask(
            combined_mask,
            (0, 0, image.width, image.height),
            max(scores) if scores else None,
            diagnostics_max_side=diagnostics_max_side,
        )
        cleanup_limit = self._mask_micro_island_max_area_ratio
        if self._architecture_ready and candidate.semantic_role in {
            "architecture_primary",
            "architecture_detail",
        }:
            cleanup_limit = self._architecture_micro_island_max_area_ratio
        mask_cleanup = "not_needed"
        if self._micro_island_cleanup_enabled and self._physical_ready and not is_coherent_group:
            cleanup = clean_micro_islands(
                combined_mask,
                max_removed_area_ratio=cleanup_limit,
            )
            if cleanup.component_count > 1 and not cleanup.applied:
                return None, _candidate_metric(
                    candidate,
                    segmentation_elapsed_ms=_elapsed_ms(segmentation_started),
                    layer_build_elapsed_ms=0,
                    quality=combined_quality,
                    success=False,
                    failure_reason="not_single_component",
                    bbox_coverage=min(item.bbox_coverage for item in component_qualities),
                    border_touch=any(item.border_touch for item in component_qualities),
                    mask_cleanup=f"rejected_detached:{cleanup.removed_area_ratio:.6f}",
                )
            if cleanup.applied:
                combined_mask = cleanup.mask
                combined_quality = assess_mask(
                    combined_mask,
                    (0, 0, image.width, image.height),
                    max(scores) if scores else None,
                    diagnostics_max_side=diagnostics_max_side,
                )
                mask_cleanup = f"removed_micro_islands:{cleanup.removed_area_ratio:.6f}"
            elif cleanup.component_count == 1:
                mask_cleanup = "already_single_component"
        elif self._physical_ready:
            # coherent_groupで指定されたrequired componentは、離れていても意味を構成する。
            # 微小island cleanupで付属物を削除したり、橋を描いて連結したりはしない。
            mask_cleanup = (
                f"closed_narrow_gaps:{self._coherent_group_gap_closure_px};"
                f"retained_coherent_group:{len(masks)}"
                if self._coherent_group_gap_closure_px
                else f"retained_coherent_group:{len(masks)}"
            )
        if (
            self._physical_ready
            and not is_coherent_group
            and combined_quality.diagnostics is not None
            and combined_quality.diagnostics.component_count != 1
        ):
            return None, _candidate_metric(
                candidate,
                segmentation_elapsed_ms=_elapsed_ms(segmentation_started),
                layer_build_elapsed_ms=0,
                quality=combined_quality,
                success=False,
                failure_reason="not_single_component",
                bbox_coverage=min(item.bbox_coverage for item in component_qualities),
                border_touch=any(item.border_touch for item in component_qualities),
                mask_cleanup=mask_cleanup,
            )
        rejection_reason = self._quality_policy.rejection_reason(
            combined_quality.diagnostics,
            bbox_coverage=min(item.bbox_coverage for item in component_qualities),
            border_touch=any(item.border_touch for item in component_qualities),
            expected_multiple_components=is_coherent_group,
        )
        if rejection_reason is not None:
            return None, _candidate_metric(
                candidate,
                segmentation_elapsed_ms=_elapsed_ms(segmentation_started),
                layer_build_elapsed_ms=0,
                quality=combined_quality,
                success=False,
                failure_reason=rejection_reason,
                bbox_coverage=min(item.bbox_coverage for item in component_qualities),
                border_touch=any(item.border_touch for item in component_qualities),
            )

        layer_started = time.perf_counter()
        png, width, height = mask_to_rgba_png(
            image, combined_mask, padding_px=self._layer_padding_px
        )
        asset = AssetBlob(
            asset_id=f"layer-{uuid4().hex}",
            mime_type="image/png",
            width_px=width,
            height_px=height,
            data=png,
        )
        return (
            AcceptedLayer(
                candidate_id=candidate.candidate_id,
                label=candidate.label,
                source_photo_index=candidate.source_photo_index,
                source_layer_id=(
                    f"source-layer-{hashlib.sha256(candidate.candidate_id.encode()).hexdigest()[:16]}"
                ),
                asset=asset,
                importance=candidate.importance,
                kind=candidate.kind,
                semantic_role=candidate.semantic_role,
            ),
            _candidate_metric(
                candidate,
                segmentation_elapsed_ms=_elapsed_ms(segmentation_started),
                layer_build_elapsed_ms=_elapsed_ms(layer_started),
                quality=combined_quality,
                success=True,
                failure_reason=None,
                bbox_coverage=min(item.bbox_coverage for item in component_qualities),
                border_touch=any(item.border_touch for item in component_qualities),
                mask_cleanup=mask_cleanup,
                coherent_group_metrics=coherent_group_metrics,
            ),
        )

    def _build_scene_anchor(
        self, candidate: VisualElementCandidate, image: Image.Image
    ) -> tuple[AcceptedLayer | None, CandidateMetric]:
        """背景として機能する範囲を、分割せず矩形CropでLayer化する。"""

        started = time.perf_counter()
        if len(candidate.components) != 1:
            return None, CandidateMetric(
                candidate.candidate_id,
                candidate.label,
                0,
                0,
                None,
                None,
                False,
                "scene_anchor_requires_single_bbox",
                candidate_kind=candidate.kind,
                layer_build_mode="rectangular_crop",
            )
        component = candidate.components[0]
        box = gemini_box_to_px(component.box_2d, image.size)
        x0, y0, x1, y1 = box
        mask = np.zeros((image.height, image.width), dtype=bool)
        mask[y0:y1, x0:x1] = True
        quality = assess_mask(
            mask,
            box,
            None,
            diagnostics_max_side=self._quality_diagnostics_max_side,
        )
        if self._observer is not None:
            self._observer.segmentation_attempt(
                candidate=candidate,
                component=component,
                source_photo_index=candidate.source_photo_index,
                image=image,
                result=SegmentationResult(mask=mask, score=None, prompt_box_px=box),
                quality=quality,
                attempt=0,
            )
        fit_scale = min(
            1.0,
            (x1 - x0) / (self._canvas_aspect_ratio * (y1 - y0)),
        )
        if min(self._layout_max_scale, fit_scale) < self._physical_scene_anchor_min_scale:
            return None, _candidate_metric(
                candidate,
                segmentation_elapsed_ms=_elapsed_ms(started),
                layer_build_elapsed_ms=0,
                quality=quality,
                success=False,
                failure_reason="scene_anchor_too_tall_for_minimum_width",
                bbox_coverage=quality.bbox_coverage,
                border_touch=quality.border_touch,
                layer_build_mode="rectangular_crop",
            )
        layer_started = time.perf_counter()
        png, width, height = crop_to_rgba_png(image, box)
        asset = AssetBlob(
            asset_id=f"layer-{uuid4().hex}",
            mime_type="image/png",
            width_px=width,
            height_px=height,
            data=png,
        )
        return (
            AcceptedLayer(
                candidate_id=candidate.candidate_id,
                label=candidate.label,
                source_photo_index=candidate.source_photo_index,
                source_layer_id=(
                    f"source-layer-{hashlib.sha256(candidate.candidate_id.encode()).hexdigest()[:16]}"
                ),
                asset=asset,
                importance=candidate.importance,
                kind=candidate.kind,
                semantic_role=candidate.semantic_role,
            ),
            _candidate_metric(
                candidate,
                segmentation_elapsed_ms=_elapsed_ms(started),
                layer_build_elapsed_ms=_elapsed_ms(layer_started),
                quality=quality,
                success=True,
                failure_reason=None,
                bbox_coverage=quality.bbox_coverage,
                border_touch=quality.border_touch,
                layer_build_mode="rectangular_crop",
            ),
        )


def _candidate_metric(
    candidate: VisualElementCandidate,
    *,
    segmentation_elapsed_ms: float,
    layer_build_elapsed_ms: float,
    quality: MaskQuality,
    success: bool,
    failure_reason: str | None,
    bbox_coverage: float,
    border_touch: bool,
    layer_build_mode: str = "segmented_mask",
    mask_cleanup: str = "not_applicable",
    coherent_group_metrics: tuple[int, int, tuple[tuple[str, float], ...]] | None = None,
) -> CandidateMetric:
    diagnostics = quality.diagnostics
    return CandidateMetric(
        candidate.candidate_id,
        candidate.label,
        segmentation_elapsed_ms,
        layer_build_elapsed_ms,
        quality.score,
        quality.area_ratio,
        success,
        failure_reason,
        mask_component_count=diagnostics.component_count if diagnostics else None,
        mask_largest_component_ratio=diagnostics.largest_component_ratio if diagnostics else None,
        mask_top_component_area_ratios=(
            diagnostics.top_component_area_ratios if diagnostics else None
        ),
        mask_tail_component_area_ratio=(
            diagnostics.tail_component_area_ratio if diagnostics else None
        ),
        mask_interior_hole_count=diagnostics.interior_hole_count if diagnostics else None,
        mask_interior_hole_area_ratio=(
            diagnostics.interior_hole_area_ratio if diagnostics else None
        ),
        mask_diagnostics_analysis_scale=diagnostics.analysis_scale if diagnostics else None,
        mask_bbox_coverage=bbox_coverage,
        mask_border_touch=border_touch,
        coherent_group_required_component_count=(
            coherent_group_metrics[0] if coherent_group_metrics else None
        ),
        coherent_group_required_component_accepted_count=(
            coherent_group_metrics[1] if coherent_group_metrics else None
        ),
        coherent_group_component_exclusive_area_ratios=(
            coherent_group_metrics[2] if coherent_group_metrics else None
        ),
        candidate_kind=candidate.kind,
        semantic_role=candidate.semantic_role,
        layer_build_mode=layer_build_mode,
        mask_cleanup=mask_cleanup,
    )


def _coherent_group_component_metrics(
    candidate: VisualElementCandidate,
    accepted_components: list[SegmentationComponent],
    masks: list[np.ndarray],
) -> tuple[int, int, tuple[tuple[str, float], ...]]:
    """component別Maskのunionへの寄与をprivate metricsとして残す。"""

    combined = union_masks(masks)
    combined_area = int(combined.sum())
    exclusive_ratios: list[tuple[str, float]] = []
    for index, (component, mask) in enumerate(zip(accepted_components, masks, strict=True)):
        other_masks = [item for other_index, item in enumerate(masks) if other_index != index]
        other_union = union_masks(other_masks) if other_masks else np.zeros_like(mask)
        exclusive_area = int(np.logical_and(mask, np.logical_not(other_union)).sum())
        exclusive_ratios.append((component.component_id, exclusive_area / combined_area))
    return (
        sum(component.required for component in candidate.components),
        sum(component.required for component in accepted_components),
        tuple(exclusive_ratios),
    )


def _semantic_profile_instruction(profile: str) -> str:
    if profile == "baseline":
        return ""
    if profile == "physical_layer_v1":
        return (
            "For every candidate, prioritize a self-contained layer identity. It should remain "
            "recognizable when isolated, have a clear silhouette, and avoid a broad scenery crop "
            "or heavily occluded subject when an equally meaningful alternative is visible. "
            "Do not choose a collection of unrelated background fragments just to fill a layer. "
        )
    if profile == "physical_layer_v2":
        return (
            "Classify every candidate with kind subject or scene_anchor. Return at most two "
            "scene_anchor candidates and prefer one when a broad meaningful scene range can work "
            "as the background of the artwork. A scene_anchor must have exactly one component: "
            "one broad rectangular range such as a garden, room, or landscape; do not split it "
            "into individual objects. Give it a landscape-friendly range that can be displayed at "
            "least 0.60 of canvas width. Subjects must be self-contained and must resolve to one "
            "connected visible shape after segmentation; never combine separated objects merely "
            "to fill a layer. Avoid candidates that would need to float high above the canvas. "
        )
    if profile == "physical_layer_v3_architecture":
        return (
            "Classify every candidate with kind subject or scene_anchor. Return at most two "
            "scene_anchor candidates. When a clearly visible historic building is present, return "
            "one architecture_primary subject for the complete main building, not a scenery crop. "
            "You may return architecture_detail subjects only for visually separate, "
            "non-overlapping "
            "details such as a roof ornament or upper tier; never return duplicate full-building "
            "silhouettes. Use semantic_role general, architecture_primary, or architecture_detail. "
            "A scene_anchor must have exactly one broad rectangular component. Every subject must "
            "resolve to one connected visible shape after segmentation; never combine separated "
            "objects merely to fill a layer. Avoid candidates that would need to float high above "
            "the canvas. "
        )
    if profile == "coherent_group_planning":
        return (
            "Classify every candidate with kind subject or scene_anchor and with extraction_intent "
            "single_form, coherent_group, or scene_anchor. Use coherent_group only when two or "
            "more visible components are all necessary for one meaningful memory element, such as "
            "a dish with its food or a person with a held object. A coherent_group must have at "
            "least two tight component bboxes in the same source photo, exactly one required "
            "primary component, and every other component must state whether it is contained, "
            "supported_by, or attached to that primary component. Do not group unrelated objects "
            "just to fill a layer. Use single_form when one independent visible shape is enough. "
            "Use scene_anchor only for one broad rectangular background range with exactly one "
            "component. This profile plans component relationships only; it does not decide Mask "
            "union, physical support, or final Layer acceptance. "
        )
    raise AiNotConfiguredError("未対応のSEMANTIC_PROFILEです")


async def _generate_structured(
    client: genai.Client,
    model: str,
    contents: list[object],
    result_model: type,
    response_schema: dict[str, Any],
    request_timeout_ms: int,
) -> object:
    try:
        # Toolを渡さないStructured Outputでは自動function callingを無効化する。
        # 同期SDK呼び出しだけをthreadへ退避し、FastAPI event loopをblockしない。
        response = await asyncio.to_thread(
            client.models.generate_content,
            model=model,
            contents=contents,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                # JSON Schemaを明示し、response.parsedをPydanticで再検証する。
                response_json_schema=response_schema,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                http_options=types.HttpOptions(timeout=request_timeout_ms),
            ),
        )
    except Exception as exc:
        name = type(exc).__name__.lower()
        if "timeout" in name or "deadline" in name:
            raise AiTimeoutError("Gemini request timed out") from exc
        if "rate" in name or "resourceexhausted" in name or "429" in str(exc):
            raise AiRateLimitedError("Gemini rate limited") from exc
        raise AiError("Gemini structured output request failed") from exc
    parsed = getattr(response, "parsed", None)
    if parsed is None:
        raise AiError("Gemini structured output was empty")
    return result_model.model_validate(parsed)


def _semantic_plan_schema(
    *, require_semantic_role: bool = False, require_extraction_plan: bool = False
) -> dict[str, Any]:
    box = {
        "type": "object",
        "properties": {name: {"type": "integer"} for name in ("y_min", "x_min", "y_max", "x_max")},
        "required": ["y_min", "x_min", "y_max", "x_max"],
    }
    component = {
        "type": "object",
        "properties": {
            "component_id": {"type": "string"},
            "label": {"type": "string"},
            "box_2d": box,
            "required": {"type": "boolean"},
        },
        "required": ["component_id", "label", "box_2d", "required"],
    }
    candidate = {
        "type": "object",
        "properties": {
            "candidate_id": {"type": "string"},
            "label": {"type": "string"},
            "source_photo_index": {"type": "integer"},
            "importance": {"type": "number"},
            "selection_reason": {"type": "string"},
            "kind": {"type": "string", "enum": ["subject", "scene_anchor"]},
            "semantic_role": {
                "type": "string",
                "enum": ["general", "architecture_primary", "architecture_detail"],
            },
            "components": {"type": "array", "items": component},
        },
        "required": [
            "candidate_id",
            "label",
            "source_photo_index",
            "importance",
            "selection_reason",
            "kind",
            "components",
        ],
    }
    if require_semantic_role:
        candidate["required"].append("semantic_role")
    if require_extraction_plan:
        candidate["properties"]["extraction_intent"] = {
            "type": "string",
            "enum": ["single_form", "coherent_group", "scene_anchor"],
        }
        component["properties"]["relation_to_primary"] = {
            "type": "string",
            "enum": ["primary", "contained", "supported_by", "attached"],
        }
        candidate["required"].append("extraction_intent")
        component["required"].append("relation_to_primary")
    return {
        "type": "object",
        "properties": {
            "memory_summary": {"type": "string"},
            "candidates": {"type": "array", "items": candidate},
        },
        "required": ["memory_summary", "candidates"],
    }


def _composition_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "layers": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "candidate_id": {"type": "string"},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "scale": {"type": "number"},
                        "order": {"type": "integer"},
                    },
                    "required": ["candidate_id", "x", "y", "scale", "order"],
                },
            }
        },
        "required": ["layers"],
    }


def _build_source_assets(decoded) -> list[SourcePhotoAsset]:
    result: list[SourcePhotoAsset] = []
    for index, item in enumerate(decoded):
        image = item.image
        result.append(
            SourcePhotoAsset(
                source_photo_id=f"source-photo-{index + 1}",
                asset=AssetBlob(
                    asset_id=f"source-{uuid4().hex}",
                    mime_type=item.input_photo.mime_type,
                    width_px=image.width,
                    height_px=image.height,
                    # InputPhotoが既に保持しているbytesを参照し、全写真を再encodeして
                    # Cloud RunのPeak Memoryを増やさない。LayerのみRGBA PNGにする。
                    data=item.input_photo.data,
                ),
            )
        )
    return result


def _image_part(image: Image.Image) -> types.Part:
    content = BytesIO()
    image.save(content, format="PNG", optimize=True)
    return types.Part.from_bytes(data=content.getvalue(), mime_type="image/png")


def _asset_thumbnail(asset: AssetBlob) -> Image.Image:
    with Image.open(BytesIO(asset.data)) as image:
        return thumbnail(image.convert("RGBA"), 512)


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000
