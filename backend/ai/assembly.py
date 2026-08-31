"""Accepted LayerとCompositionをArtwork Dataへ安全に組み立てる。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from uuid import uuid4

from ai.errors import AiError
from ai.internal_models import CompositionPlan
from ai.types import AssetBlob


@dataclass(frozen=True)
class AcceptedLayer:
    candidate_id: str
    label: str
    source_photo_index: int
    source_layer_id: str
    asset: AssetBlob
    importance: float
    kind: str = "subject"
    # Semantic planner内部の選定情報。Artwork Dataへはserializeしない。
    semantic_role: str = "general"


@dataclass(frozen=True)
class SourcePhotoAsset:
    source_photo_id: str
    asset: AssetBlob


def normalize_composition(
    accepted_layers: list[AcceptedLayer],
    plan: CompositionPlan,
    *,
    canvas_aspect_ratio: float,
    min_scale: float,
    max_scale: float,
    minimum_scales: dict[str, float] | None = None,
) -> dict[str, dict[str, float | int]]:
    """Geminiの構図を検証し、全LayerをCanvas内へ収めて正規化する。"""

    accepted_by_id = {layer.candidate_id: layer for layer in accepted_layers}
    if len(accepted_by_id) != len(accepted_layers):
        raise AiError("採用Layerのcandidate_idが重複しています")
    placements = {placement.candidate_id: placement for placement in plan.layers}
    if len(placements) != len(plan.layers) or set(placements) != set(accepted_by_id):
        raise AiError("Compositionが採用Layerと一致しません")
    if not math.isfinite(canvas_aspect_ratio) or canvas_aspect_ratio <= 0:
        raise AiError("Canvas aspect ratioが不正です")
    if min_scale <= 0 or max_scale < min_scale:
        raise AiError("Layout scale設定が不正です")

    ordered = sorted(plan.layers, key=lambda placement: (placement.order, placement.candidate_id))
    result: dict[str, dict[str, float | int]] = {}
    for layer_index, placement in enumerate(ordered):
        layer = accepted_by_id[placement.candidate_id]
        asset = layer.asset
        # scaleはCanvas幅基準。表示高さのCanvas比は
        # scale * canvasAspectRatio * assetHeight / assetWidth になる。
        fit_scale = min(
            1.0,
            asset.width_px / (canvas_aspect_ratio * asset.height_px),
        )
        upper_scale = min(max_scale, fit_scale)
        explicit_minimum = (minimum_scales or {}).get(placement.candidate_id)
        requested_minimum = explicit_minimum if explicit_minimum is not None else min_scale
        if requested_minimum <= 0:
            raise AiError("Layerごとの最小scale設定が不正です")
        # 極端な縦長AssetではCanvas内収容をminScaleより優先する。ただし、
        # scene anchor等の明示的な最小表示幅を満たせない候補は採用しない。
        if explicit_minimum is not None and requested_minimum > upper_scale:
            raise AiError("Layerが必要な表示幅でCanvas内に収まりません")
        lower_scale = (
            max(min_scale, requested_minimum)
            if explicit_minimum is not None
            else min(min_scale, upper_scale)
        )
        scale = _clamp_finite(
            placement.scale,
            lower_scale,
            upper_scale,
            default=lower_scale,
        )
        half_width = scale / 2
        half_height = (
            scale * canvas_aspect_ratio * asset.height_px / asset.width_px / 2
        )
        result[placement.candidate_id] = {
            "x": _clamp_finite(
                placement.x,
                half_width,
                1 - half_width,
                default=0.5,
            ),
            "y": _clamp_finite(
                placement.y,
                half_height,
                1 - half_height,
                default=0.5,
            ),
            "scale": scale,
            "layerIndex": layer_index,
        }
    return result


def bottom_gaps(
    accepted_layers: list[AcceptedLayer],
    composition: dict[str, dict[str, float | int]],
    *,
    canvas_aspect_ratio: float,
) -> dict[str, float]:
    """各Layerの下端からCanvas下端までの正規化距離を返す。"""

    accepted_by_id = {layer.candidate_id: layer for layer in accepted_layers}
    if set(composition) != set(accepted_by_id):
        raise AiError("Artwork構図とLayerが一致しません")
    gaps: dict[str, float] = {}
    for candidate_id, layout in composition.items():
        layer = accepted_by_id[candidate_id]
        scale = float(layout["scale"])
        display_height = scale * canvas_aspect_ratio * layer.asset.height_px / layer.asset.width_px
        gaps[candidate_id] = 1 - (float(layout["y"]) + display_height / 2)
    return gaps


def clamp_bottom_gaps(
    accepted_layers: list[AcceptedLayer],
    composition: dict[str, dict[str, float | int]],
    *,
    canvas_aspect_ratio: float,
    max_bottom_gap: float,
) -> tuple[dict[str, dict[str, float | int]], dict[str, float]]:
    """上限を超えたLayerだけを下げ、補正量を内部PoC診断用に返す。"""

    if not 0 <= max_bottom_gap <= 1:
        raise AiError("Canvas下端からの最大距離設定が不正です")
    result = {candidate_id: dict(layout) for candidate_id, layout in composition.items()}
    corrections: dict[str, float] = {}
    accepted_by_id = {layer.candidate_id: layer for layer in accepted_layers}
    for candidate_id, gap in bottom_gaps(
        accepted_layers, result, canvas_aspect_ratio=canvas_aspect_ratio
    ).items():
        if gap <= max_bottom_gap:
            continue
        layer = accepted_by_id[candidate_id]
        scale = float(result[candidate_id]["scale"])
        half_height = scale * canvas_aspect_ratio * layer.asset.height_px / layer.asset.width_px / 2
        previous_y = float(result[candidate_id]["y"])
        corrected_y = max(half_height, min(1 - half_height, 1 - max_bottom_gap - half_height))
        result[candidate_id]["y"] = corrected_y
        corrections[candidate_id] = corrected_y - previous_y
    return result, corrections


def assemble_artwork(
    source_photos: list[SourcePhotoAsset],
    accepted_layers: list[AcceptedLayer],
    composition: dict[str, dict[str, float | int]],
    *,
    canvas_aspect_ratio: float,
) -> dict:
    if not source_photos or not accepted_layers:
        raise AiError("Artworkに必要なAssetが不足しています")
    if set(composition) != {layer.candidate_id for layer in accepted_layers}:
        raise AiError("Artwork構図とLayerが一致しません")

    artwork_id = _id("artwork")
    return {
        "schemaVersion": "1.0",
        "artworkId": artwork_id,
        "canvas": {"aspectRatio": canvas_aspect_ratio},
        "sourcePhotos": [
            {
                "sourcePhotoId": source.source_photo_id,
                "asset": _asset_ref(source.asset),
            }
            for source in source_photos
        ],
        "layers": [
            {
                "layerId": _id("layer"),
                "sourcePhotoId": source_photos[layer.source_photo_index].source_photo_id,
                "sourceLayerId": layer.source_layer_id,
                "asset": _asset_ref(layer.asset),
                "label": layer.label,
                **composition[layer.candidate_id],
                "replacementCandidates": [],
            }
            for layer in accepted_layers
        ],
    }


def _asset_ref(asset: AssetBlob) -> dict:
    return {
        "assetId": asset.asset_id,
        "mimeType": asset.mime_type,
        "widthPx": asset.width_px,
        "heightPx": asset.height_px,
    }


def _id(prefix: str) -> str:
    return f"{prefix}-{uuid4().hex}"


def _clamp_finite(value: float, lower: float, upper: float, *, default: float) -> float:
    if not math.isfinite(value):
        return default
    return max(lower, min(upper, value))
