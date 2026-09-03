"""固定Saved Plan / bboxでEfficientSAMだけを決定論的に計測する。

Gemini・Composition・品質gateは実行しない。privateな写真とSaved PlanはGit管理外の
引数で渡し、出力も既定で ``poc-output/`` に保存する。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.image_ops import gemini_box_to_px  # noqa: E402
from ai.internal_models import SemanticPlan  # noqa: E402
from ai.segmentation import EfficientSamOnnxSegmenter, SegmentationResult  # noqa: E402

STAGE_FIELDS = (
    "resizeElapsedMs",
    "tensorPreparationElapsedMs",
    "onnxInferenceElapsedMs",
    "maskRestoreElapsedMs",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True, help="SemanticPlan JSONへのpath")
    parser.add_argument(
        "--photo",
        type=Path,
        action="append",
        required=True,
        help="Saved PlanのsourcePhotoIndex順の写真。複数回指定する",
    )
    parser.add_argument(
        "--model-path",
        type=Path,
        default=BACKEND_DIR / ".models" / "efficientsam_ti.onnx",
    )
    parser.add_argument("--max-side", type=int, default=1024)
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--warmup-runs", type=int, default=1)
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument(
        "--reference-results",
        type=Path,
        help="比較対象のbenchmark JSON。binary Mask hashのTier A一致を検証する",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.runs <= 0 or args.warmup_runs < 0:
        raise SystemExit("--runs は正、--warmup-runs は0以上にしてください")
    if args.max_side <= 0:
        raise SystemExit("--max-side は正の整数にしてください")

    plan = SemanticPlan.model_validate_json(args.plan.read_text(encoding="utf-8"))
    images = [_load_rgb(path) for path in args.photo]
    attempts = _build_attempts(plan, images)
    if not attempts:
        raise SystemExit("Saved PlanにEfficientSAM対象のcomponentがありません")

    output_dir = args.output_dir or (
        REPO_ROOT / "poc-output" / f"performance-optimization-{datetime.now():%Y%m%d-%H%M%S}"
    )
    output_dir.mkdir(parents=True, exist_ok=False)

    segmenter = EfficientSamOnnxSegmenter(args.model_path, args.max_side)
    for _ in range(args.warmup_runs):
        _run_once(segmenter, attempts)

    runs = [_run_once(segmenter, attempts) for _ in range(args.runs)]
    _assert_self_parity(runs)
    if args.reference_results is not None:
        _assert_reference_parity(
            runs[0], json.loads(args.reference_results.read_text(encoding="utf-8"))
        )

    payload = {
        "schemaVersion": 1,
        "kind": "deterministic_efficientsam_segmentation_benchmark",
        "createdAt": datetime.now().astimezone().isoformat(),
        "codeRevision": _git_revision(),
        "scope": {
            "geminiCalled": False,
            "fixedSavedPlan": True,
            "fixedBbox": True,
            "included": [
                "resize",
                "tensor preparation",
                "monolithic ONNX inference",
                "mask restore",
            ],
            "excluded": [
                "scene anchor crop",
                "quality assessment and retry selection",
                "closed-hole fill",
                "micro-island cleanup",
                "RGBA build",
                "composition",
            ],
        },
        "configuration": {
            "modelPath": str(args.model_path),
            "maxSide": args.max_side,
            "measurementRuns": args.runs,
            "warmupRuns": args.warmup_runs,
            "sourcePhotoCount": len(images),
            "segmentationAttemptCount": len(attempts),
        },
        "runs": runs,
        "summary": _summarize(runs),
        "tierA": {
            "selfMaskHashParity": True,
            "referenceMaskHashParity": args.reference_results is not None,
        },
    }
    output_file = output_dir / "benchmark.json"
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"output={output_file}")
    print(json.dumps(payload["summary"], ensure_ascii=False))
    return 0


def _load_rgb(path: Path) -> Image.Image:
    if not path.is_file():
        raise SystemExit(f"写真が見つかりません: {path}")
    with Image.open(path) as source:
        return ImageOps.exif_transpose(source).convert("RGB")


def _build_attempts(plan: SemanticPlan, images: list[Image.Image]) -> list[dict[str, Any]]:
    attempts: list[dict[str, Any]] = []
    for candidate in plan.candidates:
        if candidate.kind == "scene_anchor":
            continue
        if candidate.source_photo_index >= len(images):
            raise SystemExit(
                "Saved Planが参照するsourcePhotoIndexに対応する--photoが不足しています: "
                f"{candidate.source_photo_index}"
            )
        image = images[candidate.source_photo_index]
        for component in candidate.components:
            attempts.append(
                {
                    "candidateId": candidate.candidate_id,
                    "componentId": component.component_id,
                    "sourcePhotoIndex": candidate.source_photo_index,
                    "image": image,
                    "promptBoxPx": gemini_box_to_px(component.box_2d, image.size),
                }
            )
    return attempts


def _run_once(
    segmenter: EfficientSamOnnxSegmenter, attempts: list[dict[str, Any]]
) -> dict[str, Any]:
    started = time.perf_counter()
    results = []
    for attempt in attempts:
        result = segmenter.segment(attempt["image"], attempt["promptBoxPx"])
        results.append(_record_attempt(attempt, result))
    return {"totalElapsedMs": _elapsed_ms(started), "attempts": results}


def _record_attempt(attempt: dict[str, Any], result: SegmentationResult) -> dict[str, Any]:
    timings = result.timings
    mask = np.ascontiguousarray(result.mask, dtype=np.uint8)
    return {
        "candidateId": attempt["candidateId"],
        "componentId": attempt["componentId"],
        "sourcePhotoIndex": attempt["sourcePhotoIndex"],
        "promptBoxPx": list(result.prompt_box_px),
        "score": result.score,
        "maskSha256": hashlib.sha256(mask.tobytes()).hexdigest(),
        "maskShape": list(mask.shape),
        "resizeElapsedMs": timings.resize_elapsed_ms,
        "tensorPreparationElapsedMs": timings.tensor_preparation_elapsed_ms,
        "onnxInferenceElapsedMs": timings.onnx_inference_elapsed_ms,
        "maskRestoreElapsedMs": timings.mask_restore_elapsed_ms,
    }


def _assert_self_parity(runs: list[dict[str, Any]]) -> None:
    reference = _mask_index(runs[0])
    for run_number, run in enumerate(runs[1:], start=2):
        if _mask_index(run) != reference:
            raise RuntimeError(f"同一条件のrun 1とrun {run_number}でbinary Mask hashが一致しません")


def _assert_reference_parity(run: dict[str, Any], reference: dict[str, Any]) -> None:
    reference_runs = reference.get("runs")
    if not isinstance(reference_runs, list) or not reference_runs:
        raise RuntimeError("--reference-results にruns[0]がありません")
    if _mask_index(run) != _mask_index(reference_runs[0]):
        raise RuntimeError("reference benchmarkとbinary Mask hashが一致しません")


def _mask_index(run: dict[str, Any]) -> dict[tuple[str, str, tuple[int, ...]], str]:
    index = {}
    for attempt in run["attempts"]:
        key = (
            attempt["candidateId"],
            attempt["componentId"],
            tuple(attempt["promptBoxPx"]),
        )
        index[key] = attempt["maskSha256"]
    return index


def _summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    values: dict[str, list[float]] = {"totalElapsedMs": []}
    for field in STAGE_FIELDS:
        values[field] = []
    for run in runs:
        values["totalElapsedMs"].append(run["totalElapsedMs"])
        for attempt in run["attempts"]:
            for field in STAGE_FIELDS:
                value = attempt[field]
                if value is not None:
                    values[field].append(value)
    return {field: _distribution(samples) for field, samples in values.items()}


def _distribution(samples: list[float]) -> dict[str, float | int]:
    ordered = sorted(samples)
    return {
        "count": len(ordered),
        "minMs": ordered[0],
        "medianMs": float(np.median(ordered)),
        "maxMs": ordered[-1],
        "p95Ms": ordered[math.ceil(len(ordered) * 0.95) - 1],
    }


def _git_revision() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip() or None


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


if __name__ == "__main__":
    raise SystemExit(main())
