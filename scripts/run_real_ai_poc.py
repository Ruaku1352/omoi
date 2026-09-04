"""追跡対象外の実写真でReal AI Pipelineを実行し、Layerと計測値を保存する。"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.gemini import GeminiArtworkGenerator
from ai.types import InputPhoto
from app.config import Settings
from app.models.artwork import Artwork
from app.services.generator import build_generator
from app.services.validation import check_artwork_rules, check_assets_present
from frontend_handoff_bundle import PocDebugObserver, write_frontend_handoff_bundle

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def _safe_error_record(exc: Exception) -> dict[str, object]:
    """Secretやprovider応答を保存せず、再実行に必要な失敗stageだけを残す。"""
    record: dict[str, object] = {
        "type": type(exc).__name__,
        "causeType": type(exc.__cause__).__name__ if exc.__cause__ else None,
        "category": "generation_failed",
        "message": "Real AI pipelineの実行に失敗しました",
    }
    if isinstance(exc, ValidationError):
        record["validationErrors"] = [
            {
                "location": list(item["loc"]),
                "type": item["type"],
                "message": item["msg"],
            }
            for item in exc.errors()
        ]
    return record


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photos-dir", type=Path, default=REPO_ROOT / "poc-images")
    parser.add_argument(
        "--memory-text",
        required=True,
        help="MVPの正式入力。生成結果と一緒にmemory-text.txtへ保存する。",
    )
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument(
        "--max-photos",
        type=int,
        default=5,
        help="代表MVPは5。0なら探索用に全画像を使う。",
    )
    parser.add_argument("--preview-width-px", type=int, default=1600)
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
    if len(photos) != 5:
        raise SystemExit("MVP代表PoCは写真を正確に5枚指定してください")
    if not args.memory_text.strip():
        raise SystemExit("MVP代表PoCには空でない--memory-textが必要です")
    if args.preview_width_px <= 0:
        raise SystemExit("--preview-width-pxは正の値にしてください")

    run_id = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    staging = args.output_dir / f".frontend-debug-bundle-{run_id}-{uuid4().hex}.tmp"
    settings = Settings()
    if settings.mock_ai:
        raise SystemExit("MOCK_AI=falseで実行してください")
    staging.mkdir()
    observer = PocDebugObserver(staging / "debug")
    generator = build_generator(settings, observer=observer)
    if not isinstance(generator, GeminiArtworkGenerator):
        raise SystemExit("MOCK_AI=falseで実行してください")
    try:
        result = await generator.generate(photos, args.memory_text)
        artwork = Artwork.model_validate(result.artwork)
        errors = check_artwork_rules(artwork) + check_assets_present(
            artwork, result.assets
        )
        if errors:
            raise RuntimeError("; ".join(errors))
        success = True
        error = None
    except Exception as exc:  # noqa: BLE001
        success = False
        error = _safe_error_record(exc)
    record = {
        "success": success,
        "error": error,
        "model": settings.gemini_model,
        "photoCount": len(photos),
        "selectedPhotoFiles": [photo.filename for photo in photos],
        "memoryTextProvided": bool(args.memory_text.strip()),
        "metrics": asdict(generator.last_metrics),
    }
    if success:
        record["layerCount"] = len(artwork.layers)
        record["canvasAspectRatio"] = artwork.canvas.aspect_ratio
        try:
            write_frontend_handoff_bundle(
                output_dir=staging,
                artwork=artwork,
                assets=result.assets,
                memory_text=args.memory_text,
                metrics=record,
                selected_photo_files=[photo.filename for photo in photos],
                preview_width_px=args.preview_width_px,
            )
        except Exception as exc:  # noqa: BLE001
            success = False
            error = _safe_error_record(exc)
            error["message"] = "Frontend handoff bundleの検証または出力に失敗しました"
            record.update({"success": False, "error": error})
    if success:
        output = args.output_dir / f"frontend-debug-bundle-{run_id}"
    else:
        (staging / "metrics.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        output = args.output_dir / f"real-ai-failed-{run_id}"
    staging.rename(output)
    print(f"output={output}")
    print(f"success={success}")
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
