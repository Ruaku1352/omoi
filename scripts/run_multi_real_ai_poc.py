"""同一Production Promptで3写真パターンをE2E検証する、Git管理外のReal AI PoC runner。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.errors import AiError, AiRateLimitedError, AiTimeoutError  # noqa: E402
from ai.gemini import GeminiArtworkGenerator  # noqa: E402
from ai.types import AssetBlob, InputPhoto  # noqa: E402
from app.config import Settings  # noqa: E402
from app.models.artwork import Artwork  # noqa: E402
from app.services.generator import build_generator  # noqa: E402
from app.services.validation import check_artwork_rules, check_assets_present  # noqa: E402

MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
MEMORY_TEXT = "金沢観光で、庭園・伝統建築・食・文化体験を楽しんだ日。"


@dataclass(frozen=True)
class Pattern:
    name: str
    photos: tuple[str, ...]


# HEIC/HEIFを含めず、過去の5枚PoCとは異なる写真を優先する可変長の代表セット。
PATTERNS = (
    Pattern("garden_night_kimono", ("IMG_2663.png", "IMG_2712.jpg", "IMG_5319.png")),
    Pattern("craft_architecture", ("IMG_2708.jpg", "IMG_2718.png", "IMG_2844.png")),
    Pattern("sweets_and_gold_craft", ("IMG_2853.jpg", "IMG_2900.png", "IMG_2708.jpg")),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photos-dir", type=Path, default=REPO_ROOT / "poc-images")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--efficientsam-model-path", type=Path, required=True)
    parser.add_argument("--preview-width-px", type=int, default=1600)
    parser.add_argument(
        "--pattern", choices=[pattern.name for pattern in PATTERNS], action="append"
    )
    return parser.parse_args()


def load_pattern(pattern: Pattern, photos_dir: Path) -> list[InputPhoto]:
    photos: list[InputPhoto] = []
    for filename in pattern.photos:
        path = photos_dir / filename
        mime_type = MIME_TYPES.get(path.suffix.lower())
        if not path.is_file() or mime_type is None:
            raise ValueError(f"P0対象画像が見つからない、または形式対象外です: {filename}")
        photos.append(InputPhoto(filename, mime_type, path.read_bytes()))
    return photos


async def run(args: argparse.Namespace) -> int:
    if not args.efficientsam_model_path.is_file():
        raise SystemExit("--efficientsam-model-path のONNXファイルが見つかりません")
    if args.preview_width_px <= 0:
        raise SystemExit("--preview-width-px は正の値にしてください")
    settings = Settings().model_copy(
        update={
            "mock_ai": False,
            "gemini_model": args.model,
            "efficientsam_model_path": args.efficientsam_model_path,
        }
    )
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEYが未設定です")
    output = args.output_dir / f"multi-real-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output.mkdir(parents=True)
    selected_patterns = (
        PATTERNS
        if not args.pattern
        else tuple(pattern for pattern in PATTERNS if pattern.name in args.pattern)
    )
    records = []
    for pattern in selected_patterns:
        records.append(
            await run_pattern(pattern, args.photos_dir, output, settings, args.preview_width_px)
        )
    (output / "summary.json").write_text(
        json.dumps(
            {
                "model": args.model,
                "memoryText": MEMORY_TEXT,
                "promptSystem": (
                    "GeminiArtworkGenerator production SemanticPlanner and Composer prompts"
                ),
                "patterns": records,
                "notes": "各パターンは同じPrompt系で実行。Mock fallback・HEIC変換・自動retryなし。",
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return 0 if all(record["success"] for record in records) else 1


async def run_pattern(
    pattern: Pattern,
    photos_dir: Path,
    output: Path,
    settings: Settings,
    preview_width_px: int,
) -> dict[str, Any]:
    pattern_output = output / pattern.name
    pattern_output.mkdir()
    generator: GeminiArtworkGenerator | None = None
    try:
        photos = load_pattern(pattern, photos_dir)
        generator = build_generator(settings)
        if not isinstance(generator, GeminiArtworkGenerator):
            raise RuntimeError("MOCK_AI=falseのReal generatorを構成できません")
        result = await generator.generate(photos, MEMORY_TEXT)
        artwork = Artwork.model_validate(result.artwork)
        errors = check_artwork_rules(artwork) + check_assets_present(artwork, result.assets)
        if errors:
            raise RuntimeError("artwork_or_assets_invalid")
        write_artifacts(pattern_output, artwork, result.assets, preview_width_px)
        record = {
            "pattern": pattern.name,
            "selectedPhotoFiles": list(pattern.photos),
            "success": True,
            "error_type": None,
            "layerCount": len(artwork.layers),
            "metrics": asdict(generator.last_metrics),
            "artworkSchemaValidation": "passed",
            "notes": "Semantic Planning・EfficientSAM・CompositionをProduction Promptのまま実行。",
        }
    except Exception as exc:
        record = {
            "pattern": pattern.name,
            "selectedPhotoFiles": list(pattern.photos),
            "success": False,
            "error_type": classify_error(exc),
            "metrics": asdict(generator.last_metrics) if generator else None,
            "notes": "Provider raw response・例外本文は保存しない。",
        }
    (pattern_output / "metrics.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return record


def write_artifacts(output: Path, artwork: Artwork, assets: Any, preview_width_px: int) -> None:
    (output / "artwork.json").write_text(
        json.dumps(
            artwork.model_dump(by_alias=True, exclude_none=True), ensure_ascii=False, indent=2
        ),
        encoding="utf-8",
    )
    assets_dir = output / "assets"
    assets_dir.mkdir()
    assets_by_id = {asset.asset_id: asset for asset in assets}
    for asset in assets:
        extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}[asset.mime_type]
        (assets_dir / f"{asset.asset_id}.{extension}").write_bytes(asset.data)
    render_preview(artwork, assets_by_id, output / "composition-preview.png", preview_width_px)


def render_preview(
    artwork: Artwork,
    assets_by_id: dict[str, AssetBlob],
    output_path: Path,
    width_px: int,
) -> None:
    """Artwork Dataだけを配置正本とし、layerIndex順にRGBA Assetを描画する。"""

    height_px = round(width_px / artwork.canvas.aspect_ratio)
    canvas = Image.new("RGBA", (width_px, height_px), "#F7F3EA")
    for layer in sorted(artwork.layers, key=lambda item: item.layer_index):
        asset = assets_by_id[layer.asset.asset_id]
        from io import BytesIO

        with Image.open(BytesIO(asset.data)) as source:
            image = source.convert("RGBA")
        display_width = max(1, round(layer.scale * width_px))
        display_height = max(1, round(display_width * image.height / image.width))
        image = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        left = round(layer.x * width_px - display_width / 2)
        top = round(layer.y * height_px - display_height / 2)
        canvas.alpha_composite(image, (left, top))
    canvas.save(output_path, format="PNG")


def classify_error(exc: Exception) -> str:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status == 429:
        return "rate_limited"
    if status == 503:
        return "service_unavailable"
    if status == 504:
        return "gateway_timeout"
    if "readtimeout" in type(exc).__name__.lower():
        return "client_timeout"
    if isinstance(exc, AiRateLimitedError):
        return "rate_limited"
    if isinstance(exc, AiTimeoutError):
        return "client_timeout"
    if isinstance(exc, AiError):
        return "e2e_generation_failed"
    if isinstance(exc, ValueError):
        return "input_or_schema_error"
    return "provider_or_e2e_error"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
