"""Accepted LayerとCompositionをArtwork Dataへ安全に組み立てる。"""

from __future__ import annotations

import math
from dataclasses import dataclass
from io import BytesIO
from uuid import uuid4

import numpy as np
from PIL import Image

from ai.errors import AiError
from ai.internal_models import CompositionPlan
from ai.types import AssetBlob

COMPOSITION_BOUND_EPSILON = 1e-9


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
    semantic_role: str | None = None


@dataclass(frozen=True)
class SourcePhotoAsset:
    source_photo_id: str
    asset: AssetBlob


@dataclass(frozen=True)
class SubjectOverlapDiagnostic:
    """Canvas上で後方subjectが前方subjectに隠れる量のprivate診断。"""

    back_candidate_id: str
    front_candidate_id: str
    overlap_pixels: int
    back_foreground_pixels: int
    front_foreground_pixels: int
    back_obscured_ratio: float
    front_overlap_ratio: float
    canvas_width_px: int
    canvas_height_px: int


@dataclass(frozen=True)
class CompositionLayerDiagnostic:
    """正規化済みLayoutのprivate観測値。採否や補正は決めない。"""

    candidate_id: str
    kind: str
    layer_index: int
    x: float
    y: float
    scale: float
    display_width: float
    display_height: float
    left: float
    top: float
    right: float
    bottom: float
    within_canvas: bool


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
        half_height = scale * canvas_aspect_ratio * asset.height_px / asset.width_px / 2
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


def diagnose_composition_layers(
    accepted_layers: list[AcceptedLayer],
    composition: dict[str, dict[str, float | int]],
    *,
    canvas_aspect_ratio: float,
) -> tuple[CompositionLayerDiagnostic, ...]:
    """構図の座標・scale・Canvas境界をprivate診断用に集約する。

    ``normalize_composition``後のLayoutを観測するだけであり、overlapの閾値や
    自動reject・自動補正はここへ持ち込まない。
    """

    if not math.isfinite(canvas_aspect_ratio) or canvas_aspect_ratio <= 0:
        raise AiError("Canvas aspect ratioが不正です")
    accepted_by_id = {layer.candidate_id: layer for layer in accepted_layers}
    if set(composition) != set(accepted_by_id):
        raise AiError("Artwork構図とLayerが一致しません")
    diagnostics: list[CompositionLayerDiagnostic] = []
    for candidate_id, layout in sorted(
        composition.items(), key=lambda item: (int(item[1]["layerIndex"]), item[0])
    ):
        layer = accepted_by_id[candidate_id]
        x, y, scale = (float(layout[key]) for key in ("x", "y", "scale"))
        display_height = scale * canvas_aspect_ratio * layer.asset.height_px / layer.asset.width_px
        left, top = x - scale / 2, y - display_height / 2
        right, bottom = x + scale / 2, y + display_height / 2
        diagnostics.append(
            CompositionLayerDiagnostic(
                candidate_id=candidate_id,
                kind=layer.kind,
                layer_index=int(layout["layerIndex"]),
                x=x,
                y=y,
                scale=scale,
                display_width=scale,
                display_height=display_height,
                left=left,
                top=top,
                right=right,
                bottom=bottom,
                within_canvas=(
                    left >= -COMPOSITION_BOUND_EPSILON
                    and top >= -COMPOSITION_BOUND_EPSILON
                    and right <= 1 + COMPOSITION_BOUND_EPSILON
                    and bottom <= 1 + COMPOSITION_BOUND_EPSILON
                ),
            )
        )
    return tuple(diagnostics)


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


