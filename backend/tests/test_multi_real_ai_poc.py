"""複数E2E Real AI PoC runnerの副作用なしUnit Test。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from PIL import Image


def _module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_multi_real_ai_poc.py"
    spec = importlib.util.spec_from_file_location("multi_real_ai_poc", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_patterns_use_only_p0_supported_photos() -> None:
    module = _module()
    assert len(module.PATTERNS) == 3
    assert all(len(pattern.photos) >= 1 for pattern in module.PATTERNS)
    assert all(
        Path(filename).suffix.lower() in module.MIME_TYPES
        for pattern in module.PATTERNS
        for filename in pattern.photos
    )


def test_preview_uses_layer_index_not_array_order(tmp_path: Path) -> None:
    module = _module()
    red = module.AssetBlob("red", "image/png", 10, 10, _png_bytes("red"))
    blue = module.AssetBlob("blue", "image/png", 10, 10, _png_bytes("blue"))
    artwork = module.Artwork.model_validate(
        {
            "schemaVersion": "1.0",
            "artworkId": "preview-test",
            "canvas": {"aspectRatio": 1},
            "sourcePhotos": [
                {
                    "sourcePhotoId": "source",
                    "asset": {
                        "assetId": "source",
                        "mimeType": "image/png",
                        "widthPx": 1,
                        "heightPx": 1,
                    },
                }
            ],
            "layers": [
                _layer("red", "red", 1),
                _layer("blue", "blue", 0),
            ],
        }
    )
    output = tmp_path / "preview.png"

    module.render_preview(artwork, {"red": red, "blue": blue}, output, 10)

    assert Image.open(output).getpixel((5, 5))[:3] == (255, 0, 0)


def _layer(layer_id: str, asset_id: str, layer_index: int) -> dict:
    return {
        "layerId": layer_id,
        "sourcePhotoId": "source",
        "sourceLayerId": f"source-{layer_id}",
        "asset": {"assetId": asset_id, "mimeType": "image/png", "widthPx": 10, "heightPx": 10},
        "label": layer_id,
        "x": 0.5,
        "y": 0.5,
        "scale": 1,
        "layerIndex": layer_index,
        "replacementCandidates": [],
    }


def _png_bytes(color: str) -> bytes:
    from io import BytesIO

    output = BytesIO()
    Image.new("RGBA", (10, 10), color).save(output, format="PNG")
    return output.getvalue()
