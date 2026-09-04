"""保存済みの原寸Maskからmicro-island cleanupを再生し、実行時metricsと照合する。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.quality import clean_micro_islands


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-output",
        type=Path,
        required=True,
        help="quality-evaluation内の1ケース出力Directory",
    )
    parser.add_argument(
        "--max-removed-area-ratio",
        type=float,
        default=0.005,
        help="再生するcleanup上限。candidate実行時の設定値を指定する。",
    )
    parser.add_argument(
        "--output-name",
        default="mask-cleanup-replay.json",
        help="ケース出力Directory内へ保存するJSONファイル名。",
    )
    parser.add_argument(
        "--allow-runtime-mismatch",
        action="store_true",
        help="異なる閾値のstage comparisonで、実行時metricsとの差を正常終了として保存する。",
    )
    return parser.parse_args()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise TypeError(f"object JSONが必要です: {path}")
    return payload


def _runtime_ratio(value: str) -> float | None:
    prefixes = ("removed_micro_islands:", "rejected_detached:")
    for prefix in prefixes:
        if value.startswith(prefix):
            return float(value.removeprefix(prefix))
    return None


def replay(case_output: Path, *, max_removed_area_ratio: float) -> dict[str, object]:
    if not 0 <= max_removed_area_ratio <= 1:
        raise ValueError("--max-removed-area-ratioは0から1の範囲で指定してください")
    metrics = _read_json(case_output / "metrics.json")
    mask_index = _read_json(case_output / "debug" / "masks" / "index.json")
    candidates = metrics.get("metrics", {}).get("candidates", [])
    attempts = mask_index.get("attempts", [])
    if not isinstance(candidates, list) or not isinstance(attempts, list):
        raise TypeError("metricsまたはMask indexの形式が不正です")
    attempts_by_candidate: dict[str, list[dict[str, Any]]] = {}
    for attempt in attempts:
        if isinstance(attempt, dict) and isinstance(attempt.get("candidateId"), str):
            attempts_by_candidate.setdefault(attempt["candidateId"], []).append(attempt)

    records: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        candidate_id = candidate.get("candidate_id")
        runtime_cleanup = candidate.get("mask_cleanup")
        if not isinstance(candidate_id, str) or not isinstance(runtime_cleanup, str):
            continue
        if runtime_cleanup == "not_applicable":
            continue
        candidate_attempts = attempts_by_candidate.get(candidate_id, [])
        if len(candidate_attempts) != 1:
            records.append(
                {
                    "candidateId": candidate_id,
                    "runtimeCleanup": runtime_cleanup,
                    "status": "skipped_multiple_or_missing_component_masks",
                    "maskCount": len(candidate_attempts),
                }
            )
            continue
        mask_file = candidate_attempts[0].get("file")
        if not isinstance(mask_file, str):
            raise TypeError(f"{candidate_id}: Mask fileがありません")
        with Image.open(case_output / "debug" / "masks" / mask_file) as image:
            mask = np.asarray(image.convert("L"), dtype=np.uint8) > 0
        cleanup = clean_micro_islands(mask, max_removed_area_ratio=max_removed_area_ratio)
        expected_ratio = _runtime_ratio(runtime_cleanup)
        replay_ratio = round(cleanup.removed_area_ratio, 6)
        matches = (
            expected_ratio is not None
            and round(expected_ratio, 6) == replay_ratio
            and (
                runtime_cleanup.startswith("removed_micro_islands:") == cleanup.applied
                or runtime_cleanup.startswith("rejected_detached:") == (not cleanup.applied)
            )
        )
        if runtime_cleanup == "already_single_component":
            matches = cleanup.component_count == 1 and not cleanup.applied
        records.append(
            {
                "candidateId": candidate_id,
                "maskFile": mask_file,
                "runtimeCleanup": runtime_cleanup,
                "replayComponentCount": cleanup.component_count,
                "replayRemovedAreaRatio": replay_ratio,
                "replayApplied": cleanup.applied,
                "matchesRuntimeMetric": matches,
            }
        )
    return {
        "caseId": metrics.get("caseId"),
        "maxRemovedAreaRatio": max_removed_area_ratio,
        "records": records,
        "allComparableRecordsMatch": all(
            item.get("matchesRuntimeMetric") is True
            for item in records
            if item.get("status") is None
        ),
    }


def main() -> int:
    args = parse_args()
    result = replay(
        args.case_output,
        max_removed_area_ratio=args.max_removed_area_ratio,
    )
    output = args.case_output / args.output_name
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"output={output}")
    print(f"allComparableRecordsMatch={result['allComparableRecordsMatch']}")
    if result["allComparableRecordsMatch"] or args.allow_runtime_mismatch:
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
