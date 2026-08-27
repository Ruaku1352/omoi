"""Real AI pipelineのUnit Test。Gemini API KeyとONNX Weightを必要としない。"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from ai.assembly import AcceptedLayer, normalize_composition
from ai.errors import AiError, AiNotConfiguredError
from ai.gemini import GeminiArtworkGenerator
from ai.image_ops import gemini_box_to_px, mask_to_rgba_png, union_masks
from ai.internal_models import CompositionPlan, SemanticPlan
from ai.quality import QualityPolicy, assess_mask, diagnose_mask
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


class FakeSegmenter:
    def segment(self, image: Image.Image, box_px) -> SegmentationResult:
        x0, y0, x1, y1 = box_px
        mask = np.zeros((image.height, image.width), dtype=bool)
        mask[y0:y1, x0:x1] = True
        return SegmentationResult(mask=mask, score=0.9, prompt_box_px=box_px)


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
    quality = assess_mask(mask, (0, 0, 20, 20), 0.9, diagnostics_max_side=20)
    assert quality.accepted
    assert quality.diagnostics == diagnostics
    assert QualityPolicy().rejection_reason(
        diagnostics, bbox_coverage=1, border_touch=False
    ) is None
    with pytest.raises(ValueError, match="at least one"):
        QualityPolicy(mode="enforce")


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
        segmenter=FakeSegmenter(),
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
                assert image.getchannel("A").getextrema()[0] == 0
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
