"""Composition専用PoCの副作用なしUnit Test。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image


def _module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_composition_poc.py"
    spec = importlib.util.spec_from_file_location("composition_poc", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _layers(module):
    return [
        module.LayerInput("layer-a", "A", "a.jpg", Image.new("RGBA", (100, 200))),
        module.LayerInput("layer-b", "B", "b.jpg", Image.new("RGBA", (400, 100))),
    ]


def test_normalization_keeps_layers_inside_canvas_and_reindexes_order() -> None:
    module = _module()
    plan = module.CompositionResponse.model_validate(
        {
            "layers": [
                {"layerId": "layer-a", "x": -3, "y": 4, "scale": 9, "frontToBackOrder": 8},
                {"layerId": "layer-b", "x": 3, "y": -4, "scale": 0, "frontToBackOrder": -1},
            ]
        }
    )

    layout = module.normalize_composition(
        _layers(module), plan, canvas_aspect_ratio=4 / 3, min_scale=0.1, max_scale=1.2
    )

    assert layout["layer-b"]["layerIndex"] == 0
    assert layout["layer-a"]["layerIndex"] == 1
    assert all(
        value == 0 for value in module.outside_ratio(_layers(module), layout, 4 / 3).values()
    )


def test_preview_is_determined_by_artwork_layer_index(tmp_path: Path) -> None:
    module = _module()
    layers = [
        module.LayerInput("layer-a", "A", "a.jpg", Image.new("RGBA", (20, 20), "red")),
        module.LayerInput("layer-b", "B", "b.jpg", Image.new("RGBA", (20, 20), "blue")),
    ]
    artwork = {
        "canvas": {"aspectRatio": 1.0},
        "layers": [
            {"layerId": "layer-a", "x": 0.5, "y": 0.5, "scale": 1.0, "layerIndex": 1},
            {"layerId": "layer-b", "x": 0.5, "y": 0.5, "scale": 1.0, "layerIndex": 0},
        ],
    }
    output = tmp_path / "preview.png"

    module.render_preview(artwork, layers, output, width_px=20)

    assert Image.open(output).getpixel((10, 10))[:3] == (255, 0, 0)
