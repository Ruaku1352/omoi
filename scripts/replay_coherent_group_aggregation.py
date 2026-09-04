"""Saved Planのcoherent_groupを、補正なしのcomponent Mask aggregationとして再生する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.image_ops import (
    decode_photo,
    gemini_box_to_px,
    mask_to_rgba_png,
    union_masks,
)
from ai.internal_models import SemanticPlan
from ai.quality import assess_mask, diagnose_mask
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
    if not case_dir.is_dir():
        raise ValueError("case directoryが存在しません")
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


def load_candidates(args: argparse.Namespace, photos: list[InputPhoto]):
    run = json.loads((args.plan_dir / "run.json").read_text(encoding="utf-8"))
    if run.get("inputHash") != input_hash(photos):
        raise ValueError("Saved Planと入力写真のhashが一致しません")
    plan = SemanticPlan.model_validate_json(
        (args.plan_dir / "semantic-plan.json").read_text(encoding="utf-8")
    )
    by_id = {candidate.candidate_id: candidate for candidate in plan.candidates}
    candidates = []
    for candidate_id in args.candidate_id:
        candidate = by_id.get(candidate_id)
        if candidate is None:
            raise ValueError(f"candidateが見つかりません: {candidate_id}")
        if candidate.extraction_intent != "coherent_group":
            raise ValueError(f"coherent_groupではありません: {candidate_id}")
        candidates.append(candidate)
    return candidates


def write_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255, mode="L").save(path, "PNG")


def write_alpha_preview(png: bytes, path: Path) -> None:
    with Image.open(BytesIO(png)) as layer:
        layer = layer.convert("RGBA")
        preview = Image.new("RGB", layer.size, "#e5e7eb")
        draw = ImageDraw.Draw(preview)
        for y in range(0, layer.height, 32):
            for x in range(0, layer.width, 32):
                if (x // 32 + y // 32) % 2:
                    draw.rectangle((x, y, x + 31, y + 31), fill="#9ca3af")
        preview.paste(layer, mask=layer.getchannel("A"))
        preview.save(path, "PNG")


def replay(args: argparse.Namespace) -> Path:
    photos = load_photos(args.case_dir)
    candidates = load_candidates(args, photos)
    settings = Settings()
    if settings.mock_ai or settings.efficientsam_model_path is None:
        raise ValueError("MOCK_AI=falseおよびEFFICIENTSAM_MODEL_PATHが必要です")
    model_path = settings.efficientsam_model_path
    if not model_path.is_absolute():
        model_path = BACKEND_DIR / model_path
    segmenter = LazyEfficientSamOnnxSegmenter(
        model_path, settings.segmentation_max_side
    )
    output = args.output_dir / (
        f"coherent-group-raw-aggregation-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    component_dir = output / "component-masks"
    aggregate_dir = output / "aggregate-masks"
    layer_dir = output / "layers"
    preview_dir = output / "previews"
    for directory in (component_dir, aggregate_dir, layer_dir, preview_dir):
        directory.mkdir(parents=True, exist_ok=True)

    candidate_records: list[dict[str, object]] = []
    for candidate in candidates:
        image = decode_photo(photos[candidate.source_photo_index]).image
        components: list[tuple[object, np.ndarray]] = []
        component_records: list[dict[str, object]] = []
        for component in candidate.components:
            print(
                f"stage=segment candidate={candidate.candidate_id} component={component.component_id}",
                flush=True,
            )
            box = gemini_box_to_px(component.box_2d, image.size)
            result = segmenter.segment(image, box)
            raw_mask = result.mask
            quality = assess_mask(
                raw_mask,
                box,
                result.score,
                diagnostics_max_side=settings.quality_diagnostics_max_side,
            )
            file_name = f"{candidate.candidate_id}--{component.component_id}.png"
            write_mask(raw_mask, component_dir / file_name)
            components.append((component, raw_mask))
            component_records.append(
                {
                    "componentId": component.component_id,
                    "required": component.required,
                    "bboxPx": box,
                    "score": result.score,
                    "qualityAccepted": quality.accepted,
                    "qualityReason": quality.reason,
                    "foregroundPixels": int(raw_mask.sum()),
                    "maskFile": str((component_dir / file_name).relative_to(output)),
                }
            )

        aggregate = union_masks([mask for _, mask in components])
        aggregate_diagnostics = diagnose_mask(
            aggregate, max_side=settings.quality_diagnostics_max_side
        )
        for component_record, (_, mask) in zip(
            component_records, components, strict=True
        ):
            other_masks = [other for _, other in components if other is not mask]
            other_union = (
                union_masks(other_masks) if other_masks else np.zeros_like(mask)
            )
            exclusive = np.logical_and(mask, np.logical_not(other_union))
            component_record["exclusivePixels"] = int(exclusive.sum())
            component_record["exclusiveRatioOfAggregate"] = float(
                exclusive.sum() / aggregate.sum()
            )

        aggregate_name = f"{candidate.candidate_id}.png"
        write_mask(aggregate, aggregate_dir / aggregate_name)
        layer_png, width_px, height_px = mask_to_rgba_png(
            image, aggregate, padding_px=settings.layer_padding_px
        )
        (layer_dir / aggregate_name).write_bytes(layer_png)
        write_alpha_preview(layer_png, preview_dir / aggregate_name)
        candidate_records.append(
            {
                "candidateId": candidate.candidate_id,
                "label": candidate.label,
                "sourcePhotoIndex": candidate.source_photo_index,
                "requiredComponentCount": sum(
                    component.required for component in candidate.components
                ),
                "requiredComponentAcceptedCount": sum(
                    component_record["required"] and component_record["qualityAccepted"]
                    for component_record in component_records
                ),
                "components": component_records,
                "aggregateMask": str(
                    (aggregate_dir / aggregate_name).relative_to(output)
                ),
                "aggregateForegroundPixels": int(aggregate.sum()),
                "aggregateDiagnostics": {
                    "componentCount": aggregate_diagnostics.component_count,
                    "largestComponentRatio": aggregate_diagnostics.largest_component_ratio,
                    "interiorHoleCount": aggregate_diagnostics.interior_hole_count,
                },
                "layer": str((layer_dir / aggregate_name).relative_to(output)),
                "preview": str((preview_dir / aggregate_name).relative_to(output)),
                "layerWidthPx": width_px,
                "layerHeightPx": height_px,
            }
        )

    record = {
        "inputHash": input_hash(photos),
        "planDirectory": str(args.plan_dir),
        "candidateIds": args.candidate_id,
        "segmentationBackend": "efficient_sam_onnx",
        "geminiCalled": False,
        "operation": "raw component segmentation followed by union_masks only",
        "excludedOperations": [
            "fill_closed_mask_holes",
            "close_narrow_mask_gaps",
            "clean_micro_islands",
            "quality retry",
            "composition",
        ],
        "candidates": candidate_records,
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
