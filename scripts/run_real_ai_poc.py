"""追跡対象外の実写真でReal AI Pipelineを実行し、Layerと計測値を保存する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.gemini import GeminiArtworkGenerator  # noqa: E402
from ai.types import InputPhoto  # noqa: E402
from app.config import Settings  # noqa: E402
from app.models.artwork import Artwork  # noqa: E402
from app.services.generator import build_generator  # noqa: E402
from app.services.validation import check_artwork_rules, check_assets_present  # noqa: E402

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photos-dir", type=Path, default=REPO_ROOT / "poc-images")
    parser.add_argument("--memory-text", default=None)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument(
        "--max-photos",
        type=int,
        default=5,
        help="代表PoCの上限。0なら対象形式の全画像を使う。",
    )
    return parser.parse_args()


async def run(args: argparse.Namespace) -> int:
    photos = [
        InputPhoto(path.name, MIME_TYPES[path.suffix.lower()], path.read_bytes())
        for path in sorted(args.photos_dir.iterdir())
        if path.is_file() and path.suffix.lower() in MIME_TYPES
    ]
    if args.max_photos < 0:
        raise SystemExit("--max-photosは0以上にしてください")
    if args.max_photos:
        photos = photos[: args.max_photos]
    if not photos:
        raise SystemExit("PoC画像が見つかりません")
    output = args.output_dir / datetime.now().strftime("%Y%m%d-%H%M%S")
    layers_dir = output / "layers"
    layers_dir.mkdir(parents=True)
    generator = build_generator(Settings())
    if not isinstance(generator, GeminiArtworkGenerator):
        raise SystemExit("MOCK_AI=falseで実行してください")
    try:
        result = await generator.generate(photos, args.memory_text)
        artwork = Artwork.model_validate(result.artwork)
        errors = check_artwork_rules(artwork) + check_assets_present(artwork, result.assets)
        if errors:
            raise RuntimeError("; ".join(errors))
        (output / "artwork.json").write_text(
            json.dumps(result.artwork, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        layer_ids = {layer.asset.asset_id for layer in artwork.layers}
        for asset in result.assets:
            if asset.asset_id in layer_ids:
                (layers_dir / f"{asset.asset_id}.png").write_bytes(asset.data)
        success = True
        error = None
    except Exception as exc:
        success = False
        error = {
            "type": type(exc).__name__,
            "causeType": type(exc.__cause__).__name__ if exc.__cause__ else None,
            "message": str(exc),
        }
    record = {
        "success": success,
        "error": error,
        "model": Settings().gemini_model,
        "photoCount": len(photos),
        "metrics": asdict(generator.last_metrics),
    }
    (output / "metrics.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    expectation = args.photos_dir / "EXPECTATIONS.md"
    if expectation.is_file():
        (output / "EXPECTATIONS.md").write_text(
            expectation.read_text(encoding="utf-8"), encoding="utf-8"
        )
    print(f"output={output}")
    print(f"success={success}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
