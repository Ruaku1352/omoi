"""Locked regression-6から、Cloud Run評価のprivate実行台帳を作る。"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REQUIRED_ARTIFACTS = [
    "semantic_plan",
    "candidate_rejections",
    "bbox_and_component_diagnostics",
    "mask_and_rgba_layers",
    "composition_preview",
    "artwork_and_asset_manifest",
    "contract_validation",
    "stage_elapsed_ms_and_failure_stage",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Locked regression-6のbaseline/candidate実行台帳を生成する。"
    )
    parser.add_argument("--locked-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _required(mapping: dict[str, Any], key: str) -> Any:
    value = mapping.get(key)
    if value is None:
        raise ValueError(f"manifestに{key}がありません")
    return value


def build_run_sheet(manifest: dict[str, Any]) -> dict[str, Any]:
    comparison = _required(manifest, "comparison")
    if not isinstance(comparison, dict):
        raise TypeError("comparisonがobjectではありません")
    baseline = _required(comparison, "baseline")
    candidate = _required(comparison, "candidate")
    if not isinstance(baseline, dict) or not isinstance(candidate, dict):
        raise TypeError("baseline/candidateがobjectではありません")
    repeat = _required(comparison, "repeatPerVariant")
    if not isinstance(repeat, int) or repeat < 1:
        raise ValueError("repeatPerVariantは1以上の整数です")
    cases = _required(manifest, "cases")
    if not isinstance(cases, list) or not cases:
        raise ValueError("casesが空です")
    candidate_profiles = _required(candidate, "semanticProfileByCaseClass")
    if not isinstance(candidate_profiles, dict):
        raise TypeError("candidate.semanticProfileByCaseClassがobjectではありません")

    variants = (
        (
            "baseline",
            _required(baseline, "codeRevision"),
            _required(baseline, "semanticProfile"),
        ),
        ("candidate", _required(candidate, "codeRevision"), None),
    )
    runs: list[dict[str, Any]] = []
    for variant, code_revision, fixed_profile in variants:
        if not isinstance(code_revision, str) or not code_revision:
            raise ValueError(f"{variant}のcodeRevisionが不正です")
        for case in cases:
            if not isinstance(case, dict):
                raise TypeError("caseがobjectではありません")
            case_id = _required(case, "caseId")
            case_class = _required(case, "caseClass")
            profile = fixed_profile or candidate_profiles.get(case_class)
            if not isinstance(profile, str) or not profile:
                raise ValueError(f"{variant}/{case_id}のsemantic profileがありません")
            for run_number in range(1, repeat + 1):
                runs.append(
                    {
                        "runId": f"{variant}-{case_id}-{run_number}",
                        "status": "pending_backend_run",
                        "variant": variant,
                        "codeRevision": code_revision,
                        "semanticProfile": profile,
                        "caseId": case_id,
                        "caseClass": case_class,
                        "inputHash": _required(case, "inputHash"),
                        "memoryTextHash": _required(case, "memoryTextHash"),
                        "attempt": run_number,
                        "result": {
                            "cloudRunRevision": None,
                            "environmentFingerprint": None,
                            "fourLayerSuccess": None,
                            "contractValidation": None,
                            "failureStage": None,
                            "artifactDirectory": None,
                        },
                    }
                )

    return {
        "evaluationId": _required(manifest, "evaluationId"),
        "dataset": _required(manifest, "dataset"),
        "generatedAt": datetime.now(UTC).isoformat(),
        "status": "pending_backend_artifacts",
        "privacy": {
            "containsPhotoBinary": False,
            "containsMemoryText": False,
            "containsSecret": False,
        },
        "fixedConditions": {
            "geminiModel": _required(comparison, "geminiModel"),
            "segmentationBackend": _required(comparison, "segmentationBackend"),
            "expectedLayerCount": _required(comparison, "expectedLayerCount"),
            "runtime": _required(comparison, "runtime"),
        },
        "requiredArtifactsPerRun": REQUIRED_ARTIFACTS,
        "runs": runs,
    }


def main() -> int:
    args = parse_args()
    manifest = json.loads(args.locked_manifest.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise TypeError("manifestの最上位はobjectです")
    run_sheet = build_run_sheet(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(run_sheet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"runs={len(run_sheet['runs'])}")
    print(f"output={args.output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
