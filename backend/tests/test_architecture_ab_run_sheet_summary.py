from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "summarize_architecture_ab_run_sheet.py"
)
SPEC = importlib.util.spec_from_file_location("architecture_ab_run_sheet_summary", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _completed_run(
    *, variant: str, case_id: str, case_class: str, attempt: int
) -> dict[str, object]:
    return {
        "runId": f"{variant}-{case_id}-{attempt}",
        "variant": variant,
        "caseId": case_id,
        "caseClass": case_class,
        "attempt": attempt,
        "result": {
            "cloudRunRevision": f"{variant}-revision",
            "environmentFingerprint": "fixed-non-secret-runtime",
            "fourLayerSuccess": True,
            "contractValidation": True,
            "failureStage": None,
            "artifactDirectory": f"private/{variant}/{case_id}/{attempt}",
        },
    }


def _sheet() -> dict[str, object]:
    runs = []
    for variant in ("baseline", "candidate"):
        for case_id, case_class in (
            ("ARCH-01", "architecture"),
            ("NONARCH-01", "nonArchitecture"),
        ):
            for attempt in (1, 2, 3):
                runs.append(
                    _completed_run(
                        variant=variant,
                        case_id=case_id,
                        case_class=case_class,
                        attempt=attempt,
                    )
                )
    return {"evaluationId": "quality-test", "dataset": "locked-regression-6", "runs": runs}


def test_summary_accepts_complete_three_run_pairs() -> None:
    summary = MODULE.summarize_run_sheet(_sheet())

    assert summary["technicalEvidenceReady"] is True
    assert summary["errors"] == []
    assert len(summary["cases"]) == 4
    assert all(item["fourLayerSuccessCount"] == 3 for item in summary["cases"])


def test_summary_requires_failure_stage_and_artifact_for_failed_run() -> None:
    sheet = _sheet()
    failed = sheet["runs"][0]
    failed["result"]["fourLayerSuccess"] = False
    failed["result"]["contractValidation"] = False
    failed["result"]["failureStage"] = None
    failed["result"]["artifactDirectory"] = None

    summary = MODULE.summarize_run_sheet(sheet)

    assert summary["technicalEvidenceReady"] is False
    assert any("failureStage" in error for error in summary["errors"])
    assert any("artifactDirectory" in error for error in summary["errors"])
