"""coherent_group G1のSemantic Planだけをprivate入力で作るPoC runner。

Mask、RGBA Layer、Composition、Artwork Contractは扱わない。画像とmemoryText、出力planは
Git管理外のprivate directoryにだけ保存する。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from google import genai
from PIL import ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.gemini import GeminiSemanticPlanner
from ai.image_ops import decode_photo, gemini_box_to_px
from ai.internal_models import SemanticPlan
from ai.types import InputPhoto
from app.config import Settings

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-dir",
        type=Path,
        required=True,
        help="5枚の画像とmemory-text.txtを持つGit管理外のcase directory",
    )
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument(
        "--model", default=None, help="未指定ならbackend/.envのGEMINI_MODEL"
    )
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    return parser.parse_args()


def load_case(case_dir: Path) -> tuple[list[InputPhoto], str]:
    if not case_dir.is_dir():
        raise ValueError("--case-dir が存在しません")
    memory_path = case_dir / "memory-text.txt"
    if not memory_path.is_file():
        raise ValueError("case directoryにmemory-text.txtがありません")
    photos = [
        InputPhoto(path.name, MIME_TYPES[path.suffix.lower()], path.read_bytes())
        for path in sorted(case_dir.iterdir())
        if path.is_file() and path.suffix.lower() in MIME_TYPES
    ]
    if len(photos) != 5:
        raise ValueError("G1 PoCは正確に5枚のJPEG / PNG / WebPを必要とします")
    memory_text = memory_path.read_text(encoding="utf-8")
    if not memory_text.strip():
        raise ValueError("memory-text.txtは空にできません")
    return photos, memory_text


def write_component_review_images(
    output: Path, photos: list[InputPhoto], plan: SemanticPlan
) -> list[str]:
    """Write private images so a reviewer can inspect each proposed component bbox."""
    review_dir = output / "component-review"
    review_dir.mkdir()
    review_files: list[str] = []
    for index, candidate in enumerate(plan.candidates, start=1):
        if candidate.source_photo_index >= len(photos):
            continue
        image = decode_photo(photos[candidate.source_photo_index]).image.convert("RGB")
        draw = ImageDraw.Draw(image)
        for component in candidate.components:
            x0, y0, x1, y1 = gemini_box_to_px(component.box_2d, image.size)
            draw.rectangle((x0, y0, x1, y1), outline="#e11d48", width=4)
            draw.text(
                (x0 + 4, y0 + 4),
                f"{component.component_id}: {component.relation_to_primary}",
                fill="#e11d48",
                stroke_width=2,
                stroke_fill="white",
            )
        image_path = review_dir / f"candidate-{index:02d}.png"
        image.save(image_path, "PNG")
        review_files.append(str(image_path.relative_to(output)))
    return review_files


async def run(args: argparse.Namespace) -> int:
    if args.timeout_ms <= 0:
        raise ValueError("--timeout-msは正の整数にしてください")
    photos, memory_text = load_case(args.case_dir)
    settings = Settings()
    if settings.mock_ai:
        raise ValueError("MOCK_AI=falseで実行してください")
    if not settings.gemini_api_key:
        raise ValueError("GEMINI_API_KEYが未設定です")
    model = args.model or settings.gemini_model
    if not model:
        raise ValueError("GEMINI_MODELが未設定です")

    planner = GeminiSemanticPlanner(
        genai.Client(api_key=settings.gemini_api_key),
        model,
        settings.gemini_analysis_max_side,
        args.timeout_ms,
        settings.candidate_count,
        settings.target_layer_max,
        "coherent_group_planning",
    )
    plan = await planner.plan(
        [decode_photo(photo).image for photo in photos], memory_text
    )
    output = (
        args.output_dir
        / f"coherent-group-planning-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    output.mkdir(parents=True)
    photo_hashes = [hashlib.sha256(photo.data).hexdigest() for photo in photos]
    record = {
        "model": model,
        "semanticProfile": "coherent_group_planning",
        "photoCount": len(photos),
        "inputHash": hashlib.sha256("\n".join(photo_hashes).encode()).hexdigest(),
        "memoryTextHash": hashlib.sha256(memory_text.encode()).hexdigest(),
        "candidateCount": len(plan.candidates),
        "coherentGroupCount": sum(
            item.extraction_intent == "coherent_group" for item in plan.candidates
        ),
        "reviewFiles": write_component_review_images(output, photos, plan),
        "notes": "G1 planning only. No segmentation, Mask union, composition, or fallback was run.",
    }
    (output / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "semantic-plan.json").write_text(
        json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"output={output}")
    print(f"coherent_groups={record['coherentGroupCount']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
