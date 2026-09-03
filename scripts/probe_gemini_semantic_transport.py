"""private評価入力のSemantic transportだけを比較するGemini PoC。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.gemini import GeminiSemanticPlanner
from ai.image_ops import decode_photo, thumbnail
from ai.types import InputPhoto
from app.config import Settings
from frontend_handoff_bundle import PocDebugObserver

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--case-id",
        help="複数caseのprivate datasetから診断対象を1件だけ選ぶ。",
    )
    parser.add_argument("--photos-dir", type=Path, default=REPO_ROOT / "poc-images")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument(
        "--analysis-image-format", choices=("jpeg", "png"), default="jpeg"
    )
    parser.add_argument("--jpeg-quality", type=int, default=85)
    return parser.parse_args()


def _load_case(dataset: Path, case_id: str | None = None) -> tuple[str, list[str], str]:
    payload = json.loads(dataset.read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(cases, list):
        raise ValueError("transport PoCはcases配列を必要とします")  # noqa: TRY004
    matching_cases = [
        case
        for case in cases
        if isinstance(case, dict) and (case_id is None or case.get("id") == case_id)
    ]
    if len(matching_cases) != 1:
        detail = "対象case" if case_id else "1件だけのcase"
        raise ValueError(f"transport PoCは{detail}を必要とします")
    case = matching_cases[0]
    selected_case_id = case.get("id")
    photos = case.get("photos")
    memory_text = case.get("memoryText")
    if (
        not isinstance(selected_case_id, str)
        or not isinstance(photos, list)
        or len(photos) != 5
    ):
        raise ValueError("case idと5枚のphotosが必要です")
    if not all(isinstance(photo, str) and photo for photo in photos):
        raise ValueError("photosは非空string配列である必要があります")
    if not isinstance(memory_text, str) or not memory_text:
        raise ValueError("非空memoryTextが必要です")
    return selected_case_id, photos, memory_text


def _safe_error_metadata(exc: BaseException) -> dict[str, object]:
    """例外本文を残さず、provider失敗を分類する最小情報だけを返す。"""

    cause = exc
    cause_depth = 0
    while cause.__cause__ is not None and cause.__cause__ is not cause:
        cause = cause.__cause__
        cause_depth += 1
    raw_status = getattr(cause, "code", None) or getattr(cause, "status_code", None)
    try:
        http_status = int(raw_status) if raw_status is not None else None
    except (TypeError, ValueError):
        http_status = None
    response = getattr(cause, "response", None)
    headers: Any = getattr(response, "headers", None)
    request_id_present = False
    if headers is not None:
        try:
            request_id_present = any(
                bool(headers.get(name))
                for name in (
                    "x-request-id",
                    "x-goog-request-id",
                    "x-cloud-trace-context",
                )
            )
        except (AttributeError, TypeError):
            request_id_present = False
    return {
        "errorType": type(exc).__name__,
        "providerErrorType": type(cause).__name__,
        "httpStatus": http_status,
        "requestIdPresent": request_id_present,
        "causeDepth": cause_depth,
    }


def _load_images(
    names: list[str], photos_dir: Path
) -> tuple[list[Image.Image], list[str]]:
    images: list[Image.Image] = []
    hashes: list[str] = []
    for name in names:
        path = photos_dir / name
        mime_type = MIME_TYPES.get(path.suffix.lower())
        if mime_type is None or not path.is_file():
            raise ValueError(f"P0形式の画像がありません: {name}")
        data = path.read_bytes()
        images.append(decode_photo(InputPhoto(name, mime_type, data)).image)
        hashes.append(hashlib.sha256(data).hexdigest())
    return images, hashes


def _jpeg_part(image: Image.Image, quality: int) -> tuple[types.Part, int]:
    content = BytesIO()
    image.convert("RGB").save(content, format="JPEG", quality=quality, optimize=True)
    data = content.getvalue()
    return types.Part.from_bytes(data=data, mime_type="image/jpeg"), len(data)


def _png_part(image: Image.Image) -> tuple[types.Part, int]:
    content = BytesIO()
    image.save(content, format="PNG", optimize=True)
    data = content.getvalue()
    return types.Part.from_bytes(data=data, mime_type="image/png"), len(data)


async def probe(args: argparse.Namespace) -> Path:
    if not 1 <= args.jpeg_quality <= 100:
        raise ValueError("jpeg-qualityは1..100です")
    settings = Settings()
    if settings.gemini_model != "gemini-3.5-flash-lite":
        raise ValueError("transport PoCはgemini-3.5-flash-liteを必要とします")
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEYが必要です")
    case_id, photo_names, memory_text = _load_case(args.dataset, args.case_id)
    images, image_hashes = _load_images(photo_names, args.photos_dir)
    thumbnails = [
        thumbnail(image, settings.gemini_analysis_max_side) for image in images
    ]
    parts_and_sizes = (
        [_jpeg_part(image, args.jpeg_quality) for image in thumbnails]
        if args.analysis_image_format == "jpeg"
        else [_png_part(image) for image in thumbnails]
    )
    output = args.output_dir / (
        f"gemini-semantic-transport-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    output.mkdir(parents=True)
    started = time.perf_counter()
    try:
        planner = GeminiSemanticPlanner(
            genai.Client(api_key=settings.gemini_api_key),
            settings.gemini_model,
            settings.gemini_analysis_max_side,
            settings.gemini_request_timeout_ms,
            settings.candidate_count,
            settings.target_layer_max,
            settings.semantic_profile,
        )
        plan = await planner.plan(images, memory_text)
    except Exception as exc:  # noqa: BLE001 -- provider exception本文を出さず分類だけを保存する。
        record: dict[str, object] = {"success": False, **_safe_error_metadata(exc)}
    else:
        (output / "semantic-plan.json").write_text(
            plan.model_dump_json(indent=2), encoding="utf-8"
        )
        PocDebugObserver(output / "debug").semantic_plan(plan, images)
        record = {"success": True, "candidateCount": len(plan.candidates)}
    record.update(
        {
            "caseId": case_id,
            "geminiModel": settings.gemini_model,
            "analysisImageFormat": args.analysis_image_format,
            "jpegQuality": args.jpeg_quality
            if args.analysis_image_format == "jpeg"
            else None,
            "analysisImageBytes": [size for _, size in parts_and_sizes],
            "analysisImageBytesTotal": sum(size for _, size in parts_and_sizes),
            "inputImageSha256": image_hashes,
            "memoryTextSha256": hashlib.sha256(memory_text.encode()).hexdigest(),
            "semanticElapsedMs": round((time.perf_counter() - started) * 1000, 3),
            "automaticFunctionCalling": "disabled",
            "runtimeSemanticPlanner": True,
            "diagnosticErrorMetadata": "exception-type/http-status/request-id-presence-only",
        }
    )
    (output / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


def main() -> int:
    output = asyncio.run(probe(parse_args()))
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
