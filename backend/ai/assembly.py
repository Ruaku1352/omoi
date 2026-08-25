"""Accepted LayerとCompositionをArtwork Dataへ安全に組み立てる。"""

from __future__ import annotations

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


@dataclass(frozen=True)
class SourcePhotoAsset:
    source_photo_id: str
    asset: AssetBlob


def normalize_composition(
    accepted_layers: list[AcceptedLayer],
    plan: CompositionPlan,
    *,
    min_scale: float,
    max_scale: float,
) -> dict[str, dict[str, float | int]]:
    """Geminiの構図を検証し、Contractの座標と連番layerIndexへ正規化する。"""

    accepted_by_id = {layer.candidate_id: layer for layer in accepted_layers}
    if len(accepted_by_id) != len(accepted_layers):
        raise AiError("採用Layerのcandidate_idが重複しています")
    placements = {placement.candidate_id: placement for placement in plan.layers}
    if len(placements) != len(plan.layers) or set(placements) != set(accepted_by_id):
        raise AiError("Compositionが採用Layerと一致しません")
    if min_scale <= 0 or max_scale < min_scale:
        raise AiError("Layout scale設定が不正です")

    ordered = sorted(plan.layers, key=lambda placement: (placement.order, placement.candidate_id))
    result: dict[str, dict[str, float | int]] = {}
    for layer_index, placement in enumerate(ordered):
        result[placement.candidate_id] = {
            "x": _clamp(placement.x, 0.0, 1.0),
            "y": _clamp(placement.y, 0.0, 1.0),
            "scale": _clamp(placement.scale, min_scale, max_scale),
            "layerIndex": layer_index,
        }
    return result


def assemble_artwork(
    source_photos: list[SourcePhotoAsset],
    accepted_layers: list[AcceptedLayer],
    composition: dict[str, dict[str, float | int]],
) -> dict:
    if not source_photos or not accepted_layers:
        raise AiError("Artworkに必要なAssetが不足しています")
    if set(composition) != {layer.candidate_id for layer in accepted_layers}:
        raise AiError("Artwork構図とLayerが一致しません")

    primary = source_photos[0].asset
    artwork_id = _id("artwork")
    return {
        "schemaVersion": "1.0",
        "artworkId": artwork_id,
        "canvas": {"aspectRatio": primary.width_px / primary.height_px},
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


def _clamp(value: float, lower: float, upper: float) -> float:
    if value != value:  # NaN
        return (lower + upper) / 2
    return max(lower, min(upper, value))
