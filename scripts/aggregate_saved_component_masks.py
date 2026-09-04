"""保存済みのRaw component Maskを、補正なしで候補単位へunionする。"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.image_ops import union_masks
from ai.quality import diagnose_mask


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-artifact", type=Path, required=True)
    parser.add_argument("--candidate-id", action="append", required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument("--diagnostics-max-side", type=int, default=512)
    return parser.parse_args()


def read_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8) > 0


def write_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255, mode="L").save(path, "PNG")


def replay(args: argparse.Namespace) -> Path:
    source = args.source_artifact.resolve()
    source_run_path = source / "run.json"
    if not source_run_path.is_file():
        raise ValueError("source artifactにrun.jsonがありません")
    source_run = json.loads(source_run_path.read_text(encoding="utf-8"))
    records = source_run.get("records")
    if not isinstance(records, list) or not records:
        raise ValueError("source artifactにcomponent recordsがありません")
    if source_run.get("geminiCalled") is not False:
        raise ValueError("Geminiを呼んだartifactはこのreplayの入力に使えません")

    output = args.output_dir / (
        f"coherent-group-saved-raw-aggregation-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    aggregate_dir = output / "aggregate-masks"
    aggregate_dir.mkdir(parents=True)
    candidate_records: list[dict[str, object]] = []
    for candidate_id in args.candidate_id:
        component_records = [
            record for record in records if record.get("candidateId") == candidate_id
        ]
        if len(component_records) < 2:
            raise ValueError(
                f"candidateに2件以上のcomponent Raw Maskがありません: {candidate_id}"
            )
        masks: list[np.ndarray] = []
        replayed_components: list[dict[str, object]] = []
        for record in component_records:
            raw_name = record.get("rawMask")
            if not isinstance(raw_name, str):
                raise TypeError(f"rawMaskが不正です: {candidate_id}")
            raw_path = source / raw_name
            if not raw_path.is_file():
                raise ValueError(f"Raw Maskがありません: {raw_path}")
            mask = read_mask(raw_path)
            masks.append(mask)
            replayed_components.append(
                {
                    "componentId": record.get("componentId"),
                    "required": record.get("required"),
                    "rawMask": str(raw_path.relative_to(REPO_ROOT)),
                    "foregroundPixels": int(mask.sum()),
                }
            )

        aggregate = union_masks(masks)
        for component, mask in zip(replayed_components, masks, strict=True):
            other_masks = [other for other in masks if other is not mask]
            other_union = (
                union_masks(other_masks) if other_masks else np.zeros_like(mask)
            )
            exclusive = np.logical_and(mask, np.logical_not(other_union))
            component["exclusivePixels"] = int(exclusive.sum())
            component["exclusiveRatioOfAggregate"] = float(
                exclusive.sum() / aggregate.sum()
            )
        diagnostics = diagnose_mask(aggregate, max_side=args.diagnostics_max_side)
        aggregate_path = aggregate_dir / f"{candidate_id}.png"
        write_mask(aggregate, aggregate_path)
        candidate_records.append(
            {
                "candidateId": candidate_id,
                "requiredComponentCount": sum(
                    component["required"] for component in replayed_components
                ),
                "components": replayed_components,
                "aggregateMask": str(aggregate_path.relative_to(output)),
                "aggregateForegroundPixels": int(aggregate.sum()),
                "aggregateDiagnostics": {
                    "componentCount": diagnostics.component_count,
                    "largestComponentRatio": diagnostics.largest_component_ratio,
                    "interiorHoleCount": diagnostics.interior_hole_count,
                    "interiorHoleAreaRatio": diagnostics.interior_hole_area_ratio,
                },
            }
        )

    output_record = {
        "inputHash": source_run.get("inputHash"),
        "sourceArtifact": str(source.relative_to(REPO_ROOT)),
        "sourceGeminiCalled": False,
        "candidateIds": args.candidate_id,
        "operation": "union_masks only over saved Raw component Masks",
        "excludedOperations": [
            "fill_closed_mask_holes",
            "close_narrow_mask_gaps",
            "clean_micro_islands",
            "quality retry",
            "composition",
        ],
        "sourceImageAvailable": False,
        "candidates": candidate_records,
    }
    (output / "run.json").write_text(
        json.dumps(output_record, ensure_ascii=False, indent=2), encoding="utf-8"
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
