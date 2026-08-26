"""Real AI pipelineのUnit Test。Gemini API KeyとONNX Weightを必要としない。"""

from __future__ import annotations

from io import BytesIO

import numpy as np
import pytest
from PIL import Image

from ai.assembly import AcceptedLayer, normalize_composition
from ai.errors import AiNotConfiguredError
from ai.gemini import GeminiArtworkGenerator
from ai.image_ops import gemini_box_to_px, mask_to_rgba_png, union_masks
from ai.internal_models import CompositionPlan, SemanticPlan
from ai.quality import assess_mask
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
    async def compose(self, layers) -> CompositionPlan:
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


def test_efficient_sam_missing_model_fails_without_download(tmp_path) -> None:
    with pytest.raises(AiNotConfiguredError):
        EfficientSamOnnxSegmenter(tmp_path / "missing.onnx", 1024)


def test_mvp_settings_default_to_four_layers_and_2l_landscape() -> None:
    settings = Settings(_env_file=None)

    assert settings.target_layer_min == settings.target_layer_max == 4
    assert settings.artwork_canvas_aspect_ratio == 178 / 127
