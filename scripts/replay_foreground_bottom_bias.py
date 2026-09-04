"""保存済みE2E artifactだけで最前面subjectの下寄せを再生する。

Gemini・Segmentation・Semantic Planningは呼び出さない。通常Profileを変更する前に、
最前面subjectだけをCanvas下端へ寄せた場合の境界・bottom gap・subject overlapと
previewを固定artifactから比較するためのprivate PoCである。
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class LayerPlacement:
    candidate_id: str
    asset_id: str
    label: str
    kind: str
    layer_index: int
    x: float
    y: float
    scale: float
    width_px: int
    height_px: int
    canvas_aspect_ratio: float

    @property
    def display_height(self) -> float:
        return self.scale * self.canvas_aspect_ratio * self.height_px / self.width_px

    @property
    def bottom(self) -> float:
        return self.y + self.display_height / 2


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-root", action="append", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-front-bottom-gap", type=float, default=0.15)
    parser.add_argument("--preview-width-px", type=int, default=1024)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if not 0 <= args.max_front_bottom_gap <= 1:
        raise SystemExit("--max-front-bottom-gap は0..1で指定してください")
    if args.preview_width_px <= 0:
        raise SystemExit("--preview-width-px は正の整数で指定してください")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for root in args.input_root:
        for case_dir in sorted(path for path in root.iterdir() if path.is_dir()):
            row = replay_case(
                case_dir,
                args.output_dir,
                args.max_front_bottom_gap,
                args.preview_width_px,
            )
            if row is not None:
                rows.append(row)

    shifted = [row for row in rows if row["moved"]]
    summary = {
        "purpose": "最前面subjectだけを下端余白以内へ決定論的に寄せるprivate replay",
        "apiCalls": {"gemini": 0, "segmentation": 0, "semanticPlanning": 0},
        "inputRoots": [str(path) for path in args.input_root],
        "maxFrontBottomGap": args.max_front_bottom_gap,
        "evaluatedSuccessCases": len(rows),
        "movedCases": len(shifted),
        "allCandidateLayersWithinCanvas": all(
            row["candidateAllWithinCanvas"] for row in rows
        ),
        "frontIsLowestBefore": sum(row["frontIsLowestBefore"] for row in rows),
        "frontIsLowestAfter": sum(row["frontIsLowestAfter"] for row in rows),
        "overlapPixelsBefore": sum(row["overlapPixelsBefore"] for row in rows),
        "overlapPixelsAfter": sum(row["overlapPixelsAfter"] for row in rows),
        "cases": rows,
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {key: summary[key] for key in summary if key != "cases"}, ensure_ascii=False
        )
    )
    return 0


def replay_case(
    case_dir: Path,
    output_dir: Path,
    max_front_bottom_gap: float,
    preview_width_px: int,
) -> dict[str, Any] | None:
    metrics_path = case_dir / "metrics.json"
    physical_path = case_dir / "debug" / "physical-ready.json"
    artwork_path = case_dir / "artwork.json"
    if not (
        metrics_path.is_file() and physical_path.is_file() and artwork_path.is_file()
    ):
        return None
    metrics = load_json(metrics_path)
    if metrics.get("success") is not True:
        return None
    physical = load_json(physical_path)
    diagnostic_layers = physical["diagnostics"]["composition_layers"]
    candidate_layers = physical["layers"]
    artwork = load_json(artwork_path)
    placements = build_placements(artwork, candidate_layers, diagnostic_layers)
    subjects = [placement for placement in placements if placement.kind == "subject"]
    if not subjects:
        return None
    front = max(
        subjects, key=lambda placement: (placement.layer_index, placement.candidate_id)
    )
    lowered_y = min(
        1 - front.display_height / 2,
        max(front.y, 1 - max_front_bottom_gap - front.display_height / 2),
    )
    adjusted = {
        placement.candidate_id: placement
        if placement.candidate_id != front.candidate_id
        else LayerPlacement(
            **{**placement.__dict__, "y": lowered_y},
        )
        for placement in placements
    }
    adjusted_layers = list(adjusted.values())
    before_lowest = max(
        subjects, key=lambda placement: (placement.bottom, placement.candidate_id)
    )
    after_subjects = [
        placement for placement in adjusted_layers if placement.kind == "subject"
    ]
    after_lowest = max(
        after_subjects, key=lambda placement: (placement.bottom, placement.candidate_id)
    )
    case_output = output_dir / case_dir.name
    case_output.mkdir(exist_ok=True)
    overlap_before = render_preview_and_overlap(
        case_dir, placements, case_output / "baseline-preview.png", preview_width_px
    )
    overlap_after = render_preview_and_overlap(
        case_dir,
        adjusted_layers,
        case_output / "foreground-bottom-bias-preview.png",
        preview_width_px,
    )
    row = {
        "case": case_dir.name,
        "frontCandidateId": front.candidate_id,
        "frontLabel": front.label,
        "frontBottomGapBefore": 1 - front.bottom,
        "frontBottomGapAfter": 1 - adjusted[front.candidate_id].bottom,
        "moved": lowered_y > front.y,
        "yDelta": lowered_y - front.y,
        "frontIsLowestBefore": before_lowest.candidate_id == front.candidate_id,
        "frontIsLowestAfter": after_lowest.candidate_id == front.candidate_id,
        "candidateAllWithinCanvas": all(
            within_canvas(placement) for placement in adjusted_layers
        ),
        "overlapPixelsBefore": overlap_before,
        "overlapPixelsAfter": overlap_after,
    }
    (case_output / "metrics.json").write_text(
        json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return row


def build_placements(
    artwork: dict[str, Any],
    candidate_layers: list[dict[str, Any]],
    diagnostic_layers: list[dict[str, Any]],
) -> list[LayerPlacement]:
    canvas_aspect_ratio = float(artwork["canvas"]["aspectRatio"])
    candidate_by_label = {layer["label"]: layer for layer in candidate_layers}
    diagnostic_by_id = {layer["candidate_id"]: layer for layer in diagnostic_layers}
    if len(candidate_by_label) != len(candidate_layers):
        raise ValueError(
            "candidate labelが重複しているためartifactを安全に対応付けできません"
        )
    placements: list[LayerPlacement] = []
    for layer in artwork["layers"]:
        candidate = candidate_by_label.get(layer["label"])
        if candidate is None:
            raise ValueError(
                f"Artwork Layerのcandidate対応が見つかりません: {layer['label']}"
            )
        diagnostic = diagnostic_by_id[candidate["candidateId"]]
        asset = layer["asset"]
        placements.append(
            LayerPlacement(
                candidate_id=candidate["candidateId"],
                asset_id=asset["assetId"],
                label=layer["label"],
                kind=candidate["kind"],
                layer_index=layer["layerIndex"],
                x=float(layer["x"]),
                y=float(layer["y"]),
                scale=float(layer["scale"]),
                width_px=int(asset["widthPx"]),
                height_px=int(asset["heightPx"]),
                canvas_aspect_ratio=canvas_aspect_ratio,
            )
        )
        if abs(placements[-1].bottom - float(diagnostic["bottom"])) > 1e-6:
            raise ValueError(
                f"Composition diagnosticとArtworkが一致しません: {candidate['candidateId']}"
            )
    return placements


def render_preview_and_overlap(
    case_dir: Path,
    placements: list[LayerPlacement],
    output_path: Path,
    width_px: int,
) -> int:
    aspect_ratio = float(load_json(case_dir / "artwork.json")["canvas"]["aspectRatio"])
    height_px = round(width_px / aspect_ratio)
    canvas = Image.new("RGBA", (width_px, height_px), "#F7F3EA")
    subject_masks: list[np.ndarray] = []
    for placement in sorted(placements, key=lambda item: item.layer_index):
        image = Image.open(asset_path(case_dir, placement.asset_id)).convert("RGBA")
        display_width = max(1, round(placement.scale * width_px))
        display_height = max(1, round(display_width * image.height / image.width))
        image = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        left = round(placement.x * width_px - display_width / 2)
        top = round(placement.y * height_px - display_height / 2)
        canvas.alpha_composite(image, (left, top))
        if placement.kind == "subject":
            alpha = Image.new("L", (width_px, height_px), 0)
            alpha.paste(image.getchannel("A"), (left, top))
            subject_masks.append(np.asarray(alpha) > 0)
    canvas.save(output_path, format="PNG")
    return sum(
        int(np.count_nonzero(left & right))
        for index, left in enumerate(subject_masks)
        for right in subject_masks[index + 1 :]
    )


def asset_path(case_dir: Path, asset_id: str) -> Path:
    matches = list((case_dir / "assets").glob(f"{asset_id}.*"))
    if len(matches) != 1:
        raise ValueError(f"assetが一意に見つかりません: {asset_id}")
    return matches[0]


def within_canvas(placement: LayerPlacement) -> bool:
    half_width = placement.scale / 2
    half_height = placement.display_height / 2
    return (
        placement.x - half_width >= -1e-9
        and placement.x + half_width <= 1 + 1e-9
        and placement.y - half_height >= -1e-9
        and placement.y + half_height <= 1 + 1e-9
    )


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
