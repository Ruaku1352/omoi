"""private実写評価runnerの副作用なしUnit Test。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

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

    assert [profile for _case, profile in plan] == ["baseline", "physical_layer_v1"]
    with pytest.raises(ValueError, match="上限"):
        module.build_run_plan(cases, ("baseline", "physical_layer_v1"), 1)
