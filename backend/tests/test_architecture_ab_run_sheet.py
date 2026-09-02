from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "create_architecture_ab_run_sheet.py"
)
SPEC = importlib.util.spec_from_file_location("architecture_ab_run_sheet", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _manifest() -> dict[str, object]:
    return {
        "evaluationId": "quality-test",
        "dataset": "locked-regression-6",
        "comparison": {
            "baseline": {
                "codeRevision": "baseline-sha",
                "semanticProfile": "physical_layer_v2",
            },
            "candidate": {
                "codeRevision": "candidate-sha",
                "semanticProfileByCaseClass": {
                    "architecture": "physical_layer_v3_architecture",
                    "nonArchitecture": "physical_layer_v2",
                },
            },
            "repeatPerVariant": 3,
            "geminiModel": "gemini-3.5-flash-lite",
            "segmentationBackend": "efficient_sam_onnx",
            "expectedLayerCount": 4,
            "runtime": {"platform": "Cloud Run"},
        },
        "cases": [
            {
                "caseId": "ARCH-01",
                "caseClass": "architecture",
                "inputHash": "input-hash-arch",
                "memoryTextHash": "memory-hash-arch",
                "sourceCase": "must-not-appear-in-sheet",
            },
            {
                "caseId": "NONARCH-01",
                "caseClass": "nonArchitecture",
                "inputHash": "input-hash-nonarch",
                "memoryTextHash": "memory-hash-nonarch",
                "sourceCase": "must-not-appear-in-sheet",
            },
        ],
    }


def test_build_run_sheet_generates_all_variants_and_uses_hashes_only() -> None:
    sheet = MODULE.build_run_sheet(_manifest())

    assert sheet["status"] == "pending_backend_artifacts"
    assert len(sheet["runs"]) == 12
    assert {run["runId"] for run in sheet["runs"]} == {
        f"{variant}-{case_id}-{attempt}"
        for variant in ("baseline", "candidate")
        for case_id in ("ARCH-01", "NONARCH-01")
        for attempt in range(1, 4)
    }
    candidate_arch = next(run for run in sheet["runs"] if run["runId"] == "candidate-ARCH-01-1")
    candidate_nonarch = next(
        run for run in sheet["runs"] if run["runId"] == "candidate-NONARCH-01-1"
    )
    assert candidate_arch["semanticProfile"] == "physical_layer_v3_architecture"
    assert candidate_nonarch["semanticProfile"] == "physical_layer_v2"
    assert all("sourceCase" not in run for run in sheet["runs"])
    assert all("memoryTextHash" in run and "memoryText" not in run for run in sheet["runs"])


def test_build_run_sheet_requires_a_candidate_profile_for_each_case_class() -> None:
    manifest = _manifest()
    comparison = manifest["comparison"]
    assert isinstance(comparison, dict)
    candidate = comparison["candidate"]
    assert isinstance(candidate, dict)
    candidate["semanticProfileByCaseClass"] = {"architecture": "architecture-only"}

    with pytest.raises(ValueError, match="semantic profile"):
        MODULE.build_run_sheet(manifest)
