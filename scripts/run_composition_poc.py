"""既存のRGBA Layer AssetsだけでArtwork Compositionを検証するPoC runner。

Semantic PlanningとEfficientSAMは再実行しない。Geminiには最小の配置情報だけを
Structured Outputで要求し、Artwork Dataと2D PreviewはPythonで決定論的に組み立てる。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import math
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

from google import genai
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.config import Settings  # noqa: E402
from app.models.artwork import Artwork  # noqa: E402


@dataclass(frozen=True)
class FixedLayerSpec:
    layer_id: str
    label: str
    source_photo_filename: str


# Layer PNGそのものを目視した固定メタデータ。Semantic Plannerを再実行して得た情報ではない。
FIXED_LAYERS = (
    FixedLayerSpec("layer-01", "着物姿の人物と扇子", "IMG_5041.jpg"),
    FixedLayerSpec("layer-02", "庭園の噴水", "IMG_2612.jpg"),
    FixedLayerSpec("layer-03", "牡丹の絵付け", "IMG_2844.png"),
    FixedLayerSpec("layer-04", "木造建築模型", "IMG_2718.png"),
    FixedLayerSpec("layer-05", "モンブラン", "IMG_2853.jpg"),
)


@dataclass(frozen=True)
class LayerInput:
    layer_id: str
    label: str
    source_photo_filename: str
    image: Image.Image

    @property
    def width_px(self) -> int:
        return self.image.width

    @property
    def height_px(self) -> int:
        return self.image.height


class CompositionPlacement(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    layer_id: str = Field(alias="layerId", min_length=1)
    x: float
    y: float
    scale: float
    front_to_back_order: int = Field(alias="frontToBackOrder")


class CompositionResponse(BaseModel):
    layers: list[CompositionPlacement] = Field(min_length=1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--layers-dir",
        type=Path,
        default=REPO_ROOT / "poc-output" / "20260824-200419" / "layers",
    )
    parser.add_argument("--photos-dir", type=Path, default=REPO_ROOT / "poc-images")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    # 手動REST Smoke Testで確認済みのPoC専用暫定モデル。最終採用モデルではない。
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    # PoCで見比べやすい4:3 Landscape。Productの固定値ではなくCLIで差し替え可能。
    parser.add_argument("--canvas-aspect-ratio", type=float, default=4 / 3)
    parser.add_argument("--preview-width-px", type=int, default=1600)
    return parser.parse_args()


def load_fixed_layers(layers_dir: Path) -> list[LayerInput]:
    layers: list[LayerInput] = []
    for index, spec in enumerate(FIXED_LAYERS, start=1):
        path = layers_dir / f"{index:02d}.png"
        if not path.is_file():
            raise ValueError(f"固定Composition入力Layerが見つかりません: {path.name}")
        with Image.open(path) as source:
            image = source.convert("RGBA")
        if image.getchannel("A").getbbox() is None:
            raise ValueError(f"透過Layerに不透明ピクセルがありません: {path.name}")
        layers.append(LayerInput(spec.layer_id, spec.label, spec.source_photo_filename, image))
    return layers


async def run(args: argparse.Namespace) -> int:
    if args.timeout_ms <= 0 or args.canvas_aspect_ratio <= 0 or args.preview_width_px <= 0:
        raise SystemExit("timeout / canvas aspect ratio / preview widthは正の値にしてください")
    layers = load_fixed_layers(args.layers_dir)
    settings = Settings()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEYが未設定です")

    output = args.output_dir / f"composition-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    output.mkdir(parents=True)
    started = time.perf_counter()
    try:
        response = await _request_composition(
            genai.Client(api_key=settings.gemini_api_key),
            args.model,
            layers,
            args.canvas_aspect_ratio,
            args.timeout_ms,
        )
        composition_latency_ms = _elapsed_ms(started)
        plan = CompositionResponse.model_validate_json(response.output_text)
        layout = normalize_composition(
            layers,
            plan,
            canvas_aspect_ratio=args.canvas_aspect_ratio,
            min_scale=settings.layout_min_scale,
            max_scale=settings.layout_max_scale,
        )
        artwork = build_artwork(layers, args.photos_dir, layout, args.canvas_aspect_ratio)
        Artwork.model_validate(artwork)
        (output / "artwork.json").write_text(
            json.dumps(artwork, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        render_preview(
            artwork,
            layers,
            output / "composition-preview.png",
            width_px=args.preview_width_px,
        )
        metrics = {
            "model": args.model,
            "success": True,
            "error_type": None,
            "composition_latency_ms": composition_latency_ms,
            "usage": usage_of(response),
            "layer_count": len(layers),
            "canvas": {"aspectRatio": args.canvas_aspect_ratio},
            "layers": [
                {"layerId": layer.layer_id, "label": layer.label, **layout[layer.layer_id]}
                for layer in layers
            ],
            "canvas_outside_ratio": outside_ratio(layers, layout, args.canvas_aspect_ratio),
            "schema_validation": "passed",
            "notes": (
                "既存RGBA Layerを固定入力に使用。"
                "Semantic PlanningとSegmentationは再実行していない。"
            ),
        }
        write_metrics(output, metrics)
        return 0
    except Exception as exc:
        write_metrics(
            output,
            {
                "model": args.model,
                "success": False,
                "error_type": classify_error(exc),
                "composition_latency_ms": _elapsed_ms(started),
                "layer_count": len(layers),
                "schema_validation": "not_run",
                "notes": "Provider raw response・例外本文は保存しない。",
            },
        )
        return 1


async def _request_composition(
    client: genai.Client,
    model: str,
    layers: list[LayerInput],
    canvas_aspect_ratio: float,
    timeout_ms: int,
) -> Any:
    prompt = (
        "You are composing a single layered-memory artwork, not a photo collage. "
        f"The canvas aspect ratio (width/height) is {canvas_aspect_ratio:.6f}. "
        "Return exactly one placement for every supplied layer. x and y are center coordinates "
        "in 0..1. scale is displayed layer width divided by canvas width. "
        "frontToBackOrder is an integer where a smaller value is farther back. "
        "Create visible hierarchy: choose a clear hero, make important elements relatively larger, "
        "and avoid uniform sizes, a horizontal row, or meaningless overlaps. "
        "Keep all layers inside the canvas; do not let a layer obscure a face or another symbolic "
        "subject. Natural overlaps "
        "are allowed. Reconstruct a memory artwork rather than the original photographic scene. "
        "Return only the requested JSON schema."
    )
    content: list[dict[str, str]] = [{"type": "text", "text": prompt}]
    for layer in layers:
        content.append(
            {
                "type": "text",
                "text": (
                    f"layerId={layer.layer_id}; label={layer.label}; "
                    f"widthPx={layer.width_px}; heightPx={layer.height_px}; importance=unavailable"
                ),
            }
        )
        content.append(
            {
                "type": "image",
                "data": base64.b64encode(_thumbnail_png(layer.image)).decode("ascii"),
                "mime_type": "image/png",
            }
        )
    return await asyncio.to_thread(
        client.interactions.create,
        model=model,
        input=content,
        response_format={
            "type": "text",
            "mime_type": "application/json",
            "schema": CompositionResponse.model_json_schema(by_alias=True),
        },
        timeout=timeout_ms / 1000,
    )


def normalize_composition(
    layers: list[LayerInput],
    plan: CompositionResponse,
    *,
    canvas_aspect_ratio: float,
    min_scale: float,
    max_scale: float,
) -> dict[str, dict[str, float | int]]:
    """Gemini配置を検証し、画面内に収まる値と連番layerIndexへ決定論的に正規化する。"""

    layer_by_id = {layer.layer_id: layer for layer in layers}
    placements = {placement.layer_id: placement for placement in plan.layers}
    if len(placements) != len(plan.layers) or set(placements) != set(layer_by_id):
        raise ValueError("CompositionのlayerId集合が固定Layer入力と一致しません")
    if min_scale <= 0 or max_scale < min_scale:
        raise ValueError("scaleの正規化範囲が不正です")

    normalized: dict[str, dict[str, float | int]] = {}
    ordered = sorted(
        plan.layers, key=lambda placement: (placement.front_to_back_order, placement.layer_id)
    )
    for layer_index, placement in enumerate(ordered):
        layer = layer_by_id[placement.layer_id]
        fit_scale = min(1.0, layer.width_px / (canvas_aspect_ratio * layer.height_px))
        upper = max(min_scale, min(max_scale, fit_scale))
        scale = _clamp_finite(placement.scale, min_scale, upper, default=min_scale)
        half_width = scale / 2
        half_height = scale * canvas_aspect_ratio * layer.height_px / layer.width_px / 2
        normalized[placement.layer_id] = {
            "x": _clamp_finite(placement.x, half_width, 1 - half_width, default=0.5),
            "y": _clamp_finite(placement.y, half_height, 1 - half_height, default=0.5),
            "scale": scale,
            "layerIndex": layer_index,
        }
    return normalized


def build_artwork(
    layers: list[LayerInput],
    photos_dir: Path,
    layout: dict[str, dict[str, float | int]],
    canvas_aspect_ratio: float,
) -> dict[str, Any]:
    source_photos: list[dict[str, Any]] = []
    source_ids: dict[str, str] = {}
    for layer in layers:
        if layer.source_photo_filename in source_ids:
            continue
        source_path = photos_dir / layer.source_photo_filename
        if not source_path.is_file():
            raise ValueError(f"Layer由来の写真が見つかりません: {source_path.name}")
        with Image.open(source_path) as source:
            width, height = source.size
            mime_type = Image.MIME.get(source.format, "")
        if mime_type not in {"image/jpeg", "image/png"}:
            raise ValueError(f"P0対象外のsource photo形式です: {source_path.name}")
        source_id = f"source-photo-{Path(layer.source_photo_filename).stem.lower()}"
        source_ids[layer.source_photo_filename] = source_id
        source_photos.append(
            {
                "sourcePhotoId": source_id,
                "asset": {
                    "assetId": f"source-asset-{Path(layer.source_photo_filename).stem.lower()}",
                    "mimeType": mime_type,
                    "widthPx": width,
                    "heightPx": height,
                },
            }
        )
    return {
        "schemaVersion": "1.0",
        "artworkId": "poc-composition-20260824",
        "canvas": {"aspectRatio": canvas_aspect_ratio},
        "sourcePhotos": source_photos,
        # 配列順は固定入力順。前後関係は必ずlayerIndexのみで表す。
        "layers": [
            {
                "layerId": layer.layer_id,
                "sourcePhotoId": source_ids[layer.source_photo_filename],
                "sourceLayerId": f"source-layer-{layer.layer_id}",
                "asset": {
                    "assetId": f"asset-{layer.layer_id}",
                    "mimeType": "image/png",
                    "widthPx": layer.width_px,
                    "heightPx": layer.height_px,
                },
                "label": layer.label,
                **layout[layer.layer_id],
                "replacementCandidates": _replacement_candidates(layer, source_ids),
            }
            for layer in layers
        ],
    }


def _replacement_candidates(layer: LayerInput, source_ids: dict[str, str]) -> list[dict[str, Any]]:
    """既存Validatorが要求する最小の差し替え候補。

    Composition Previewはこの候補を利用しない。PoCの固定Layerから、UI境界を検証できる
    同一意味の代替Asset参照だけを持たせる。
    """

    if layer.layer_id != "layer-03":
        return []
    return [
        {
            "candidateId": "candidate-layer-03-alt",
            "sourcePhotoId": source_ids[layer.source_photo_filename],
            "sourceLayerId": "source-layer-layer-03-alt",
            "asset": {
                "assetId": "asset-layer-03-alt",
                "mimeType": "image/png",
                "widthPx": layer.width_px,
                "heightPx": layer.height_px,
            },
            "label": "牡丹の絵付け（代替）",
        }
    ]


def render_preview(
    artwork: dict[str, Any], layers: list[LayerInput], output_path: Path, *, width_px: int
) -> None:
    """Artwork Dataのx/y/scale/layerIndexのみから正面Previewを描画する。"""

    height_px = round(width_px / artwork["canvas"]["aspectRatio"])
    canvas = Image.new("RGBA", (width_px, height_px), "#F7F3EA")
    image_by_id = {layer.layer_id: layer.image for layer in layers}
    for layer in sorted(artwork["layers"], key=lambda item: item["layerIndex"]):
        image = image_by_id[layer["layerId"]]
        display_width = max(1, round(layer["scale"] * width_px))
        display_height = max(1, round(display_width * image.height / image.width))
        resized = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        left = round(layer["x"] * width_px - display_width / 2)
        top = round(layer["y"] * height_px - display_height / 2)
        canvas.alpha_composite(resized, (left, top))
    canvas.save(output_path, format="PNG")


def outside_ratio(
    layers: list[LayerInput], layout: dict[str, dict[str, float | int]], canvas_aspect_ratio: float
) -> dict[str, float]:
    """正規化後の矩形がCanvas外へ出る面積割合。透明形状ではなく配置安全性の指標。"""

    result: dict[str, float] = {}
    for layer in layers:
        placement = layout[layer.layer_id]
        width = float(placement["scale"])
        height = width * canvas_aspect_ratio * layer.height_px / layer.width_px
        x0, x1 = float(placement["x"]) - width / 2, float(placement["x"]) + width / 2
        y0, y1 = float(placement["y"]) - height / 2, float(placement["y"]) + height / 2
        visible = max(0.0, min(1.0, x1) - max(0.0, x0)) * max(0.0, min(1.0, y1) - max(0.0, y0))
        result[layer.layer_id] = max(0.0, 1 - visible / (width * height))
    return result


def usage_of(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None) or getattr(response, "usage_metadata", None)
    return {
        "input": getattr(usage, "input_tokens", None) or getattr(usage, "prompt_token_count", None),
        "output": getattr(usage, "output_tokens", None)
        or getattr(usage, "candidates_token_count", None),
        "thought": getattr(usage, "thought_tokens", None)
        or getattr(usage, "thoughts_token_count", None),
        "total": getattr(usage, "total_tokens", None) or getattr(usage, "total_token_count", None),
    }


def classify_error(exc: Exception) -> str:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status == 429:
        return "rate_limited"
    if status == 503:
        return "service_unavailable"
    if status == 504:
        return "gateway_timeout"
    if "readtimeout" in type(exc).__name__.lower():
        return "client_timeout"
    if isinstance(exc, ValidationError):
        return "schema_validation_failure"
    if isinstance(exc, ValueError):
        return "input_or_normalization_error"
    return "provider_or_local_error"


def write_metrics(output: Path, metrics: dict[str, Any]) -> None:
    (output / "composition-metrics.json").write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _thumbnail_png(image: Image.Image) -> bytes:
    thumbnail = image.copy()
    thumbnail.thumbnail((768, 768), Image.Resampling.LANCZOS)
    output = BytesIO()
    thumbnail.save(output, format="PNG")
    return output.getvalue()


def _clamp_finite(value: float, lower: float, upper: float, *, default: float) -> float:
    if not math.isfinite(value):
        return default
    return max(lower, min(upper, value))


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
