"""多様なprivate実写セットでArtwork品質を比較する、Git管理外のReal AI評価runner。

Datasetは ``poc-images/quality-evaluation.json`` 等のprivate JSONで渡す。写真名、思い出文、
生成Artifact、Codexによる画像レビューは ``poc-output/`` にのみ保存し、Repositoryへcommitしない。
このrunnerは閾値を学習・変更しない。baseline / Semantic profileの比較根拠を残すだけである。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from ai.gemini import GeminiArtworkGenerator
from ai.types import InputPhoto
from app.config import Settings
from app.models.artwork import Artwork
from app.services.generator import build_generator
from app.services.validation import (
    check_artwork_rules,
    check_assets_present,
)
from frontend_handoff_bundle import (
    PocDebugObserver,
    write_frontend_handoff_bundle,
)

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
SUPPORTED_PROFILES = (
    "baseline",
    "physical_layer_v1",
    "physical_layer_v2",
    "physical_layer_v3_architecture",
)
DEFAULT_PROFILES = ("baseline", "physical_layer_v2")


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    photos: tuple[str, ...]
    memory_text: str
    scenario_tags: tuple[str, ...]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--photos-dir", type=Path, default=REPO_ROOT / "poc-images")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    parser.add_argument("--case-id")
    parser.add_argument("--profile", choices=SUPPORTED_PROFILES, action="append")
    parser.add_argument("--repeat", type=int, default=1)
    parser.add_argument("--max-e2e-runs", type=int, default=24)
    parser.add_argument("--preview-width-px", type=int, default=1600)
    return parser.parse_args()


def load_dataset(path: Path) -> tuple[EvaluationCase, ...]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("quality evaluation datasetを読めません") from exc
    items = payload.get("cases") if isinstance(payload, dict) else None
    if not isinstance(items, list) or not items:
        raise ValueError("dataset.casesには少なくとも1件必要です")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            raise TypeError("dataset.casesの各要素はobjectである必要があります")
        case_id = item.get("id")
        photos = item.get("photos")
        memory_text = item.get("memoryText")
        tags = item.get("scenarioTags", [])
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError(
                "dataset case idは重複しない非空stringである必要があります"
            )
        if (
            not isinstance(photos, list)
            or len(photos) != 5
            or not all(isinstance(photo, str) and photo for photo in photos)
        ):
            raise ValueError(f"{case_id}: MVP評価は正確に5枚のphotosを必要とします")
        if not isinstance(memory_text, str) or not memory_text.strip():
            raise ValueError(f"{case_id}: 非空memoryTextが必要です")
        if not isinstance(tags, list) or not all(
            isinstance(tag, str) and tag for tag in tags
        ):
            raise ValueError(f"{case_id}: scenarioTagsはstring配列である必要があります")
        seen_ids.add(case_id)
        cases.append(EvaluationCase(case_id, tuple(photos), memory_text, tuple(tags)))
    return tuple(cases)


def build_run_plan(
    cases: tuple[EvaluationCase, ...],
    profiles: tuple[str, ...],
    max_e2e_runs: int,
    repeat: int = 1,
) -> tuple[tuple[EvaluationCase, str, int], ...]:
    if max_e2e_runs < 1:
        raise ValueError("max-e2e-runsは1以上である必要があります")
    if repeat < 1:
        raise ValueError("repeatは1以上である必要があります")
    if any(profile not in SUPPORTED_PROFILES for profile in profiles):
        raise ValueError("未対応のprofileです")
    runs = tuple(
        (case, profile, attempt)
        for case in cases
        for profile in profiles
        for attempt in range(1, repeat + 1)
    )
    if len(runs) > max_e2e_runs:
        raise ValueError(
            f"計画されたE2E実行数 {len(runs)} が上限 {max_e2e_runs} を超えています"
        )
    return runs


def load_photos(case: EvaluationCase, photos_dir: Path) -> list[InputPhoto]:
    photos: list[InputPhoto] = []
    for filename in case.photos:
        path = photos_dir / filename
        mime_type = MIME_TYPES.get(path.suffix.lower())
        if mime_type is None or not path.is_file():
            raise ValueError(
                f"{case.case_id}: 画像が無い、またはP0形式外です: {filename}"
            )
        photos.append(InputPhoto(filename, mime_type, path.read_bytes()))
    return photos


def input_hash(photos: list[InputPhoto]) -> str:
    """順序を保った入力写真のSHA-256をprivate評価記録へ残す。"""

    photo_hashes = [hashlib.sha256(photo.data).hexdigest() for photo in photos]
    return hashlib.sha256("\n".join(photo_hashes).encode()).hexdigest()


def memory_text_hash(memory_text: str) -> str:
    """APIへ送る原文を保存せず、同一入力であることだけを追跡する。"""

    return hashlib.sha256(memory_text.encode()).hexdigest()


async def run(args: argparse.Namespace) -> int:
    cases = load_dataset(args.dataset)
    case_id = getattr(args, "case_id", None)
    if case_id is not None:
        cases = tuple(case for case in cases if case.case_id == case_id)
        if not cases:
            raise ValueError("--case-idに一致するdataset caseがありません")
    profiles = tuple(args.profile or DEFAULT_PROFILES)
    run_plan = build_run_plan(cases, profiles, args.max_e2e_runs, args.repeat)
    if args.preview_width_px <= 0:
        raise ValueError("preview-width-pxは正の値である必要があります")

    base_settings = Settings()
    if base_settings.mock_ai:
        raise ValueError("MOCK_AI=falseで実行してください")
    if not base_settings.gemini_api_key or not base_settings.efficientsam_model_path:
        raise ValueError("GEMINI_API_KEYとEFFICIENTSAM_MODEL_PATHが必要です")
    if base_settings.gemini_model != "gemini-3.5-flash-lite":
        raise ValueError(
            "品質評価はGEMINI_MODEL=gemini-3.5-flash-liteで実行する必要があります"
        )

    output = (
        args.output_dir
        / f"quality-evaluation-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    output.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    for ordinal, (case, profile, attempt) in enumerate(run_plan, start=1):
        case_output = output / f"{ordinal:02d}-{case.case_id}-{profile}-try{attempt}"
        case_output.mkdir()
        print(
            f"stage=generate case={case.case_id} profile={profile} attempt={attempt}",
            flush=True,
        )
        record = await run_case(
            case,
            profile,
            case_output,
            args.photos_dir,
            base_settings,
            args.preview_width_px,
            attempt,
        )
        records.append(record)

    summary = {
        "runLimit": args.max_e2e_runs,
        "plannedE2eRuns": len(run_plan),
        "repeat": args.repeat,
        "profiles": list(profiles),
        "geminiModel": base_settings.gemini_model,
        "qualityFeatureFlags": _quality_feature_flags(base_settings),
        "successCount": sum(record["success"] for record in records),
        "failureCount": sum(not record["success"] for record in records),
        "runs": records,
        "aggregate": _aggregate_records(records),
        "notes": (
            "診断値とCodexレビューの比較用。閾値の学習・自動適用・Mock fallbackは行わない。"
        ),
    }
    _write_json(output / "summary.json", summary)
    print(f"output={output}")
    print(f"success={summary['successCount']}/{len(run_plan)}")
    return 0 if summary["failureCount"] == 0 else 1


async def run_case(
    case: EvaluationCase,
    profile: str,
    output: Path,
    photos_dir: Path,
    base_settings: Settings,
    preview_width_px: int,
    attempt: int,
) -> dict[str, Any]:
    settings = base_settings.model_copy(update={"semantic_profile": profile})
    observer = PocDebugObserver(output / "debug")
    generator = build_generator(
        settings,
        observer=observer,
        subject_overlap_diagnostics=True,
    )
    if not isinstance(generator, GeminiArtworkGenerator):
        raise TypeError("MOCK_AI=falseのReal generatorを構成できません")
    photos = load_photos(case, photos_dir)
    evidence = {
        "photoCount": len(photos),
        "inputHash": input_hash(photos),
        "memoryTextHash": memory_text_hash(case.memory_text),
    }
    try:
        result = await generator.generate(photos, case.memory_text)
        artwork = Artwork.model_validate(result.artwork)
        errors = check_artwork_rules(artwork) + check_assets_present(
            artwork, result.assets
        )
        if errors:
            raise RuntimeError("artwork_or_assets_invalid")
        record: dict[str, Any] = {
            "caseId": case.case_id,
            "profile": profile,
            "attempt": attempt,
            "scenarioTags": list(case.scenario_tags),
            **evidence,
            "geminiModel": settings.gemini_model,
            "qualityFeatureFlags": _quality_feature_flags(settings),
            "success": True,
            "layerCount": len(artwork.layers),
            "metrics": asdict(generator.last_metrics),
        }
        write_frontend_handoff_bundle(
            output_dir=output,
            artwork=artwork,
            assets=result.assets,
            memory_text=case.memory_text,
            metrics=record,
            selected_photo_files=case.photos,
            preview_width_px=preview_width_px,
        )
        print(
            f"stage=generated case={case.case_id} success=true layers={len(artwork.layers)}",
            flush=True,
        )
        _write_review_template(output / "quality-review.json", record)
        return record
    except Exception as exc:  # noqa: BLE001 - PoCでは失敗種別を問わず記録して次ケースへ進む
        print(
            f"stage=failed case={case.case_id} error_type={type(exc).__name__}",
            flush=True,
        )
        metrics = asdict(generator.last_metrics)
        record = {
            "caseId": case.case_id,
            "profile": profile,
            "attempt": attempt,
            "scenarioTags": list(case.scenario_tags),
            **evidence,
            "geminiModel": settings.gemini_model,
            "qualityFeatureFlags": _quality_feature_flags(settings),
            "success": False,
            "errorType": type(exc).__name__,
            "failureStage": _failure_stage(metrics, type(exc).__name__),
            "metrics": metrics,
        }
        _write_json(output / "metrics.json", record)
        return record


def _write_review_template(path: Path, record: dict[str, Any]) -> None:
    candidates = record["metrics"].get("candidates", [])
    _write_json(
        path,
        {
            "caseId": record["caseId"],
            "profile": record["profile"],
            "scenarioTags": record["scenarioTags"],
            "reviewer": "codex",
            "rubric": {
                "semantic": "A/B/C",
                "source": "A/B/C",
                "bbox": "A/B/C",
                "mask": "A/B/C",
                "physicalLayer": "A/B/C",
                "composition": "A/B/C",
            },
            "candidates": [
                {
                    "candidateId": candidate["candidate_id"],
                    "label": candidate["label"],
                    "pipelineSuccess": candidate["success"],
                    "failureReason": candidate["failure_reason"],
                    "semanticRole": candidate["semantic_role"],
                    "maskCleanup": candidate["mask_cleanup"],
                    "diagnostics": {
                        "componentCount": candidate["mask_component_count"],
                        "largestComponentRatio": candidate[
                            "mask_largest_component_ratio"
                        ],
                        "interiorHoleCount": candidate["mask_interior_hole_count"],
                        "interiorHoleAreaRatio": candidate[
                            "mask_interior_hole_area_ratio"
                        ],
                        "bboxCoverage": candidate["mask_bbox_coverage"],
                        "borderTouch": candidate["mask_border_touch"],
                        "requiredComponentCount": candidate[
                            "coherent_group_required_component_count"
                        ],
                        "requiredComponentAcceptedCount": candidate[
                            "coherent_group_required_component_accepted_count"
                        ],
                        "componentExclusiveAreaRatios": [
                            {"componentId": component_id, "ratio": ratio}
                            for component_id, ratio in (
                                candidate[
                                    "coherent_group_component_exclusive_area_ratios"
                                ]
                                or ()
                            )
                        ],
                    },
                    "rating": None,
                    "failureStage": None,
                    "evidence": [],
                    "notes": None,
                }
                for candidate in candidates
            ],
        },
    )


def _quality_feature_flags(settings: Settings) -> dict[str, bool]:
    """採否待ちPoCの実効状態をprivate artifactへ残す。"""

    return {
        "closedHoleFillEnabled": settings.closed_hole_fill_enabled,
        "microIslandCleanupEnabled": settings.micro_island_cleanup_enabled,
        "compositionOverlapInstructionEnabled": settings.composition_overlap_instruction_enabled,
        "compositionForegroundBottomInstructionEnabled": (
            settings.composition_foreground_bottom_instruction_enabled
        ),
    }


def _aggregate_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Profile別の比較値だけをprivate summaryへ集約する。"""

    grouped: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        grouped.setdefault(record["profile"], []).append(record)
    return [
        {
            "profile": profile,
            "runCount": len(items),
            "successCount": sum(item["success"] for item in items),
            "architecturePrimaryAcceptedCount": sum(
                candidate["success"]
                and candidate.get("semantic_role") == "architecture_primary"
                for item in items
                for candidate in item["metrics"].get("candidates", [])
            ),
            "microIslandCleanupCount": sum(
                str(candidate.get("mask_cleanup", "")).startswith(
                    "removed_micro_islands:"
                )
                for item in items
                for candidate in item["metrics"].get("candidates", [])
            ),
            "failureStages": {
                stage: sum(item.get("failureStage") == stage for item in items)
                for stage in sorted(
                    {
                        str(item["failureStage"])
                        for item in items
                        if item.get("failureStage") is not None
                    }
                )
            },
        }
        for profile, items in sorted(grouped.items())
    ]


def _failure_stage(metrics: dict[str, Any], error_type: str) -> str:
    """例外本文を保存せず、最後に到達したAI stageを評価artifactへ残す。"""

    semantic_elapsed_ms = float(metrics.get("semantic_planning_elapsed_ms") or 0)
    composition_elapsed_ms = float(metrics.get("composition_elapsed_ms") or 0)
    candidates = metrics.get("candidates") or []
    if not candidates:
        return "semantic" if semantic_elapsed_ms > 0 else "source"
    if error_type == "RuntimeError" and composition_elapsed_ms > 0:
        return "contract"
    failed_candidates = [
        candidate for candidate in candidates if not candidate.get("success", False)
    ]
    if failed_candidates:
        return "mask"
    if composition_elapsed_ms == 0:
        return "layer"
    return "composition"


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
