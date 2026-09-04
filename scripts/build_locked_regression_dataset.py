"""Locked regression-6を既存quality runner用のprivate datasetへ復元する。"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPO_ROOT
    / "poc-output"
    / "locked-regression-6-20260901"
    / "evaluation-manifest.json"
)
DEFAULT_ARCHITECTURE_DATASET = REPO_ROOT / "poc-images" / "architecture-evaluation.json"
DEFAULT_DRIVE_ROOT = REPO_ROOT / "poc-images" / "drive-quality-20260831"

NONARCH_SOURCE_DIRECTORIES = {
    "nara-deer": "set-03-nara-deer",
    "kyoto-market-food": "set-04-kyoto-market-food",
    "basketball": "set-20-basketball",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument(
        "--architecture-dataset", type=Path, default=DEFAULT_ARCHITECTURE_DATASET
    )
    parser.add_argument("--drive-root", type=Path, default=DEFAULT_DRIVE_ROOT)
    return parser.parse_args()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        parsed = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"private manifestを読めません: {path.name}") from exc
    if not isinstance(parsed, dict):
        raise TypeError(f"private manifestはobjectである必要があります: {path.name}")
    return parsed


def _input_hash(paths: list[Path]) -> str:
    hashes = [hashlib.sha256(path.read_bytes()).hexdigest() for path in paths]
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest()


def _matching_memory_text(raw_text: str, expected_hash: str) -> str:
    candidates = (raw_text, raw_text.rstrip("\r\n"))
    matches = [
        candidate
        for candidate in candidates
        if hashlib.sha256(candidate.encode()).hexdigest() == expected_hash
    ]
    if not matches:
        raise ValueError("memoryText hashがLocked manifestと一致しません")
    return matches[0]


def _architecture_cases(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    cases = dataset.get("cases")
    if not isinstance(cases, list):
        raise TypeError("architecture datasetにcases配列がありません")
    result: dict[str, dict[str, Any]] = {}
    for case in cases:
        if isinstance(case, dict) and isinstance(case.get("id"), str):
            result[case["id"]] = case
    return result


def build_dataset(
    manifest: dict[str, Any],
    architecture_dataset: dict[str, Any],
    *,
    photos_root: Path,
    drive_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    locked_cases = manifest.get("cases")
    if not isinstance(locked_cases, list) or len(locked_cases) != 6:
        raise ValueError("Locked regression-6 manifestに6件のcaseが必要です")
    architecture_cases = _architecture_cases(architecture_dataset)
    dataset_cases: list[dict[str, Any]] = []
    receipts: list[dict[str, Any]] = []
    for locked_case in locked_cases:
        if not isinstance(locked_case, dict):
            raise TypeError("Locked caseはobjectである必要があります")
        locked_id = locked_case.get("caseId")
        source_case = locked_case.get("sourceCase")
        expected_input_hash = locked_case.get("inputHash")
        expected_memory_hash = locked_case.get("memoryTextHash")
        case_class = locked_case.get("caseClass")
        if not all(
            isinstance(value, str) and value
            for value in (
                locked_id,
                source_case,
                expected_input_hash,
                expected_memory_hash,
                case_class,
            )
        ):
            raise ValueError("Locked caseの必須hashまたはIDがありません")
        if source_case in architecture_cases:
            source = architecture_cases[source_case]
            photos = source.get("photos")
            raw_memory_text = source.get("memoryText")
            if not isinstance(photos, list) or not all(
                isinstance(photo, str) for photo in photos
            ):
                raise ValueError(f"{locked_id}: architecture photosが不正です")
            if not isinstance(raw_memory_text, str):
                raise ValueError(f"{locked_id}: architecture memoryTextが不正です")
            relative_photos = photos
        else:
            source_dir = NONARCH_SOURCE_DIRECTORIES.get(source_case)
            if source_dir is None:
                raise ValueError(f"{locked_id}: 未対応のnon-architecture sourceです")
            raw_memory_text = (drive_root / source_dir / "memory-text.txt").read_text(
                encoding="utf-8"
            )
            relative_photos = [
                f"drive-quality-20260831/{source_dir}/{index:02d}.jpg"
                for index in range(1, 6)
            ]
        if len(relative_photos) != 5:
            raise ValueError(f"{locked_id}: photosは5枚必要です")
        photo_paths = [photos_root / photo for photo in relative_photos]
        if not all(path.is_file() for path in photo_paths):
            raise ValueError(f"{locked_id}: private photoが不足しています")
        memory_text = _matching_memory_text(raw_memory_text, expected_memory_hash)
        actual_input_hash = _input_hash(photo_paths)
        if actual_input_hash != expected_input_hash:
            raise ValueError(f"{locked_id}: input hashがLocked manifestと一致しません")
        dataset_cases.append(
            {
                "id": locked_id,
                "photos": relative_photos,
                "memoryText": memory_text,
                "scenarioTags": ["locked-regression-6", case_class, source_case],
            }
        )
        receipts.append(
            {
                "caseId": locked_id,
                "sourceCase": source_case,
                "photoCount": len(relative_photos),
                "inputHash": actual_input_hash,
                "memoryTextHash": expected_memory_hash,
            }
        )
    return {"cases": dataset_cases}, {
        "lockedEvaluationId": manifest.get("evaluationId"),
        "cases": receipts,
    }


def main() -> int:
    args = parse_args()
    manifest = _load_json(args.manifest)
    architecture_dataset = _load_json(args.architecture_dataset)
    dataset, receipt = build_dataset(
        manifest,
        architecture_dataset,
        photos_root=REPO_ROOT / "poc-images",
        drive_root=args.drive_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    receipt_path = args.output.with_name(f"{args.output.stem}-receipt.json")
    receipt_path.write_text(
        json.dumps(receipt, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"dataset={args.output}")
    print(f"receipt={receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
