"""多様なprivate実写セットでArtwork品質を比較する、Git管理外のReal AI評価runner。

Datasetは ``poc-images/quality-evaluation.json`` 等のprivate JSONで渡す。写真名、思い出文、
生成Artifact、Codexによる画像レビューは ``poc-output/`` にのみ保存し、Repositoryへcommitしない。
このrunnerは閾値を学習・変更しない。baseline / Semantic profileの比較根拠を残すだけである。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
SCRIPTS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(SCRIPTS_DIR))

from frontend_handoff_bundle import PocDebugObserver, write_frontend_handoff_bundle  # noqa: E402

from ai.gemini import GeminiArtworkGenerator  # noqa: E402
from ai.types import InputPhoto  # noqa: E402
from app.config import Settings  # noqa: E402
from app.models.artwork import Artwork  # noqa: E402
from app.services.generator import build_generator  # noqa: E402
from app.services.validation import check_artwork_rules, check_assets_present  # noqa: E402

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}
SUPPORTED_PROFILES = ("baseline", "physical_layer_v1")


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
    parser.add_argument("--profile", choices=SUPPORTED_PROFILES, action="append")
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
            raise ValueError("dataset.casesの各要素はobjectである必要があります")
        case_id = item.get("id")
        photos = item.get("photos")
        memory_text = item.get("memoryText")
        tags = item.get("scenarioTags", [])
        if not isinstance(case_id, str) or not case_id or case_id in seen_ids:
            raise ValueError("dataset case idは重複しない非空stringである必要があります")
        if not isinstance(photos, list) or len(photos) != 5 or not all(
            isinstance(photo, str) and photo for photo in photos
        ):
            raise ValueError(f"{case_id}: MVP評価は正確に5枚のphotosを必要とします")
        if not isinstance(memory_text, str) or not memory_text.strip():
            raise ValueError(f"{case_id}: 非空memoryTextが必要です")
        if not isinstance(tags, list) or not all(isinstance(tag, str) and tag for tag in tags):
            raise ValueError(f"{case_id}: scenarioTagsはstring配列である必要があります")
        seen_ids.add(case_id)
        cases.append(EvaluationCase(case_id, tuple(photos), memory_text, tuple(tags)))
    return tuple(cases)


def build_run_plan(
    cases: tuple[EvaluationCase, ...], profiles: tuple[str, ...], max_e2e_runs: int
) -> tuple[tuple[EvaluationCase, str], ...]:
    if max_e2e_runs < 1:
        raise ValueError("max-e2e-runsは1以上である必要があります")
    if any(profile not in SUPPORTED_PROFILES for profile in profiles):
        raise ValueError("未対応のprofileです")
    runs = tuple((case, profile) for case in cases for profile in profiles)
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
            raise ValueError(f"{case.case_id}: 画像が無い、またはP0形式外です: {filename}")
        photos.append(InputPhoto(filename, mime_type, path.read_bytes()))
    return photos


async def run(args: argparse.Namespace) -> int:
    cases = load_dataset(args.dataset)
    profiles = tuple(args.profile or SUPPORTED_PROFILES)
    run_plan = build_run_plan(cases, profiles, args.max_e2e_runs)
    if args.preview_width_px <= 0:
        raise ValueError("preview-width-pxは正の値である必要があります")

    base_settings = Settings()
    if base_settings.mock_ai:
        raise ValueError("MOCK_AI=falseで実行してください")
    if not base_settings.gemini_api_key or not base_settings.efficientsam_model_path:
        raise ValueError("GEMINI_API_KEYとEFFICIENTSAM_MODEL_PATHが必要です")

    output = args.output_dir / f"quality-evaluation-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output.mkdir(parents=True)
    records: list[dict[str, Any]] = []
    for ordinal, (case, profile) in enumerate(run_plan, start=1):
        case_output = output / f"{ordinal:02d}-{case.case_id}-{profile}"
        case_output.mkdir()
        record = await run_case(
            case,
            profile,
            case_output,
            args.photos_dir,
            base_settings,
            args.preview_width_px,
        )
        records.append(record)

    summary = {
        "runLimit": args.max_e2e_runs,
        "plannedE2eRuns": len(run_plan),
        "profiles": list(profiles),
        "successCount": sum(record["success"] for record in records),
        "failureCount": sum(not record["success"] for record in records),
        "runs": records,
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
) -> dict[str, Any]:
    settings = base_settings.model_copy(update={"semantic_profile": profile})
    observer = PocDebugObserver(output / "debug")
    generator = build_generator(settings, observer=observer)
    if not isinstance(generator, GeminiArtworkGenerator):
        raise RuntimeError("MOCK_AI=falseのReal generatorを構成できません")
    try:
        result = await generator.generate(load_photos(case, photos_dir), case.memory_text)
        artwork = Artwork.model_validate(result.artwork)
        errors = check_artwork_rules(artwork) + check_assets_present(artwork, result.assets)
        if errors:
            raise RuntimeError("artwork_or_assets_invalid")
        record: dict[str, Any] = {
            "caseId": case.case_id,
            "profile": profile,
            "scenarioTags": list(case.scenario_tags),
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
        _write_review_template(output / "quality-review.json", record)
        return record
    except Exception as exc:
        record = {
            "caseId": case.case_id,
            "profile": profile,
            "scenarioTags": list(case.scenario_tags),
            "success": False,
            "errorType": type(exc).__name__,
            "metrics": asdict(generator.last_metrics),
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
                    "diagnostics": {
                        "componentCount": candidate["mask_component_count"],
                        "largestComponentRatio": candidate["mask_largest_component_ratio"],
                        "bboxCoverage": candidate["mask_bbox_coverage"],
                        "borderTouch": candidate["mask_border_touch"],
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


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
