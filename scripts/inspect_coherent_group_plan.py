"""保存済みcoherent_group Planのbbox関係をprivate artifactとして数値化する。

Semantic Planを変更せず、component MaskやGeminiを再実行しない。primary bboxにrequired
componentがどの程度含まれるかを、人手G1レビュー用の事実として記録する。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--plan-dir",
        type=Path,
        required=True,
        help="semantic-plan.jsonを含むGit管理外のG1 output directory",
    )
    parser.add_argument(
        "--review-image",
        type=Path,
        default=None,
        help="任意。plan-dirからの相対pathで、既存bbox画像の縮小コピーを作る",
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=1920,
        help="縮小コピーの最大辺px（既定: 1920）",
    )
    return parser.parse_args()


def area(box: dict[str, int]) -> int:
    return max(0, box["x_max"] - box["x_min"]) * max(0, box["y_max"] - box["y_min"])


def intersection_area(left: dict[str, int], right: dict[str, int]) -> int:
    return area(
        {
            "x_min": max(left["x_min"], right["x_min"]),
            "y_min": max(left["y_min"], right["y_min"]),
            "x_max": min(left["x_max"], right["x_max"]),
            "y_max": min(left["y_max"], right["y_max"]),
        }
    )


def relationship(primary: dict[str, object], component: dict[str, object]) -> dict[str, object]:
    primary_box = primary["box_2d"]
    component_box = component["box_2d"]
    if not isinstance(primary_box, dict) or not isinstance(component_box, dict):
        raise TypeError("component box_2dが不正です")
    primary_area = area(primary_box)
    component_area = area(component_box)
    overlap = intersection_area(primary_box, component_box)
    union = primary_area + component_area - overlap
    return {
        "componentId": component["component_id"],
        "label": component["label"],
        "required": component["required"],
        "relationToPrimary": component["relation_to_primary"],
        "primaryContainmentRatio": overlap / component_area if component_area else 0,
        "bboxIou": overlap / union if union else 0,
        "overlapArea": overlap,
        "componentBboxArea": component_area,
    }


def inspect_plan(plan: dict[str, object]) -> dict[str, object]:
    candidates = plan.get("candidates")
    if not isinstance(candidates, list):
        raise TypeError("semantic-plan.jsonのcandidatesが不正です")
    groups: list[dict[str, object]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict) or candidate.get("extraction_intent") != "coherent_group":
            continue
        components = candidate.get("components")
        if not isinstance(components, list):
            raise TypeError("coherent_groupのcomponentsが不正です")
        primary_components = [
            component
            for component in components
            if isinstance(component, dict) and component.get("relation_to_primary") == "primary"
        ]
        if len(primary_components) != 1:
            raise ValueError("coherent_groupにはprimary componentが1件必要です")
        primary = primary_components[0]
        groups.append(
            {
                "candidateId": candidate["candidate_id"],
                "label": candidate["label"],
                "primaryComponentId": primary["component_id"],
                "otherComponents": [
                    relationship(primary, component)
                    for component in components
                    if component is not primary
                ],
            }
        )
    return {
        "purpose": "G1 human review only; values do not accept or reject candidates automatically.",
        "coherentGroups": groups,
    }


def render_review_image(plan_dir: Path, review_image: Path, max_side: int) -> Path:
    if max_side < 1:
        raise ValueError("--max-sideは正の整数で指定してください")
    source_path = review_image if review_image.is_absolute() else plan_dir / review_image
    if not source_path.is_file() or plan_dir not in source_path.parents:
        raise ValueError("--review-imageはplan-dir配下の既存画像を指定してください")
    output_dir = plan_dir / "component-review-preview"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / source_path.name
    with Image.open(source_path) as image:
        preview = image.convert("RGB")
        preview.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
        preview.save(output_path, "PNG")
    return output_path


def run(args: argparse.Namespace) -> int:
    plan_path = args.plan_dir / "semantic-plan.json"
    if not plan_path.is_file():
        raise ValueError("--plan-dirにsemantic-plan.jsonがありません")
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    report = inspect_plan(plan)
    output = args.plan_dir / "component-bbox-review.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"output={output}")
    print(f"coherent_groups={len(report['coherentGroups'])}")
    if args.review_image is not None:
        print(
            "review_preview="
            f"{render_review_image(args.plan_dir, args.review_image, args.max_side)}"
        )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(run(parse_args()))
    except (TypeError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
