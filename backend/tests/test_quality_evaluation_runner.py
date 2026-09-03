"""private実写評価runnerの副作用なしUnit Test。"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

import pytest


def _module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "run_quality_evaluation.py"
    spec = importlib.util.spec_from_file_location("quality_evaluation", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _dataset(case_id: str = "occluded-building") -> dict:
    return {
        "cases": [
            {
                "id": case_id,
                "photos": [f"photo-{index}.jpg" for index in range(1, 6)],
                "memoryText": "大切な旅行の日。",
                "scenarioTags": ["occluded-building", "complex-background"],
            }
        ]
    }


def test_dataset_requires_five_photos_and_nonempty_memory_text(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(_dataset()), encoding="utf-8")

    cases = module.load_dataset(path)

    assert cases[0].case_id == "occluded-building"
    assert len(cases[0].photos) == 5
    invalid = _dataset()
    invalid["cases"][0]["photos"] = ["one.jpg"]
    path.write_text(json.dumps(invalid), encoding="utf-8")
    with pytest.raises(ValueError, match="正確に5枚"):
        module.load_dataset(path)


def test_run_plan_has_explicit_limit_and_profile_comparison(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "dataset.json"
    path.write_text(json.dumps(_dataset()), encoding="utf-8")
    cases = module.load_dataset(path)

    plan = module.build_run_plan(cases, ("baseline", "physical_layer_v1"), 2)

    assert [profile for _case, profile, _attempt in plan] == ["baseline", "physical_layer_v1"]
    with pytest.raises(ValueError, match="上限"):
        module.build_run_plan(cases, ("baseline", "physical_layer_v1"), 1)


def test_private_input_evidence_hashes_preserve_photo_order_and_hide_memory_text() -> None:
    module = _module()
    first = module.InputPhoto("one.jpg", "image/jpeg", b"one")
    second = module.InputPhoto("two.jpg", "image/jpeg", b"two")

    assert module.input_hash([first, second]) != module.input_hash([second, first])
    assert module.memory_text_hash("思い出") == module.memory_text_hash("思い出")
    assert module.memory_text_hash("思い出") != module.memory_text_hash("別の思い出")


def test_runner_rejects_non_flash_lite_before_any_real_ai_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    dataset_path = tmp_path / "dataset.json"
    dataset_path.write_text(json.dumps(_dataset()), encoding="utf-8")
    monkeypatch.setattr(
        module,
        "Settings",
        lambda: SimpleNamespace(
            mock_ai=False,
            gemini_api_key="test-key",
            efficientsam_model_path=tmp_path / "efficient-sam.onnx",
            gemini_model="gemini-3.7-flash",
        ),
    )
    args = Namespace(
        dataset=dataset_path,
        photos_dir=tmp_path,
        output_dir=tmp_path / "output",
        profile=["physical_layer_v2"],
        repeat=1,
        max_e2e_runs=1,
        preview_width_px=1600,
    )

    with pytest.raises(ValueError, match="gemini-3.5-flash-lite"):
        asyncio.run(module.run(args))


def test_failure_stage_records_the_last_reached_pipeline_stage() -> None:
    module = _module()

    assert (
        module._failure_stage(
            {"semantic_planning_elapsed_ms": 12, "composition_elapsed_ms": 0, "candidates": []},
            "AiError",
        )
        == "semantic"
    )
    assert (
        module._failure_stage(
            {"semantic_planning_elapsed_ms": 0, "composition_elapsed_ms": 0, "candidates": []},
            "ValueError",
        )
        == "source"
    )
    assert (
        module._failure_stage(
            {
                "semantic_planning_elapsed_ms": 12,
                "composition_elapsed_ms": 0,
                "candidates": [{"success": False}],
            },
            "AiError",
        )
        == "mask"
    )
    assert (
        module._failure_stage(
            {
                "semantic_planning_elapsed_ms": 12,
                "composition_elapsed_ms": 20,
                "candidates": [{"success": True}],
            },
            "RuntimeError",
        )
        == "contract"
    )


def test_review_template_includes_coherent_group_component_evidence(tmp_path: Path) -> None:
    module = _module()
    path = tmp_path / "quality-review.json"
    record = {
        "caseId": "food",
        "profile": "coherent_group_planning",
        "attempt": 1,
        "scenarioTags": ["food", "coherent_group"],
        "failureStage": None,
        "metrics": {
            "candidates": [
                {
                    "candidate_id": "montblanc-and-plate",
                    "label": "モンブランと皿",
                    "success": True,
                    "failure_reason": None,
                    "semantic_role": "general",
                    "mask_cleanup": "retained_coherent_group:2",
                    "mask_component_count": 2,
                    "mask_largest_component_ratio": 0.7,
                    "mask_interior_hole_count": 0,
                    "mask_interior_hole_area_ratio": 0,
                    "mask_bbox_coverage": 0.8,
                    "mask_border_touch": False,
                    "coherent_group_required_component_count": 2,
                    "coherent_group_required_component_accepted_count": 2,
                    "coherent_group_component_exclusive_area_ratios": [
                        ("plate", 0.7),
                        ("montblanc", 0.3),
                    ],
                }
            ]
        },
    }

    module._write_review_template(path, record)

    candidate = json.loads(path.read_text(encoding="utf-8"))["candidates"][0]
    diagnostics = candidate["diagnostics"]
    assert diagnostics["requiredComponentCount"] == 2
    assert diagnostics["requiredComponentAcceptedCount"] == 2
    assert diagnostics["componentExclusiveAreaRatios"] == [
        {"componentId": "plate", "ratio": 0.7},
        {"componentId": "montblanc", "ratio": 0.3},
    ]
