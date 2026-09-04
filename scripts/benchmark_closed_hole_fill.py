"""closed-hole fillの旧実装と現行実装をprivate Maskで比較する。"""

from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from ai.image_ops import fill_closed_mask_holes


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mask", type=Path, action="append", required=True)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def previous_hole_fill(mask: np.ndarray) -> np.ndarray:
    """最適化前の8近傍flood-fill。比較専用。"""

    result = np.asarray(mask, dtype=bool)
    height, width = result.shape
    exterior = np.zeros_like(result, dtype=bool)
    pending: list[int] = []

    def mark_exterior(y: int, x: int) -> None:
        if not result[y, x] and not exterior[y, x]:
            exterior[y, x] = True
            pending.append(y * width + x)

    for x in range(width):
        mark_exterior(0, x)
        mark_exterior(height - 1, x)
    for y in range(1, height - 1):
        mark_exterior(y, 0)
        mark_exterior(y, width - 1)
    while pending:
        y, x = divmod(pending.pop(), width)
        for delta_y in (-1, 0, 1):
            for delta_x in (-1, 0, 1):
                if delta_y == 0 and delta_x == 0:
                    continue
                next_y = y + delta_y
                next_x = x + delta_x
                if 0 <= next_y < height and 0 <= next_x < width:
                    mark_exterior(next_y, next_x)
    return np.logical_or(result, ~exterior)


def load_mask(path: Path) -> np.ndarray:
    with Image.open(path) as image:
        return np.asarray(image.convert("L"), dtype=np.uint8) > 0


def digest(mask: np.ndarray) -> str:
    return hashlib.sha256(np.asarray(mask, dtype=np.uint8).tobytes()).hexdigest()


def measure(implementation, masks: list[np.ndarray], runs: int) -> dict[str, object]:
    durations: list[float] = []
    expected_hashes: list[str] | None = None
    for _ in range(runs):
        started = time.perf_counter()
        outputs = [implementation(mask) for mask in masks]
        durations.append((time.perf_counter() - started) * 1000)
        hashes = [digest(mask) for mask in outputs]
        if expected_hashes is None:
            expected_hashes = hashes
        elif hashes != expected_hashes:
            raise RuntimeError("non-deterministic closed-hole fill output")
    return {
        "minMs": min(durations),
        "medianMs": statistics.median(durations),
        "maxMs": max(durations),
        "p95Ms": max(durations),
        "outputHashes": expected_hashes,
    }


def main() -> int:
    args = parse_args()
    if args.runs < 1:
        raise ValueError("--runs must be at least 1")
    masks = [load_mask(path) for path in args.mask]
    previous = measure(previous_hole_fill, masks, args.runs)
    current = measure(fill_closed_mask_holes, masks, args.runs)
    parity = previous["outputHashes"] == current["outputHashes"]
    payload = {
        "runs": args.runs,
        "maskShapes": [list(mask.shape) for mask in masks],
        "previousPixelFloodFill": previous,
        "scipyEightNeighborFill": current,
        "parity": parity,
        "medianSpeedup": previous["medianMs"] / current["medianMs"],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({"parity": parity, "medianSpeedup": payload["medianSpeedup"]}))
    return 0 if parity else 1


if __name__ == "__main__":
    raise SystemExit(main())