def diagnose_subject_overlaps(
    accepted_layers: list[AcceptedLayer],
    composition: dict[str, dict[str, float | int]],
    *,
    canvas_aspect_ratio: float,
    max_canvas_width_px: int = 512,
) -> tuple[SubjectOverlapDiagnostic, ...]:
    """前景subject同士のAlpha重なりを縮小Canvas上で計測する。

    これは観測値だけを返す。scene anchorとの重なりや、意図的な親子・成長表現を
    自動で不合格にしない。最終採否はpreviewの目視と品質評価で決める。
    """

    if not math.isfinite(canvas_aspect_ratio) or canvas_aspect_ratio <= 0:
        raise AiError("Canvas aspect ratioが不正です")
    if max_canvas_width_px < 1:
        raise AiError("重なり診断のCanvas幅が不正です")
    accepted_by_id = {layer.candidate_id: layer for layer in accepted_layers}
    if set(composition) != set(accepted_by_id):
        raise AiError("Artwork構図とLayerが一致しません")
    subjects = sorted(
        (layer for layer in accepted_layers if layer.kind == "subject"),
        key=lambda layer: (int(composition[layer.candidate_id]["layerIndex"]), layer.candidate_id),
    )
    if len(subjects) < 2:
        return ()
    canvas_height_px = max(1, round(max_canvas_width_px / canvas_aspect_ratio))
    masks = {
        layer.candidate_id: _render_alpha_mask(
            layer,
            composition[layer.candidate_id],
            canvas_width_px=max_canvas_width_px,
            canvas_height_px=canvas_height_px,
        )
        for layer in subjects
    }
    diagnostics: list[SubjectOverlapDiagnostic] = []
    for back_index, back_layer in enumerate(subjects[:-1]):
        back_mask = masks[back_layer.candidate_id]
        back_pixels = int(back_mask.sum())
        for front_layer in subjects[back_index + 1 :]:
            front_mask = masks[front_layer.candidate_id]
            front_pixels = int(front_mask.sum())
            overlap_pixels = int(np.logical_and(back_mask, front_mask).sum())
            diagnostics.append(
                SubjectOverlapDiagnostic(
                    back_candidate_id=back_layer.candidate_id,
                    front_candidate_id=front_layer.candidate_id,
                    overlap_pixels=overlap_pixels,
                    back_foreground_pixels=back_pixels,
                    front_foreground_pixels=front_pixels,
                    back_obscured_ratio=overlap_pixels / back_pixels if back_pixels else 0,
                    front_overlap_ratio=overlap_pixels / front_pixels if front_pixels else 0,
                    canvas_width_px=max_canvas_width_px,
                    canvas_height_px=canvas_height_px,
                )
            )
    return tuple(diagnostics)


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


def _render_alpha_mask(
    layer: AcceptedLayer,
    layout: dict[str, float | int],
    *,
    canvas_width_px: int,
    canvas_height_px: int,
) -> np.ndarray:
    """RGBA Layerを縮小Canvasへ置き、Alphaだけを二値Maskで返す。"""

    with Image.open(BytesIO(layer.asset.data)) as source:
        alpha = source.convert("RGBA").getchannel("A")
    scale = float(layout["scale"])
    display_width = max(1, round(scale * canvas_width_px))
    display_height = max(
        1,
        round(display_width * layer.asset.height_px / layer.asset.width_px),
    )
    alpha = alpha.resize((display_width, display_height), Image.Resampling.NEAREST)
    rendered = np.zeros((canvas_height_px, canvas_width_px), dtype=bool)
    left = round(float(layout["x"]) * canvas_width_px - display_width / 2)
    top = round(float(layout["y"]) * canvas_height_px - display_height / 2)
    source_x0, source_y0 = max(0, -left), max(0, -top)
    target_x0, target_y0 = max(0, left), max(0, top)
    target_x1 = min(canvas_width_px, left + display_width)
    target_y1 = min(canvas_height_px, top + display_height)
    if target_x0 >= target_x1 or target_y0 >= target_y1:
        return rendered
    alpha_array = np.asarray(alpha, dtype=np.uint8) > 0
    source_x1 = source_x0 + target_x1 - target_x0
    source_y1 = source_y0 + target_y1 - target_y0
    rendered[target_y0:target_y1, target_x0:target_x1] = alpha_array[
        source_y0:source_y1, source_x0:source_x1
    ]
    return rendered
