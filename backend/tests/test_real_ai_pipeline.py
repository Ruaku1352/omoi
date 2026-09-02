"""Real AI pipelineのUnit Test。Gemini API KeyとONNX Weightを必要としない。"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from ai.assembly import AcceptedLayer, normalize_composition
from ai.errors import AiError, AiNotConfiguredError
from ai.gemini import GeminiArtworkGenerator, _semantic_plan_schema
from ai.image_ops import (
    close_narrow_mask_gaps,
    fill_closed_mask_holes,
    gemini_box_to_px,
    mask_to_rgba_png,
    union_masks,
)
from ai.internal_models import CompositionPlan, SemanticPlan
from ai.quality import (
    QualityPolicy,
    assess_mask,
    clean_micro_islands,
    diagnose_mask,
)
from ai.segmentation import EfficientSamOnnxSegmenter, SegmentationResult
from ai.types import AssetBlob, InputPhoto
from app.config import Settings
from app.models.artwork import Artwork
from app.services.validation import check_artwork_rules, check_assets_present


def _photo(color: tuple[int, int, int]) -> InputPhoto:
    image = Image.new("RGB", (80, 60), color)
    output = BytesIO()
    image.save(output, format="PNG")
    return InputPhoto(filename="test.png", mime_type="image/png", data=output.getvalue())


class FakePlanner:
    def __init__(self, candidate_count: int = 4) -> None:
        self.candidate_count = candidate_count
        self.last_memory_text = None

    async def plan(self, images, memory_text) -> SemanticPlan:
        del images
        self.last_memory_text = memory_text
        return SemanticPlan.model_validate(
            {
                "memory_summary": "test memory",
                "candidates": [
                    {
                        "candidate_id": f"candidate-{index}",
                        "label": f"element {index}",
                        "source_photo_index": index % 2,
                        "importance": 1 - index / 10,
                        "selection_reason": "test",
                        "components": [
                            {
                                "component_id": f"component-{index}",
                                "label": f"element {index}",
                                "box_2d": {
                                    "y_min": 100,
                                    "x_min": 100,
                                    "y_max": 700,
                                    "x_max": 700,
                                },
                            }
                        ],
                    }
                    for index in range(self.candidate_count)
                ],
            }
        )


class FakeComposer:
    def __init__(self) -> None:
        self.calls = 0

    async def compose(self, layers) -> CompositionPlan:
        self.calls += 1
        return CompositionPlan.model_validate(
            {
                "layers": [
                    {
                        "candidate_id": layer.candidate_id,
                        "x": -0.1 if index == 0 else 0.5,
                        "y": 1.2 if index == 0 else 0.5,
                        "scale": 5 if index == 0 else 0.4,
                        "order": 10 - index,
                    }
                    for index, layer in enumerate(layers)
                ]
            }
        )


class FloatingComposer:
    def __init__(self) -> None:
        self.compose_calls = 0
        self.recompose_calls = 0

    async def compose(self, layers) -> CompositionPlan:
        self.compose_calls += 1
        return self._plan(layers)

    async def recompose(self, layers, *, max_bottom_gap: float) -> CompositionPlan:
        del max_bottom_gap
        self.recompose_calls += 1
        # あえて同じ不適切な構図を返し、決定論的な下方補正まで検証する。
        return self._plan(layers)

    @staticmethod
    def _plan(layers) -> CompositionPlan:
        return CompositionPlan.model_validate(
            {
                "layers": [
                    {
                        "candidate_id": layer.candidate_id,
                        "x": 0.5,
                        "y": 0.15,
                        "scale": 0.2,
                        "order": index,
                    }
                    for index, layer in enumerate(layers)
                ]
            }
        )


class PhysicalPlanner(FakePlanner):
    async def plan(self, images, memory_text) -> SemanticPlan:
        plan = await super().plan(images, memory_text)
        payload = plan.model_dump()
        payload["candidates"].insert(
            0,
            {
                "candidate_id": "scene-anchor",
                "label": "garden scene",
                "source_photo_index": 0,
                "importance": 1,
                "selection_reason": "shared place",
                "kind": "scene_anchor",
                "components": [
                    {
                        "component_id": "scene-range",
                        "label": "garden scene",
                        "box_2d": {"y_min": 0, "x_min": 0, "y_max": 1000, "x_max": 1000},
                    }
                ],
            },
        )
        return SemanticPlan.model_validate(payload)


class FakeSegmenter:
    def segment(self, image: Image.Image, box_px) -> SegmentationResult:
        x0, y0, x1, y1 = box_px
        mask = np.zeros((image.height, image.width), dtype=bool)
        mask[y0:y1, x0:x1] = True
        return SegmentationResult(mask=mask, score=0.9, prompt_box_px=box_px)


class PerforatedSegmenter(FakeSegmenter):
    def segment(self, image: Image.Image, box_px) -> SegmentationResult:
        result = super().segment(image, box_px)
        mask = result.mask.copy()
        x0, y0, x1, y1 = box_px
        hole_x0 = x0 + (x1 - x0) // 3
        hole_x1 = x0 + (x1 - x0) * 2 // 3
        hole_y0 = y0 + (y1 - y0) // 3
        hole_y1 = y0 + (y1 - y0) * 2 // 3
        mask[hole_y0:hole_y1, hole_x0:hole_x1] = False
        return SegmentationResult(mask=mask, score=result.score, prompt_box_px=box_px)


class RejectFirstSegmenter(FakeSegmenter):
    def __init__(self) -> None:
        self.calls = 0

    def segment(self, image: Image.Image, box_px) -> SegmentationResult:
        self.calls += 1
        if self.calls == 1:
            return SegmentationResult(
                mask=np.ones((image.height, image.width), dtype=bool),
                score=0.1,
                prompt_box_px=box_px,
            )
        return super().segment(image, box_px)


class FragmentedFirstSegmenter(FakeSegmenter):
    """最初の候補だけを意味のない2島にし、次候補への置換を検証する。"""

    def __init__(self) -> None:
        self.calls = 0

    def segment(self, image: Image.Image, box_px) -> SegmentationResult:
        self.calls += 1
        if self.calls == 1:
            mask = np.zeros((image.height, image.width), dtype=bool)
            mask[10:20, 10:20] = True
            mask[40:50, 40:50] = True
            return SegmentationResult(mask=mask, score=0.9, prompt_box_px=box_px)
        return super().segment(image, box_px)


class ArchitecturePlanner(FakePlanner):
    async def plan(self, images, memory_text) -> SemanticPlan:
        plan = await super().plan(images, memory_text)
        payload = plan.model_dump()
        payload["candidates"][0]["label"] = "main historic building"
        payload["candidates"][0]["semantic_role"] = "architecture_primary"
        return SemanticPlan.model_validate(payload)


class MicroIslandFirstSegmenter(FakeSegmenter):
    def __init__(self) -> None:
        self.calls = 0

    def segment(self, image: Image.Image, box_px) -> SegmentationResult:
        self.calls += 1
        if self.calls == 1:
            mask = np.zeros((image.height, image.width), dtype=bool)
            mask[10:50, 10:50] = True
            mask[55, 70] = True
            return SegmentationResult(mask=mask, score=0.9, prompt_box_px=box_px)
        return super().segment(image, box_px)


class CoherentGroupPlanner:
    async def plan(self, images, memory_text) -> SemanticPlan:
        del images, memory_text
        return SemanticPlan.model_validate(
            {
                "memory_summary": "ドリブルの思い出",
                "candidates": [
                    {
                        "candidate_id": "dribbler-and-ball",
                        "label": "ドリブルする選手とボール",
                        "source_photo_index": 0,
                        "importance": 1,
                        "selection_reason": "選手とボールで動作が成立する",
                        "extraction_intent": "coherent_group",
                        "components": [
                            {
                                "component_id": "player",
                                "label": "選手",
                                "box_2d": {
                                    "y_min": 100,
                                    "x_min": 100,
                                    "y_max": 700,
                                    "x_max": 450,
                                },
                                "required": True,
                                "relation_to_primary": "primary",
                            },
                            {
                                "component_id": "ball",
                                "label": "ボール",
                                "box_2d": {
                                    "y_min": 100,
                                    "x_min": 700,
                                    "y_max": 300,
                                    "x_max": 900,
                                },
                                "required": True,
                                "relation_to_primary": "attached",
                            },
                        ],
                    }
                ],
            }
        )


def test_bbox_mask_union_and_rgba_png() -> None:
    assert gemini_box_to_px(
        SemanticPlan.model_validate(
            {
                "memory_summary": "x",
                "candidates": [
                    {
                        "candidate_id": "c",
                        "label": "c",
                        "source_photo_index": 0,
                        "importance": 1,
                        "selection_reason": "x",
                        "components": [
                            {
                                "component_id": "c",
                                "label": "c",
                                "box_2d": {"y_min": 100, "x_min": 200, "y_max": 900, "x_max": 800},
                            }
                        ],
                    }
                ],
            }
        )
        .candidates[0]
        .components[0]
        .box_2d,
        (100, 50),
    ) == (20, 5, 80, 45)

    first = np.zeros((10, 10), dtype=bool)
    second = np.zeros((10, 10), dtype=bool)
    first[2:4, 2:4] = True
    second[5:7, 5:7] = True
    merged = union_masks([first, second])
    png, width, height = mask_to_rgba_png(Image.new("RGB", (10, 10), "red"), merged, padding_px=0)
    assert (width, height) == (5, 5)
    with Image.open(BytesIO(png)) as output:
        assert output.mode == "RGBA"
        assert output.getchannel("A").getextrema() == (0, 255)


def test_close_narrow_mask_gaps_closes_only_configured_width() -> None:
    mask = np.zeros((9, 15), dtype=bool)
    mask[2:7, 1:6] = True
    mask[2:7, 7:12] = True

    unchanged = close_narrow_mask_gaps(mask, max_gap_px=0)
    closed = close_narrow_mask_gaps(mask, max_gap_px=1)

    assert np.array_equal(unchanged, mask)
    assert not unchanged[4, 6]
    assert closed[4, 6]
    assert not closed[0, 0]
    with pytest.raises(ValueError, match="non-negative"):
        close_narrow_mask_gaps(mask, max_gap_px=-1)


def test_fill_closed_mask_holes_fills_windows_but_preserves_openings() -> None:
    mask = np.zeros((10, 10), dtype=bool)
    mask[1:9, 1:9] = True
    mask[3:5, 3:5] = False
    mask[6:8, 6:8] = False

    filled = fill_closed_mask_holes(mask)

    assert filled[4, 4]
    assert filled[7, 7]
    assert not filled[0, 0]
    assert filled.sum() == mask.sum() + 8

    open_mask = mask.copy()
    open_mask[1:4, 4] = False
    preserved = fill_closed_mask_holes(open_mask)
    assert not preserved[4, 4]
    assert not preserved[0, 4]


def test_fill_closed_mask_holes_removes_hole_created_by_gap_closing() -> None:
    mask = np.zeros((20, 20), dtype=bool)
    mask[2:18, 2:18] = True
    mask[6:14, 6:14] = False
    # 外部へ開いている1 pxの通路。closing前は中央の透明領域が閉鎖穴ではない。
    mask[1:7, 9] = False

    closed = close_narrow_mask_gaps(mask, max_gap_px=1)
    filled = fill_closed_mask_holes(closed)

    assert diagnose_mask(mask, max_side=20).interior_hole_count == 0
    assert diagnose_mask(closed, max_side=20).interior_hole_count == 1
    assert diagnose_mask(filled, max_side=20).interior_hole_count == 0


def test_quality_gate_rejects_empty_and_full_masks() -> None:
    box = (2, 2, 8, 8)
    assert not assess_mask(np.zeros((10, 10), dtype=bool), box, None).accepted
    assert not assess_mask(np.ones((10, 10), dtype=bool), box, None).accepted
    inside = np.zeros((10, 10), dtype=bool)
    inside[3:7, 3:7] = True
    assert assess_mask(inside, box, 0.8).accepted


def test_mask_diagnostics_describe_components_without_rejecting_them() -> None:
    mask = np.zeros((20, 20), dtype=bool)
    mask[1:11, 1:11] = True
    mask[15:17, 15:17] = True

    diagnostics = diagnose_mask(mask, max_side=20)

    assert diagnostics.component_count == 2
    assert diagnostics.largest_component_ratio == pytest.approx(100 / 104)
    assert diagnostics.top_component_area_ratios == pytest.approx((100 / 104, 4 / 104))
    assert diagnostics.tail_component_area_ratio == 0
    assert diagnostics.interior_hole_count == 0
    assert diagnostics.interior_hole_area_ratio == 0
    quality = assess_mask(mask, (0, 0, 20, 20), 0.9, diagnostics_max_side=20)
    assert quality.accepted
    assert quality.diagnostics == diagnostics
    assert (
        QualityPolicy().rejection_reason(diagnostics, bbox_coverage=1, border_touch=False) is None
    )


def test_mask_diagnostics_observes_interior_holes_without_rejecting_mask() -> None:
    mask = np.zeros((20, 20), dtype=bool)
    mask[2:18, 2:18] = True
    mask[7:13, 7:13] = False

    diagnostics = diagnose_mask(mask, max_side=20)

    assert diagnostics.interior_hole_count == 1
    assert diagnostics.interior_hole_area_ratio == pytest.approx(36 / 220)
    assert assess_mask(mask, (2, 2, 18, 18), 0.9, diagnostics_max_side=20).accepted
    with pytest.raises(ValueError, match="at least one"):
        QualityPolicy(mode="enforce")


def test_micro_island_cleanup_removes_only_micro_islands_at_full_resolution() -> None:
    mask = np.zeros((100, 100), dtype=bool)
    mask[10:50, 10:50] = True
    mask[90, 90] = True

    cleaned = clean_micro_islands(mask, max_removed_area_ratio=0.001)

    assert cleaned.component_count == 2
    assert cleaned.applied
    assert cleaned.removed_area_ratio == pytest.approx(1 / 1601)
    assert cleaned.mask.sum() == 1600
    assert not cleaned.mask[90, 90]

    detached = np.array(mask, copy=True)
    detached[90:92, 90:92] = True
    rejected = clean_micro_islands(detached, max_removed_area_ratio=0.001)
    assert rejected.component_count == 2
    assert not rejected.applied
    assert rejected.removed_area_ratio > 0.001
    assert np.array_equal(rejected.mask, detached)


def test_architecture_profile_schema_requires_semantic_role() -> None:
    default_schema = _semantic_plan_schema()
    architecture_schema = _semantic_plan_schema(require_semantic_role=True)
    default_candidate = default_schema["properties"]["candidates"]["items"]
    architecture_candidate = architecture_schema["properties"]["candidates"]["items"]

    assert "semantic_role" not in default_candidate["required"]
    assert "semantic_role" in architecture_candidate["required"]


def test_coherent_group_schema_requires_intent_and_component_relation() -> None:
    default_schema = _semantic_plan_schema()
    schema = _semantic_plan_schema(require_extraction_plan=True)
    default_candidate = default_schema["properties"]["candidates"]["items"]
    candidate = schema["properties"]["candidates"]["items"]
    default_component = default_candidate["properties"]["components"]["items"]
    component = candidate["properties"]["components"]["items"]

    assert "extraction_intent" not in default_candidate["properties"]
    assert "relation_to_primary" not in default_component["properties"]
    assert "extraction_intent" in candidate["required"]
    assert "relation_to_primary" in component["required"]


def test_coherent_group_requires_one_required_primary_component() -> None:
    payload = {
        "memory_summary": "食事の思い出",
        "candidates": [
            {
                "candidate_id": "meal-set",
                "label": "meal set",
                "source_photo_index": 0,
                "importance": 0.9,
                "selection_reason": "食事の中心",
                "extraction_intent": "coherent_group",
                "components": [
                    {
                        "component_id": "tray",
                        "label": "tray",
                        "box_2d": {"y_min": 100, "x_min": 100, "y_max": 700, "x_max": 700},
                        "required": True,
                        "relation_to_primary": "primary",
                    },
                    {
                        "component_id": "food",
                        "label": "food",
                        "box_2d": {"y_min": 200, "x_min": 200, "y_max": 500, "x_max": 500},
                        "required": True,
                        "relation_to_primary": "contained",
                    },
                ],
            }
        ],
    }

    plan = SemanticPlan.model_validate(payload)

    assert plan.candidates[0].extraction_intent == "coherent_group"
    invalid = plan.model_dump()
    invalid["candidates"][0]["components"][1]["relation_to_primary"] = "primary"
    with pytest.raises(ValueError, match="exactly one primary"):
        SemanticPlan.model_validate(invalid)


def test_layout_normalization_uses_contiguous_layer_indexes() -> None:
    asset = AssetBlob("layer-x", "image/png", 1, 1, b"x")
    accepted = [
        AcceptedLayer("a", "A", 0, "source-a", asset, 1),
        AcceptedLayer("b", "B", 0, "source-b", asset, 1),
    ]
    plan = CompositionPlan.model_validate(
        {
            "layers": [
                {"candidate_id": "a", "x": -1, "y": 2, "scale": 10, "order": 5},
                {"candidate_id": "b", "x": 0.5, "y": 0.5, "scale": 0.2, "order": 1},
            ]
        }
    )
    normalized = normalize_composition(
        accepted,
        plan,
        canvas_aspect_ratio=4 / 3,
        min_scale=0.1,
        max_scale=1.0,
    )
    assert normalized["a"] == {"x": 0.375, "y": 0.5, "scale": 0.75, "layerIndex": 1}
    assert normalized["b"]["layerIndex"] == 0


@pytest.mark.parametrize("size", [(10, 1000), (1000, 10), (100, 100)])
def test_layout_normalization_keeps_any_asset_aspect_inside_canvas(
    size: tuple[int, int],
) -> None:
    width, height = size
    asset = AssetBlob("layer-x", "image/png", width, height, b"x")
    accepted = [AcceptedLayer("a", "A", 0, "source-a", asset, 1)]
    plan = CompositionPlan.model_validate(
        {"layers": [{"candidate_id": "a", "x": -10, "y": 10, "scale": 10, "order": 0}]}
    )

    normalized = normalize_composition(
        accepted,
        plan,
        canvas_aspect_ratio=178 / 127,
        min_scale=0.1,
        max_scale=1.2,
    )["a"]

    display_width = float(normalized["scale"])
    display_height = display_width * (178 / 127) * height / width
    assert display_width <= 1
    assert display_height <= 1
    assert display_width / 2 <= normalized["x"] <= 1 - display_width / 2
    assert display_height / 2 <= normalized["y"] <= 1 - display_height / 2


@pytest.mark.anyio
async def test_real_pipeline_with_fakes_returns_valid_contract_and_rgba_layers() -> None:
    planner = FakePlanner()
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=PerforatedSegmenter(),
        candidate_count=8,
        target_layer_min=4,
        target_layer_max=4,
        segmentation_max_retries=1,
        analysis_max_side=512,
        layer_padding_px=2,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_planner=planner,
        composer=FakeComposer(),
    )
    result = await generator.generate(
        [
            _photo((255, 0, 0)),
            _photo((0, 255, 0)),
            _photo((0, 0, 255)),
            _photo((255, 255, 0)),
            _photo((0, 255, 255)),
        ],
        "memory",
    )

    artwork = Artwork.model_validate(result.artwork)
    assert not check_artwork_rules(artwork)
    assert not check_assets_present(artwork, result.assets)
    assert len(artwork.source_photos) == 5
    assert len(artwork.layers) == 4
    assert artwork.canvas.aspect_ratio == 178 / 127
    assert sorted(layer.layer_index for layer in artwork.layers) == [0, 1, 2, 3]
    assert planner.last_memory_text == "memory"
    for asset in result.assets:
        if asset.asset_id.startswith("layer-"):
            with Image.open(BytesIO(asset.data)) as image:
                assert image.mode == "RGBA"
                alpha = np.asarray(image.getchannel("A"), dtype=np.uint8) > 0
                assert alpha.any()
                assert diagnose_mask(alpha, max_side=80).interior_hole_count == 0
    assert generator.last_metrics.semantic_planning_elapsed_ms >= 0
    assert all(metric.success for metric in generator.last_metrics.candidates)


@pytest.mark.anyio
async def test_mvp_pipeline_fails_without_composition_when_four_layers_are_not_usable() -> None:
    composer = FakeComposer()
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=RejectFirstSegmenter(),
        candidate_count=8,
        target_layer_min=4,
        target_layer_max=4,
        segmentation_max_retries=0,
        analysis_max_side=512,
        layer_padding_px=2,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_planner=FakePlanner(),
        composer=composer,
    )

    with pytest.raises(AiError, match="十分に生成"):
        await generator.generate(
            [_photo((index * 20, 0, 0)) for index in range(5)],
            "memory",
        )

    assert composer.calls == 0
    assert len([metric for metric in generator.last_metrics.candidates if metric.success]) == 3


@pytest.mark.anyio
async def test_enforced_quality_policy_replaces_fragmented_candidate_with_next_candidate() -> None:
    composer = FakeComposer()
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=FragmentedFirstSegmenter(),
        candidate_count=5,
        target_layer_min=4,
        target_layer_max=4,
        segmentation_max_retries=0,
        analysis_max_side=512,
        layer_padding_px=2,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_planner=FakePlanner(candidate_count=5),
        composer=composer,
        quality_policy=QualityPolicy(mode="enforce", max_component_count=1),
        quality_diagnostics_max_side=80,
    )

    result = await generator.generate(
        [_photo((index * 20, 0, 0)) for index in range(5)],
        "memory",
    )

    artwork = Artwork.model_validate(result.artwork)
    assert len(artwork.layers) == 4
    assert composer.calls == 1
    first = generator.last_metrics.candidates[0]
    assert first.failure_reason == "quality_fragmented"
    assert first.mask_component_count == 2
    assert all(layer.label != "element 0" for layer in artwork.layers)


def test_efficient_sam_missing_model_fails_without_download(tmp_path) -> None:
    with pytest.raises(AiNotConfiguredError):
        EfficientSamOnnxSegmenter(tmp_path / "missing.onnx", 1024)


def test_mvp_settings_default_to_four_layers_and_2l_landscape() -> None:
    settings = Settings(_env_file=None)

    assert settings.target_layer_min == settings.target_layer_max == 4
    assert settings.artwork_canvas_aspect_ratio == 178 / 127
    assert settings.semantic_profile == "physical_layer_v2"
    assert settings.candidate_count == 12


@pytest.mark.anyio
async def test_physical_v2_uses_rectangular_scene_anchor_and_limits_floating() -> None:
    composer = FloatingComposer()
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=FakeSegmenter(),
        candidate_count=5,
        target_layer_min=4,
        target_layer_max=4,
        segmentation_max_retries=0,
        analysis_max_side=512,
        layer_padding_px=2,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_profile="physical_layer_v2",
        subject_overlap_diagnostics=True,
        semantic_planner=PhysicalPlanner(candidate_count=4),
        composer=composer,
    )

    result = await generator.generate([_photo((index * 20, 0, 0)) for index in range(5)], "memory")

    artwork = Artwork.model_validate(result.artwork)
    assert len(artwork.layers) == 4
    assert "kind" not in result.artwork["layers"][0]
    diagnostics = generator.last_metrics.physical_ready
    assert diagnostics is not None
    assert diagnostics.scene_anchor_candidate_id == "scene-anchor"
    assert not diagnostics.background_missing
    assert diagnostics.recomposed
    assert len(diagnostics.subject_overlap_pairs) == 3
    assert all(pair["back_obscured_ratio"] == 1 for pair in diagnostics.subject_overlap_pairs)
    assert composer.compose_calls == 1
    assert composer.recompose_calls == 1
    assert diagnostics.y_corrections
    assert all(gap <= 0.30 + 1e-9 for _candidate_id, gap in diagnostics.final_bottom_gaps)
    anchor_metric = next(
        metric
        for metric in generator.last_metrics.candidates
        if metric.candidate_id == "scene-anchor"
    )
    assert anchor_metric.layer_build_mode == "rectangular_crop"
    anchor_asset = next(
        asset for asset in result.assets if asset.asset_id == artwork.layers[0].asset.asset_id
    )
    with Image.open(BytesIO(anchor_asset.data)) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema() == (255, 255)


@pytest.mark.anyio
async def test_physical_v2_rejects_fragmented_subject_without_bridge() -> None:
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=FragmentedFirstSegmenter(),
        candidate_count=5,
        target_layer_min=4,
        target_layer_max=4,
        segmentation_max_retries=0,
        analysis_max_side=512,
        layer_padding_px=2,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_profile="physical_layer_v2",
        semantic_planner=FakePlanner(candidate_count=5),
        composer=FakeComposer(),
    )

    result = await generator.generate([_photo((index * 20, 0, 0)) for index in range(5)], "memory")

    assert len(result.artwork["layers"]) == 4
    diagnostics = generator.last_metrics.physical_ready
    assert diagnostics is not None
    assert diagnostics.background_missing
    assert diagnostics.subject_overlap_pairs == ()
    first = generator.last_metrics.candidates[0]
    assert first.failure_reason == "not_single_component"


@pytest.mark.anyio
async def test_physical_v2_keeps_subject_and_cleans_micro_island() -> None:
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=MicroIslandFirstSegmenter(),
        candidate_count=4,
        target_layer_min=4,
        target_layer_max=4,
        segmentation_max_retries=0,
        analysis_max_side=512,
        layer_padding_px=2,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_profile="physical_layer_v2",
        semantic_planner=FakePlanner(candidate_count=4),
        composer=FakeComposer(),
    )

    result = await generator.generate([_photo((index * 20, 0, 0)) for index in range(5)], "memory")

    assert len(result.artwork["layers"]) == 4
    first = generator.last_metrics.candidates[0]
    assert first.success
    assert first.mask_cleanup.startswith("removed_micro_islands:")


@pytest.mark.anyio
async def test_physical_v2_retains_approved_coherent_group_without_bridge() -> None:
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=PerforatedSegmenter(),
        candidate_count=1,
        target_layer_min=1,
        target_layer_max=1,
        segmentation_max_retries=0,
        analysis_max_side=512,
        layer_padding_px=0,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_profile="physical_layer_v2",
        semantic_planner=CoherentGroupPlanner(),
        composer=FakeComposer(),
    )

    result = await generator.generate([_photo((0, 0, 0))], "memory")

    assert len(result.artwork["layers"]) == 1
    metric = generator.last_metrics.candidates[0]
    assert metric.success
    assert metric.mask_cleanup == "retained_coherent_group:2"
    assert metric.mask_component_count == 2
    assert metric.coherent_group_required_component_count == 2
    assert metric.coherent_group_required_component_accepted_count == 2
    assert metric.coherent_group_component_exclusive_area_ratios is not None
    assert [
        component_id for component_id, _ in metric.coherent_group_component_exclusive_area_ratios
    ] == [
        "player",
        "ball",
    ]
    assert sum(
        ratio for _, ratio in metric.coherent_group_component_exclusive_area_ratios
    ) == pytest.approx(1)
    layer_asset_id = result.artwork["layers"][0]["asset"]["assetId"]
    layer_asset = next(asset for asset in result.assets if asset.asset_id == layer_asset_id)
    with Image.open(BytesIO(layer_asset.data)) as image:
        alpha = np.asarray(image.getchannel("A"), dtype=np.uint8) > 0
    diagnostics = diagnose_mask(alpha, max_side=80)
    assert diagnostics.component_count == 2
    assert diagnostics.interior_hole_count == 0


@pytest.mark.anyio
async def test_architecture_profile_keeps_primary_building_and_cleans_micro_island() -> None:
    generator = GeminiArtworkGenerator(
        api_key="test-key",
        model="test-model",
        segmenter=MicroIslandFirstSegmenter(),
        candidate_count=4,
        target_layer_min=4,
        target_layer_max=4,
        segmentation_max_retries=0,
        analysis_max_side=512,
        layer_padding_px=2,
        layout_min_scale=0.1,
        layout_max_scale=1.0,
        canvas_aspect_ratio=178 / 127,
        gemini_request_timeout_ms=10_000,
        semantic_profile="physical_layer_v3_architecture",
        semantic_planner=ArchitecturePlanner(candidate_count=4),
        composer=FakeComposer(),
    )

    result = await generator.generate([_photo((index * 20, 0, 0)) for index in range(5)], "memory")

    assert len(result.artwork["layers"]) == 4
    primary = generator.last_metrics.candidates[0]
    assert primary.semantic_role == "architecture_primary"
    assert primary.mask_cleanup.startswith("removed_micro_islands:")
    assert primary.success
    assert any(layer["label"] == "main historic building" for layer in result.artwork["layers"])
