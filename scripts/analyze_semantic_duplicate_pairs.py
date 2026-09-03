"""Saved Semantic Planから同一写真内の候補bbox重複を記録する診断。"""

from __future__ import annotations

import argparse
import itertools
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-file", type=Path, required=True)
    parser.add_argument("--output-file", type=Path, required=True)
    return parser.parse_args()


def _box_area(box: dict[str, int | float]) -> float:
    return max(0.0, float(box["y_max"]) - float(box["y_min"])) * max(
        0.0, float(box["x_max"]) - float(box["x_min"])
    )


def _intersection_area(
    first: dict[str, int | float], second: dict[str, int | float]
) -> float:
    return max(
        0.0,
        min(float(first["y_max"]), float(second["y_max"]))
        - max(float(first["y_min"]), float(second["y_min"])),
    ) * max(
        0.0,
        min(float(first["x_max"]), float(second["x_max"]))
        - max(float(first["x_min"]), float(second["x_min"])),
    )


def _pair_metrics(
    first: dict[str, int | float], second: dict[str, int | float]
) -> tuple[float, float]:
    intersection = _intersection_area(first, second)
    if not intersection:
        return 0.0, 0.0
    first_area = _box_area(first)
    second_area = _box_area(second)
    return (
        intersection / (first_area + second_area - intersection),
        intersection / min(first_area, second_area),
    )


def _components(candidate: dict[str, Any]) -> list[dict[str, int | float]]:
    return [component["box_2d"] for component in candidate["components"]]


def overlapping_pairs(plan: dict[str, Any]) -> list[dict[str, Any]]:
    """同一source photoで少しでもbboxが重なる候補対を、結論を付けずに返す。"""

    pairs: list[dict[str, Any]] = []
    candidates = plan["candidates"]
    for first, second in itertools.combinations(candidates, 2):
        if first["source_photo_index"] != second["source_photo_index"]:
            continue
        metrics = [
            _pair_metrics(first_box, second_box)
            for first_box in _components(first)
            for second_box in _components(second)
        ]
        max_iou, max_containment = max(metrics, default=(0.0, 0.0))
        if max_containment == 0:
            continue
        pairs.append(
            {
                "sourcePhotoIndex": first["source_photo_index"],
                "first": {
                    "candidateId": first["candidate_id"],
                    "label": first["label"],
                    "kind": first["kind"],
                    "extractionIntent": first["extraction_intent"],
                },
                "second": {
                    "candidateId": second["candidate_id"],
                    "label": second["label"],
                    "kind": second["kind"],
                    "extractionIntent": second["extraction_intent"],
                },
                "maxComponentBboxIou": max_iou,
                "maxComponentBboxContainment": max_containment,
                "automaticDecision": "review_required",
            }
        )
    return sorted(
        pairs,
        key=lambda pair: (
            -pair["maxComponentBboxContainment"],
            -pair["maxComponentBboxIou"],
            pair["first"]["candidateId"],
            pair["second"]["candidateId"],
        ),
    )


def main() -> int:
    args = parse_args()
    plan = json.loads(args.plan_file.read_text(encoding="utf-8"))
    report = {
        "operation": "same-source candidate component bbox overlap diagnostics only",
        "geminiCalled": False,
        "automaticRejection": False,
        "pairCount": 0,
        "pairs": overlapping_pairs(plan),
        "limitations": [
            "Different photos of the same subject are not detected.",
            "BBox overlap alone does not determine semantic duplication.",
            "scene_anchor foreground overlap can be intentional.",
        ],
    }
    report["pairCount"] = len(report["pairs"])
    args.output_file.parent.mkdir(parents=True, exist_ok=True)
    args.output_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"output={args.output_file}")
    print(f"overlapping_pairs={report['pairCount']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
