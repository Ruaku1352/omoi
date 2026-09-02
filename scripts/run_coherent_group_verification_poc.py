"""coherent_groupの最終LayerをGemini Structured Outputで確認するprivate G4 PoC。"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from io import BytesIO
from pathlib import Path
from typing import Literal

from google import genai
from google.genai import types
from PIL import Image
from pydantic import BaseModel, Field

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.internal_models import SemanticPlan, VisualElementCandidate
from ai.types import InputPhoto
from app.config import Settings

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


class RequiredComponentReview(BaseModel):
    component_id: str
    visible: bool
    explanation: str = Field(min_length=1, max_length=400)


class LayerVerification(BaseModel):
    required_components: list[RequiredComponentReview]
    all_required_components_visible: bool
    unwanted_background: Literal["none", "minor", "major"]
    material_holes: Literal["none", "minor", "major"]
    identity_preserved: bool
    decision: Literal["pass", "fail", "uncertain"]
    rationale: str = Field(min_length=1, max_length=800)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--union-dir", type=Path, required=True)
    parser.add_argument("--candidate-id", required=True)
    parser.add_argument("--model", default=None)
    parser.add_argument("--timeout-ms", type=int, default=120_000)
    return parser.parse_args()


def load_photos(case_dir: Path) -> list[InputPhoto]:
    photos = [
        InputPhoto(path.name, MIME_TYPES[path.suffix.lower()], path.read_bytes())
        for path in sorted(case_dir.iterdir())
        if path.is_file() and path.suffix.lower() in MIME_TYPES
    ]
    if len(photos) != 5:
        raise ValueError("G4 PoCは正確に5枚のJPEG / PNG / WebPを必要とします")
    return photos


def input_hash(photos: list[InputPhoto]) -> str:
    hashes = [hashlib.sha256(photo.data).hexdigest() for photo in photos]
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest()


def load_candidate(plan_dir: Path, candidate_id: str) -> VisualElementCandidate:
    plan_path = plan_dir / "semantic-plan.json"
    if not plan_path.is_file():
        raise ValueError("--plan-dir にsemantic-plan.jsonが必要です")
    plan = SemanticPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    candidate = next(
        (item for item in plan.candidates if item.candidate_id == candidate_id), None
    )
    if candidate is None:
        raise ValueError(f"candidateが見つかりません: {candidate_id}")
    if candidate.extraction_intent != "coherent_group":
        raise ValueError("coherent_group候補だけを検証できます")
    return candidate


def load_preview(union_dir: Path) -> Path:
    run_path = union_dir / "run.json"
    if not run_path.is_file():
        raise ValueError("--union-dir にrun.jsonが必要です")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    preview_files = run.get("previewFiles")
    if not isinstance(preview_files, dict) or len(preview_files) != 1:
        raise ValueError("G4 PoCはLayer previewが1件必要です")
    preview = union_dir / next(iter(preview_files.values()))
    if not preview.is_file():
        raise ValueError("Layer previewが見つかりません")
    return preview


def image_part(path: Path) -> types.Part:
    with Image.open(path) as source:
        image = source.convert("RGB")
    buffer = BytesIO()
    image.save(buffer, "PNG")
    return types.Part.from_bytes(data=buffer.getvalue(), mime_type="image/png")


async def verify(
    client: genai.Client,
    model: str,
    source_path: Path,
    preview_path: Path,
    candidate: VisualElementCandidate,
    timeout_ms: int,
) -> LayerVerification:
    required = [item for item in candidate.components if item.required]
    prompt = (
        "You are reviewing one transparent artwork layer extracted from a source photo. "
        "The first image is the original source. The second image is the extracted RGBA layer "
        "shown on a gray checkerboard background; checkerboard is transparent, not background. "
        "Judge only visible evidence. Do not infer missing content. "
        f"Candidate label: {candidate.label}. "
        "Required components: "
        + "; ".join(f"{item.component_id}={item.label}" for item in required)
        + ". A material hole means a large missing area inside a required component. "
        "Unwanted background means source context unrelated to the declared group, not the required "
        "dish or food itself. Return pass only when all required components are visibly retained, "
        "there is no major unwanted background or material hole, and the layer still represents the candidate."
    )
    response = await asyncio.to_thread(
        client.models.generate_content,
        model=model,
        contents=[prompt, image_part(source_path), image_part(preview_path)],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_json_schema=LayerVerification.model_json_schema(),
            http_options=types.HttpOptions(timeout=timeout_ms),
        ),
    )
    if getattr(response, "parsed", None) is None:
        raise RuntimeError("Gemini Structured Outputが空です")
    return LayerVerification.model_validate(response.parsed)


async def run(args: argparse.Namespace) -> int:
    if args.timeout_ms <= 0:
        raise ValueError("--timeout-msは正の整数で指定してください")
    photos = load_photos(args.case_dir)
    candidate = load_candidate(args.plan_dir, args.candidate_id)
    if candidate.source_photo_index >= len(photos):
        raise ValueError("candidateのsource_photo_indexが範囲外です")
    preview_path = load_preview(args.union_dir)
    settings = Settings()
    if settings.mock_ai or not settings.gemini_api_key:
        raise ValueError("MOCK_AI=falseとGEMINI_API_KEYが必要です")
    model = args.model or settings.gemini_model
    if not model:
        raise ValueError("GEMINI_MODELが未設定です")
    review = await verify(
        genai.Client(api_key=settings.gemini_api_key),
        model,
        args.case_dir / photos[candidate.source_photo_index].filename,
        preview_path,
        candidate,
        args.timeout_ms,
    )
    record = {
        "model": model,
        "candidateId": candidate.candidate_id,
        "inputHash": input_hash(photos),
        "previewHash": hashlib.sha256(preview_path.read_bytes()).hexdigest(),
        "review": review.model_dump(mode="json"),
        "notes": "Private G4 PoC only. This result does not automatically change a production profile.",
    }
    (args.union_dir / "verification.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"decision={review.decision}")
    print(f"verification={args.union_dir / 'verification.json'}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
