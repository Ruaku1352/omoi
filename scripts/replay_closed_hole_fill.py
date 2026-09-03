"""Saved Planのcomponent Maskへclosed-hole fillだけを再生してprivate証跡を残す。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.image_ops import decode_photo, fill_closed_mask_holes, gemini_box_to_px
from ai.internal_models import SemanticPlan
from ai.quality import diagnose_mask
from ai.segmentation import LazyEfficientSamOnnxSegmenter
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
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--candidate-id", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    return parser.parse_args()


def load_photos(case_dir: Path) -> list[InputPhoto]:
    photos = [
        InputPhoto(path.name, MIME_TYPES[path.suffix.lower()], path.read_bytes())
        for path in sorted(case_dir.iterdir())
        if path.is_file() and path.suffix.lower() in MIME_TYPES
    ]
    if len(photos) != 5:
        raise ValueError(
            "case directoryにはJPEG / PNG / WebPを正確に5枚置く必要があります"
        )
    return photos


def input_hash(photos: list[InputPhoto]) -> str:
    return hashlib.sha256(
        "\n".join(hashlib.sha256(photo.data).hexdigest() for photo in photos).encode()
    ).hexdigest()


def selected_candidates(
    plan_dir: Path, candidate_ids: list[str], photos: list[InputPhoto]
):
    run = json.loads((plan_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("inputHash") != input_hash(photos):
        raise ValueError("Saved Planと入力写真のhashが一致しません")
    plan = SemanticPlan.model_validate_json(
        (plan_dir / "semantic-plan.json").read_text(encoding="utf-8")
    )
    by_id = {candidate.candidate_id: candidate for candidate in plan.candidates}
    selected = []
    for candidate_id in candidate_ids:
        candidate = by_id.get(candidate_id)
        if candidate is None:
            raise ValueError(f"candidateが見つかりません: {candidate_id}")
        selected.append(candidate)
    return selected


def write_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255, mode="L").save(path, "PNG")


def replay(args: argparse.Namespace) -> Path:
    photos = load_photos(args.case_dir)
    candidates = selected_candidates(args.plan_dir, args.candidate_id, photos)
    settings = Settings()
    if settings.mock_ai or settings.efficientsam_model_path is None:
        raise ValueError("MOCK_AI=falseおよびEFFICIENTSAM_MODEL_PATHが必要です")
    model_path = settings.efficientsam_model_path
    if not model_path.is_absolute():
        model_path = BACKEND_DIR / model_path
    segmenter = LazyEfficientSamOnnxSegmenter(
        model_path, settings.segmentation_max_side
    )
    output = (
        args.output_dir
        / f"closed-hole-component-replay-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    raw_dir = output / "raw-masks"
    normalized_dir = output / "normalized-masks"
    raw_dir.mkdir(parents=True)
    normalized_dir.mkdir()
    records: list[dict[str, object]] = []
    for candidate in candidates:
        photo = photos[candidate.source_photo_index]
        image = decode_photo(photo).image
        for component in candidate.components:
            print(
                f"stage=segment candidate={candidate.candidate_id} component={component.component_id}",
                flush=True,
            )
            box = gemini_box_to_px(component.box_2d, image.size)
            raw = segmenter.segment(image, box).mask
            normalized = fill_closed_mask_holes(raw)
            changed = np.logical_and(normalized, np.logical_not(raw))
            raw_diagnostics = diagnose_mask(
                raw, max_side=settings.quality_diagnostics_max_side
            )
            normalized_diagnostics = diagnose_mask(
                normalized, max_side=settings.quality_diagnostics_max_side
            )
            base_name = f"{candidate.candidate_id}--{component.component_id}.png"
            write_mask(raw, raw_dir / base_name)
            write_mask(normalized, normalized_dir / base_name)
            records.append(
                {
                    "candidateId": candidate.candidate_id,
                    "componentId": component.component_id,
                    "required": component.required,
                    "sourcePhotoIndex": candidate.source_photo_index,
                    "bboxPx": box,
                    "rawMask": str((raw_dir / base_name).relative_to(output)),
                    "normalizedMask": str(
                        (normalized_dir / base_name).relative_to(output)
                    ),
                    "rawForegroundPixels": int(raw.sum()),
                    "normalizedForegroundPixels": int(normalized.sum()),
                    "addedPixels": int(changed.sum()),
                    "removedPixels": int(
                        np.logical_and(raw, np.logical_not(normalized)).sum()
                    ),
                    "changedTouchesImageBorder": bool(
                        changed[0].any()
                        or changed[-1].any()
                        or changed[:, 0].any()
                        or changed[:, -1].any()
                    ),
                    "rawInteriorHoleCount": raw_diagnostics.interior_hole_count,
                    "normalizedInteriorHoleCount": normalized_diagnostics.interior_hole_count,
                    "normalizedStableAfterReapply": bool(
                        np.array_equal(normalized, fill_closed_mask_holes(normalized))
                    ),
                }
            )
    record = {
        "inputHash": input_hash(photos),
        "planDirectory": str(args.plan_dir),
        "candidateIds": args.candidate_id,
        "segmentationBackend": "efficient_sam_onnx",
        "geminiCalled": False,
        "operation": "fill_closed_mask_holes immediately after component segmentation",
        "records": records,
    }
    (output / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output


def main() -> int:
    output = replay(parse_args())
    print(f"output={output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
