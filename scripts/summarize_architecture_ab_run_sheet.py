"""architecture A/Bのprivate実行台帳を検査し、採否前の技術集計を作る。"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

FAILURE_STAGES = {
    "semantic",
    "source",
    "bbox",
    "mask",
    "layer",
    "composition",
    "contract",
}
REQUIRED_RESULT_FIELDS = (
    "cloudRunRevision",
    "environmentFingerprint",
    "fourLayerSuccess",
    "contractValidation",
    "artifactDirectory",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Locked regression-6のarchitecture A/B実行台帳を検査・集計する。"
    )
    parser.add_argument("--run-sheet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def _required_string(value: object, *, field: str, run_id: str) -> str | None:
    if not isinstance(value, str) or not value:
        return f"{run_id}: {field}がありません"
    return None


def _result_errors(run: dict[str, Any]) -> list[str]:
    run_id = str(run.get("runId", "<unknown>"))
    result = run.get("result")
    if not isinstance(result, dict):
        return [f"{run_id}: resultがobjectではありません"]

    errors: list[str] = []
    for field in REQUIRED_RESULT_FIELDS:
        value = result.get(field)
        if field in {"fourLayerSuccess", "contractValidation"}:
            if not isinstance(value, bool):
                errors.append(f"{run_id}: {field}がbooleanではありません")
        else:
            error = _required_string(value, field=field, run_id=run_id)
            if error:
                errors.append(error)

    failure_stage = result.get("failureStage")
    completed_success = (
        result.get("fourLayerSuccess") is True
        and result.get("contractValidation") is True
    )
    if completed_success and failure_stage is not None:
        errors.append(f"{run_id}: 成功runにfailureStageがあります")
    if not completed_success and failure_stage not in FAILURE_STAGES:
        errors.append(f"{run_id}: 失敗runのfailureStageが不正です")
    return errors


def summarize_run_sheet(sheet: dict[str, Any]) -> dict[str, object]:
    runs = sheet.get("runs")
    if not isinstance(runs, list):
        raise TypeError("runsがlistではありません")

    errors: list[str] = []
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    runtime_values: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    for run in runs:
        if not isinstance(run, dict):
            errors.append("runがobjectではありません")
            continue
        run_id = run.get("runId")
        variant = run.get("variant")
        case_id = run.get("caseId")
        case_class = run.get("caseClass")
        if not isinstance(run_id, str) or not isinstance(variant, str):
            errors.append("runIdまたはvariantが不正です")
            continue
        if not isinstance(case_id, str) or not isinstance(case_class, str):
            errors.append(f"{run_id}: caseIdまたはcaseClassが不正です")
            continue
        errors.extend(_result_errors(run))
        groups[(variant, case_class, case_id)].append(run)
        result = run.get("result")
        if isinstance(result, dict):
            for field in ("cloudRunRevision", "environmentFingerprint"):
                value = result.get(field)
                if isinstance(value, str) and value:
                    runtime_values[variant][field].add(value)

    rows: list[dict[str, object]] = []
    for (variant, case_class, case_id), items in sorted(groups.items()):
        attempts = sorted(item.get("attempt") for item in items)
        if attempts != [1, 2, 3]:
            errors.append(f"{variant}/{case_id}: attempt 1, 2, 3が揃っていません")
        results = [item.get("result") for item in items]
        valid_results = [item for item in results if isinstance(item, dict)]
        stages = Counter(
            str(item["failureStage"])
            for item in valid_results
            if item.get("failureStage") is not None
        )
        rows.append(
            {
                "variant": variant,
                "caseId": case_id,
                "caseClass": case_class,
                "runCount": len(items),
                "fourLayerSuccessCount": sum(
                    item.get("fourLayerSuccess") is True for item in valid_results
                ),
                "contractValidationSuccessCount": sum(
                    item.get("contractValidation") is True for item in valid_results
                ),
                "failureStages": dict(sorted(stages.items())),
            }
        )

    expected_groups = {
        (variant, case_id)
        for variant in ("baseline", "candidate")
        for case_id in {run.get("caseId") for run in runs if isinstance(run, dict)}
    }
    actual_groups = {(row["variant"], row["caseId"]) for row in rows}
    if expected_groups != actual_groups:
        errors.append("baseline/candidateでcaseの組合せが一致しません")

    runtime_summary = {
        variant: {
            field: {"distinctCount": len(values), "consistent": len(values) == 1}
            for field, values in sorted(fields.items())
        }
        for variant, fields in sorted(runtime_values.items())
    }
    return {
        "evaluationId": sheet.get("evaluationId"),
        "dataset": sheet.get("dataset"),
        "runCount": len(runs),
        "technicalEvidenceReady": not errors,
        "errors": errors,
        "runtimeConsistencyByVariant": runtime_summary,
        "cases": rows,
        "note": (
            "この集計は技術記録の完全性だけを検査する。"
            "匿名化した目視評価と品質採否は別途必要である。"
        ),
    }


def main() -> int:
    args = parse_args()
    sheet = json.loads(args.run_sheet.read_text(encoding="utf-8"))
    if not isinstance(sheet, dict):
        raise TypeError("run sheetの最上位はobjectである必要があります")
    summary = summarize_run_sheet(sheet)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"technicalEvidenceReady={summary['technicalEvidenceReady']}")
    print(f"errors={len(summary['errors'])}")
    return 0 if summary["technicalEvidenceReady"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
