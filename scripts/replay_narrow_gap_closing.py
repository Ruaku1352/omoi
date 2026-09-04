"""保存済みRaw aggregate Maskへnarrow-gap closingだけを再生する。"""

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

from ai.image_ops import close_narrow_mask_gaps
from ai.quality import diagnose_mask


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mask", type=Path, action="append", required=True)
    parser.add_argument("--max-gap-px", type=int, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument("--diagnostics-max-side", type=int, default=512)
    return parser.parse_args()


def read_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8) > 0


def write_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255, mode="L").save(path, "PNG")


def replay(args: argparse.Namespace) -> Path:
    if any(value < 0 for value in args.max_gap_px):
        raise ValueError("max-gap-pxは0以上にしてください")
    if args.diagnostics_max_side <= 0:
        raise ValueError("diagnostics-max-sideは正の値にしてください")

    output = args.output_dir / (
        f"narrow-gap-closing-replay-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    output.mkdir(parents=True)
    records: list[dict[str, object]] = []
    for mask_arg in args.mask:
        mask_path = mask_arg.resolve()
        if not mask_path.is_file():
            raise ValueError(f"Maskがありません: {mask_path}")
        raw = read_mask(mask_path)
        raw_diagnostics = diagnose_mask(raw, max_side=args.diagnostics_max_side)
        variants: list[dict[str, object]] = []
        for max_gap_px in args.max_gap_px:
            closed = close_narrow_mask_gaps(raw, max_gap_px=max_gap_px)
            changed = np.logical_xor(raw, closed)
            output_path = output / f"{mask_path.stem}--gap-{max_gap_px}.png"
            write_mask(closed, output_path)
            diagnostics = diagnose_mask(closed, max_side=args.diagnostics_max_side)
            variants.append(
                {
                    "maxGapPx": max_gap_px,
                    "mask": str(output_path.relative_to(output)),
                    "foregroundPixels": int(closed.sum()),
                    "addedPixels": int(
                        np.logical_and(closed, np.logical_not(raw)).sum()
                    ),
                    "removedPixels": int(
                        np.logical_and(raw, np.logical_not(closed)).sum()
                    ),
                    "changedPixels": int(changed.sum()),
                    "changedRatioOfRaw": float(changed.sum() / raw.sum()),
                    "componentCount": diagnostics.component_count,
                    "largestComponentRatio": diagnostics.largest_component_ratio,
                    "interiorHoleCount": diagnostics.interior_hole_count,
                    "interiorHoleAreaRatio": diagnostics.interior_hole_area_ratio,
                    "idempotent": bool(
                        np.array_equal(
                            closed,
                            close_narrow_mask_gaps(closed, max_gap_px=max_gap_px),
                        )
                    ),
                }
            )
        records.append(
            {
                "sourceMask": str(mask_path.relative_to(REPO_ROOT)),
                "rawForegroundPixels": int(raw.sum()),
                "rawComponentCount": raw_diagnostics.component_count,
                "rawInteriorHoleCount": raw_diagnostics.interior_hole_count,
                "variants": variants,
            }
        )
    (output / "run.json").write_text(
        json.dumps(
            {
                "operation": "close_narrow_mask_gaps only over saved Raw aggregate Masks",
                "geminiCalled": False,
                "excludedOperations": [
                    "component segmentation",
                    "union_masks",
                    "fill_closed_mask_holes",
                    "clean_micro_islands",
                    "quality retry",
                    "composition",
                ],
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
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
