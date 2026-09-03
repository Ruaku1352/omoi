from __future__ import annotations

from io import BytesIO

from PIL import Image

from ai.assembly import (
    AcceptedLayer,
    diagnose_composition_layers,
    diagnose_subject_overlaps,
)
from ai.types import AssetBlob


def _layer(candidate_id: str, color: str) -> AcceptedLayer:
    image = Image.new("RGBA", (10, 10), color)
    output = BytesIO()
    image.save(output, format="PNG")
    asset = AssetBlob(
        asset_id=f"asset-{candidate_id}",
        mime_type="image/png",
        width_px=10,
        height_px=10,
        data=output.getvalue(),
    )
    return AcceptedLayer(candidate_id, candidate_id, 0, candidate_id, asset, 1)


def test_subject_overlap_diagnostics_measures_alpha_overlap_in_layer_order() -> None:
    back = _layer("back", "red")
    front = _layer("front", "blue")
    diagnostics = diagnose_subject_overlaps(
        [front, back],
        {
            "back": {"x": 0.5, "y": 0.5, "scale": 0.5, "layerIndex": 0},
            "front": {"x": 0.5, "y": 0.5, "scale": 0.5, "layerIndex": 1},
        },
        canvas_aspect_ratio=1,
        max_canvas_width_px=100,
    )

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.back_candidate_id == "back"
    assert diagnostic.front_candidate_id == "front"
    assert diagnostic.overlap_pixels == 2500
    assert diagnostic.back_obscured_ratio == 1
    assert diagnostic.front_overlap_ratio == 1


def test_subject_overlap_diagnostics_ignores_scene_anchor() -> None:
    anchor = _layer("anchor", "green")
    anchor = AcceptedLayer(
        anchor.candidate_id,
        anchor.label,
        anchor.source_photo_index,
        anchor.source_layer_id,
        anchor.asset,
        anchor.importance,
        kind="scene_anchor",
    )
    subject = _layer("subject", "red")

    diagnostics = diagnose_subject_overlaps(
        [anchor, subject],
        {
            "anchor": {"x": 0.5, "y": 0.5, "scale": 1.0, "layerIndex": 0},
            "subject": {"x": 0.5, "y": 0.5, "scale": 0.5, "layerIndex": 1},
        },
        canvas_aspect_ratio=1,
    )

    assert diagnostics == ()


def test_composition_layer_diagnostics_tolerates_floating_point_canvas_edge() -> None:
    layer = _layer("edge", "red")
    diagnostics = diagnose_composition_layers(
        [layer],
        {
            "edge": {
                "x": 0.5 - 5e-10,
                "y": 0.5 + 5e-10,
                "scale": 1.0,
                "layerIndex": 0,
            }
        },
        canvas_aspect_ratio=1,
    )

    assert diagnostics[0].within_canvas
    assert diagnostics[0].left < 0
    assert diagnostics[0].bottom > 1
