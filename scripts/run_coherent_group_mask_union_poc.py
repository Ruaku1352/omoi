"""承認済みcoherent_groupを、保存済みSemantic Planから実Maskへ変換するG3 PoC。

Geminiは呼ばない。EfficientSAM-Ti ONNXで各componentをsegmentし、承認済みcomponentだけを
橋渡しや微小island cleanupなしで1つのRGBA Layerへunionする。
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.gemini import Composer, GeminiArtworkGenerator, SemanticPlanner
from ai.image_ops import union_masks
from ai.internal_models import (
    CompositionPlan,
    SegmentationComponent,
    SemanticPlan,
    VisualElementCandidate,
)
from ai.quality import MaskQuality
from ai.segmentation import (
    LazyEfficientSamOnnxSegmenter,
    SegmentationResult,
)
from ai.types import InputPhoto
from app.config import Settings
from app.models.artwork import Artwork
from app.services.validation import check_artwork_rules, check_assets_present

MIME_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--plan-dir", type=Path, required=True)
    parser.add_argument("--candidate-id", action="append", required=True)
    parser.add_argument(
        "--gap-closure-px",
        type=int,
        default=0,
        help="union後に閉じる細い透明gapの最大幅。0はclosingなし。",
    )
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    return parser.parse_args()


def load_photos(case_dir: Path) -> list[InputPhoto]:
    if not case_dir.is_dir():
        raise ValueError("--case-dir が存在しません")
    photos = [
        InputPhoto(path.name, MIME_TYPES[path.suffix.lower()], path.read_bytes())
        for path in sorted(case_dir.iterdir())
        if path.is_file() and path.suffix.lower() in MIME_TYPES
    ]
    if len(photos) != 5:
        raise ValueError("G3 PoCは正確に5枚のJPEG / PNG / WebPを必要とします")
    return photos


def input_hash(photos: list[InputPhoto]) -> str:
    hashes = [hashlib.sha256(photo.data).hexdigest() for photo in photos]
    return hashlib.sha256("\n".join(hashes).encode()).hexdigest()


class SavedPlanPlanner(SemanticPlanner):
    def __init__(self, plan: SemanticPlan) -> None:
        self._plan = plan

    async def plan(
        self, images: list[Image.Image], memory_text: str | None
    ) -> SemanticPlan:
        del images, memory_text
        return self._plan


class DeterministicComposer(Composer):
    @staticmethod
    def _plan(layers) -> CompositionPlan:
        return CompositionPlan.model_validate(
            {
                "layers": [
                    {
                        "candidate_id": layer.candidate_id,
                        "x": 0.5,
                        "y": 0.65,
                        "scale": 0.5,
                        "order": index,
                    }
                    for index, layer in enumerate(layers)
                ]
            }
        )

    async def compose(self, layers) -> CompositionPlan:
        return self._plan(layers)

    async def recompose(self, layers, *, max_bottom_gap: float) -> CompositionPlan:
        del max_bottom_gap
        return self._plan(layers)


class ComponentMaskRecorder:
    """G3の各component Maskをprivate artifactとして残すobserver。"""

    def __init__(self) -> None:
        self._masks: dict[tuple[str, str], np.ndarray] = {}

    def semantic_plan(self, plan: SemanticPlan, images: list[Image.Image]) -> None:
        del plan, images

    def segmentation_attempt(
        self,
        *,
        candidate: VisualElementCandidate,
        component: SegmentationComponent,
        source_photo_index: int,
        image: Image.Image,
        result: SegmentationResult,
        quality: MaskQuality,
        attempt: int,
    ) -> None:
        del source_photo_index, image, attempt
        if quality.accepted:
            self._masks[(candidate.candidate_id, component.component_id)] = result.mask

    def component_masks(
        self, candidate: VisualElementCandidate
    ) -> dict[str, np.ndarray]:
        return {
            component.component_id: self._masks[
                (candidate.candidate_id, component.component_id)
            ]
            for component in candidate.components
            if (candidate.candidate_id, component.component_id) in self._masks
        }


def write_alpha_preview(png: bytes, path: Path) -> None:
    """透明部分が残っていることを人が確認できるチェッカー背景previewを作る。"""
    with Image.open(BytesIO(png)) as layer:
        layer = layer.convert("RGBA")
        preview = Image.new("RGB", layer.size, "#e5e7eb")
        draw = ImageDraw.Draw(preview)
        tile_size = 32
        for y in range(0, layer.height, tile_size):
            for x in range(0, layer.width, tile_size):
                if (x // tile_size + y // tile_size) % 2:
                    draw.rectangle(
                        (x, y, x + tile_size - 1, y + tile_size - 1), fill="#9ca3af"
                    )
        preview.paste(layer, mask=layer.getchannel("A"))
        preview.save(path, "PNG")


def write_mask(mask: np.ndarray, path: Path) -> None:
    Image.fromarray(np.asarray(mask, dtype=np.uint8) * 255, mode="L").save(path, "PNG")


def write_component_masks(
    output: Path, plan: SemanticPlan, recorder: ComponentMaskRecorder
) -> list[dict[str, object]]:
    """Mask単位の面積と、他componentと重ならない寄与を記録する。"""

    mask_dir = output / "component-masks"
    mask_dir.mkdir()
    records: list[dict[str, object]] = []
    for candidate in plan.candidates:
        masks = recorder.component_masks(candidate)
        for component in candidate.components:
            if component.required and component.component_id not in masks:
                raise RuntimeError(
                    f"required component Maskが記録されませんでした: {candidate.candidate_id}/{component.component_id}"
                )
        all_masks = list(masks.values())
        combined = union_masks(all_masks) if all_masks else None
        for component in candidate.components:
            mask = masks.get(component.component_id)
            if mask is None or combined is None:
                continue
            others = [
                other
                for component_id, other in masks.items()
                if component_id != component.component_id
            ]
            other_union = union_masks(others) if others else np.zeros_like(mask)
            exclusive = np.logical_and(mask, np.logical_not(other_union))
            filename = f"{candidate.candidate_id}--{component.component_id}.png"
            write_mask(mask, mask_dir / filename)
            records.append(
                {
                    "candidateId": candidate.candidate_id,
                    "componentId": component.component_id,
                    "required": component.required,
                    "maskFile": str((mask_dir / filename).relative_to(output)),
                    "foregroundPixels": int(mask.sum()),
                    "exclusivePixels": int(exclusive.sum()),
                    "exclusiveRatioOfUnion": float(exclusive.sum() / combined.sum()),
                }
            )
    return records


def load_approved_candidates(
    plan_dir: Path, candidate_ids: list[str], photos: list[InputPhoto]
) -> SemanticPlan:
    run_path = plan_dir / "run.json"
    plan_path = plan_dir / "semantic-plan.json"
    if not run_path.is_file() or not plan_path.is_file():
        raise ValueError("--plan-dir にrun.jsonとsemantic-plan.jsonが必要です")
    run = json.loads(run_path.read_text(encoding="utf-8"))
    if run.get("inputHash") != input_hash(photos):
        raise ValueError("保存済みSemantic Planと入力写真のhashが一致しません")
    saved_plan = SemanticPlan.model_validate_json(plan_path.read_text(encoding="utf-8"))
    by_id = {candidate.candidate_id: candidate for candidate in saved_plan.candidates}
    selected: list[VisualElementCandidate] = []
    for candidate_id in candidate_ids:
        candidate = by_id.get(candidate_id)
        if candidate is None:
            raise ValueError(f"candidateが見つかりません: {candidate_id}")
        if candidate.extraction_intent != "coherent_group":
            raise ValueError(f"coherent_groupではありません: {candidate_id}")
        selected.append(candidate)
    return SemanticPlan(memory_summary=saved_plan.memory_summary, candidates=selected)


async def run(args: argparse.Namespace) -> int:
    if args.gap_closure_px < 0:
        raise ValueError("--gap-closure-pxは0以上で指定してください")
    print("stage=load_inputs", flush=True)
    photos = load_photos(args.case_dir)
    plan = load_approved_candidates(args.plan_dir, args.candidate_id, photos)
    settings = Settings()
    if settings.mock_ai:
        raise ValueError("MOCK_AI=falseで実行してください")
    if settings.efficientsam_model_path is None:
        raise ValueError("EFFICIENTSAM_MODEL_PATHが未設定です")

    recorder = ComponentMaskRecorder()
    generator = GeminiArtworkGenerator(
        api_key="g3-replay-no-gemini-request",
        model="g3-replay-no-gemini-request",
        segmenter=LazyEfficientSamOnnxSegmenter(
            settings.efficientsam_model_path, settings.segmentation_max_side
        ),
        candidate_count=len(plan.candidates),
        target_layer_min=len(plan.candidates),
        target_layer_max=len(plan.candidates),
        segmentation_max_retries=settings.segmentation_max_retries,
        analysis_max_side=settings.gemini_analysis_max_side,
        layer_padding_px=settings.layer_padding_px,
        layout_min_scale=settings.layout_min_scale,
        layout_max_scale=settings.layout_max_scale,
        canvas_aspect_ratio=settings.artwork_canvas_aspect_ratio,
        gemini_request_timeout_ms=settings.gemini_request_timeout_ms,
        semantic_profile="physical_layer_v2",
        quality_diagnostics_max_side=settings.quality_diagnostics_max_side,
        physical_scene_anchor_min_scale=settings.physical_scene_anchor_min_scale,
        physical_max_bottom_gap=settings.physical_max_bottom_gap,
        architecture_micro_island_max_area_ratio=settings.architecture_micro_island_max_area_ratio,
        mask_micro_island_max_area_ratio=settings.mask_micro_island_max_area_ratio,
        coherent_group_gap_closure_px=args.gap_closure_px,
        semantic_planner=SavedPlanPlanner(plan),
        composer=DeterministicComposer(),
        observer=recorder,
    )
    print("stage=segment_components", flush=True)
    result = await generator.generate(photos, memory_text=None)
    artwork = Artwork.model_validate(result.artwork)
    errors = check_artwork_rules(artwork) + check_assets_present(artwork, result.assets)
    if errors:
        raise RuntimeError("; ".join(errors))

    output = (
        args.output_dir
        / f"coherent-group-mask-union-{datetime.now(UTC).strftime('%Y%m%d-%H%M%S')}"
    )
    print("stage=write_artifact", flush=True)
    output.mkdir(parents=True)
    layers_dir = output / "layers"
    layers_dir.mkdir()
    previews_dir = output / "previews"
    previews_dir.mkdir()
    component_records = write_component_masks(output, plan, recorder)
    assets = {asset.asset_id: asset for asset in result.assets}
    preview_files: dict[str, str] = {}
    for layer in artwork.layers:
        asset = assets[layer.asset.asset_id]
        (layers_dir / f"{layer.source_layer_id}.png").write_bytes(asset.data)
        preview_path = previews_dir / f"{layer.source_layer_id}.png"
        write_alpha_preview(asset.data, preview_path)
        preview_files[layer.source_layer_id] = str(preview_path.relative_to(output))
    record = {
        "sourcePlanDir": str(args.plan_dir),
        "inputHash": input_hash(photos),
        "candidateIds": args.candidate_id,
        "semanticProfile": "physical_layer_v2",
        "segmentationBackend": "efficient_sam_onnx",
        "geminiCalled": False,
        "gapClosurePx": args.gap_closure_px,
        "closedHoleFill": "subject componentとunion後の、外側背景へ到達できない透明領域を充填",
        "layerCount": len(artwork.layers),
        "previewFiles": preview_files,
        "candidateMetrics": [
            metric.__dict__ for metric in generator.last_metrics.candidates
        ],
        "componentMasks": component_records,
        "notes": "Approved coherent_group components were unioned without bridging or micro-island cleanup. Closed interior holes were filled mechanically.",
    }
    (output / "run.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (output / "artwork.json").write_text(
        json.dumps(result.artwork, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"output={output}")
    print(f"layers={len(artwork.layers)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(run(parse_args())))
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
