"""Maskのhard fail判定と、画像固有でない品質診断。

P0の通常経路はempty / full / prompt外だけをhard failにする。連結成分の診断値は
PoCの観測用であり、明示設定したQualityPolicy以外では生成可否を変えない。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ai.image_ops import BoxPx


@dataclass(frozen=True)
class MaskQuality:
    accepted: bool
    reason: str | None
    area_ratio: float
    bbox_coverage: float
    border_touch: bool
    score: float | None
    diagnostics: MaskDiagnostics | None = None


@dataclass(frozen=True)
class MaskDiagnostics:
    """縮小maskから得る形状の観測値。製造可否の閾値はここで決めない。"""

    component_count: int
    largest_component_ratio: float
    top_component_area_ratios: tuple[float, ...]
    tail_component_area_ratio: float
    interior_hole_count: int
    interior_hole_area_ratio: float
    analysis_scale: int


@dataclass(frozen=True)
class MicroIslandCleanup:
    """主成分を残すfull-resolutionの微小孤立成分判定結果。"""

    mask: np.ndarray
    component_count: int
    largest_component_ratio: float
    removed_area_ratio: float
    applied: bool


@dataclass(frozen=True)
class QualityPolicy:
    """校正済み設定を明示した時だけ働く候補置換policy。既定は観測のみ。"""

    mode: str = "observe"
    max_component_count: int | None = None
    min_largest_component_ratio: float | None = None
    min_bbox_coverage: float | None = None
    reject_border_touch: bool = False

    def __post_init__(self) -> None:
        if self.mode not in {"observe", "enforce"}:
            raise ValueError("quality policy mode must be observe or enforce")
        if self.mode == "enforce" and not any(
            (
                self.max_component_count is not None,
                self.min_largest_component_ratio is not None,
                self.min_bbox_coverage is not None,
                self.reject_border_touch,
            )
        ):
            raise ValueError("enforced quality policy requires at least one configured rule")
        if self.max_component_count is not None and self.max_component_count < 1:
            raise ValueError("max_component_count must be positive")
        for value in (self.min_largest_component_ratio, self.min_bbox_coverage):
            if value is not None and not 0 <= value <= 1:
                raise ValueError("quality ratio must be between 0 and 1")

    @property
    def diagnostics_required(self) -> bool:
        return self.mode == "enforce"

    def rejection_reason(
        self,
        diagnostics: MaskDiagnostics | None,
        *,
        bbox_coverage: float,
        border_touch: bool,
        expected_multiple_components: bool = False,
    ) -> str | None:
        if self.mode != "enforce":
            return None
        if diagnostics is None:
            raise ValueError("enforced quality policy requires mask diagnostics")
        if (
            not expected_multiple_components
            and self.max_component_count is not None
            and diagnostics.component_count > self.max_component_count
        ):
            return "quality_fragmented"
        if (
            not expected_multiple_components
            and self.min_largest_component_ratio is not None
            and diagnostics.largest_component_ratio < self.min_largest_component_ratio
        ):
            return "quality_no_dominant_component"
        if self.min_bbox_coverage is not None and bbox_coverage < self.min_bbox_coverage:
            return "quality_low_bbox_coverage"
        if self.reject_border_touch and border_touch:
            return "quality_border_touch"
        return None


def assess_mask(
    mask: np.ndarray,
    prompt_box_px: BoxPx,
    score: float | None,
    *,
    diagnostics_max_side: int | None = None,
) -> MaskQuality:
    if mask.ndim != 2 or not mask.size:
        return MaskQuality(False, "invalid_mask", 0, 0, False, score)
    area_ratio = float(np.mean(mask))
    x0, y0, x1, y1 = prompt_box_px
    prompt_region = mask[y0:y1, x0:x1]
    bbox_coverage = float(np.mean(prompt_region)) if prompt_region.size else 0.0
    border_touch = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())

    diagnostics = (
        diagnose_mask(mask, max_side=diagnostics_max_side)
        if diagnostics_max_side is not None and mask.any()
        else None
    )

    if not mask.any():
        return MaskQuality(
            False, "empty_mask", area_ratio, bbox_coverage, border_touch, score, diagnostics
        )
    if area_ratio >= 0.98:
        return MaskQuality(
            False,
            "foreground_covers_image",
            area_ratio,
            bbox_coverage,
            border_touch,
            score,
            diagnostics,
        )
    if not prompt_region.any():
        return MaskQuality(
            False,
            "mask_outside_prompt",
            area_ratio,
            bbox_coverage,
            border_touch,
            score,
            diagnostics,
        )
    return MaskQuality(True, None, area_ratio, bbox_coverage, border_touch, score, diagnostics)


def diagnose_mask(mask: np.ndarray, *, max_side: int) -> MaskDiagnostics:
    """8近傍componentを最大 ``max_side`` へ標本化して集計する。

    外部依存を増やさず、画像固有の閾値判定ではなく面積分布だけを返す。
    """

    if mask.ndim != 2 or not mask.size or not mask.any():
        return MaskDiagnostics(0, 0, (), 0, 0, 0, 1)
    if max_side < 1:
        raise ValueError("max_side must be positive")
    scale = max(1, (max(mask.shape) + max_side - 1) // max_side)
    sampled = np.asarray(mask[::scale, ::scale], dtype=bool)
    areas = _component_areas(sampled)
    foreground = sum(areas)
    ratios = tuple(sorted((area / foreground for area in areas), reverse=True))
    top = ratios[:5]
    holes = _interior_holes(sampled)
    hole_pixels = sum(hole.shape[0] for hole in holes)
    return MaskDiagnostics(
        component_count=len(ratios),
        largest_component_ratio=top[0] if top else 0,
        top_component_area_ratios=top,
        tail_component_area_ratio=float(sum(ratios[5:])),
        interior_hole_count=len(holes),
        interior_hole_area_ratio=hole_pixels / foreground,
        analysis_scale=scale,
    )


def clean_micro_islands(mask: np.ndarray, *, max_removed_area_ratio: float) -> MicroIslandCleanup:
    """微小な孤立成分だけを最大成分から除去する。

    8近傍でfull-resolutionの連結成分を調べる。閾値超過の分離領域は残して
    ``applied=False`` を返すため、呼び出し元は物理Layerとして拒否できる。
    形状の橋渡しや成分間の結合は一切行わない。
    """

    if not 0 <= max_removed_area_ratio <= 1:
        raise ValueError("max_removed_area_ratio must be between 0 and 1")
    if mask.ndim != 2 or not mask.size or not mask.any():
        return MicroIslandCleanup(mask, 0, 0, 0, False)

    components = _connected_components(mask)
    foreground = sum(component.shape[0] for component in components)
    largest = max(components, key=lambda component: component.shape[0])
    largest_area = largest.shape[0]
    removed_area_ratio = (foreground - largest_area) / foreground
    if len(components) == 1:
        return MicroIslandCleanup(mask, 1, 1, 0, False)
    if removed_area_ratio > max_removed_area_ratio:
        return MicroIslandCleanup(
            mask,
            len(components),
            largest_area / foreground,
            removed_area_ratio,
            False,
        )
    cleaned = np.zeros_like(mask, dtype=bool)
    cleaned[largest[:, 0], largest[:, 1]] = True
    return MicroIslandCleanup(
        cleaned,
        len(components),
        largest_area / foreground,
        removed_area_ratio,
        True,
    )


def _component_areas(mask: np.ndarray) -> list[int]:
    """PoC診断だけで使うdependency-freeな8近傍連結成分の面積集計。"""

    return [component.shape[0] for component in _connected_components(mask)]


def _interior_holes(mask: np.ndarray) -> list[np.ndarray]:
    """外周と接続していない透明領域を返す。

    これは縮小Maskの観測である。窓・アーチ等の意図的な開口部との区別はしないため、
    この値だけでMaskを埋めたり候補を不合格にしたりしない。
    """

    background = _connected_components(np.logical_not(mask))
    height, width = mask.shape
    return [
        component
        for component in background
        if not (
            (component[:, 0] == 0).any()
            or (component[:, 0] == height - 1).any()
            or (component[:, 1] == 0).any()
            or (component[:, 1] == width - 1).any()
        )
    ]


def _connected_components(mask: np.ndarray) -> list[np.ndarray]:
    """dependency-freeな8近傍連結成分。full-resolution cleanupにも利用する。"""

    height, width = mask.shape
    visited = np.zeros_like(mask, dtype=bool)
    components: list[np.ndarray] = []
    for start_y, start_x in np.argwhere(mask):
        y = int(start_y)
        x = int(start_x)
        if visited[y, x]:
            continue
        visited[y, x] = True
        stack = [(y, x)]
        points: list[tuple[int, int]] = []
        while stack:
            current_y, current_x = stack.pop()
            points.append((current_y, current_x))
            for neighbor_y in range(max(0, current_y - 1), min(height, current_y + 2)):
                for neighbor_x in range(max(0, current_x - 1), min(width, current_x + 2)):
                    if mask[neighbor_y, neighbor_x] and not visited[neighbor_y, neighbor_x]:
                        visited[neighbor_y, neighbor_x] = True
                        stack.append((neighbor_y, neighbor_x))
        components.append(np.asarray(points, dtype=np.intp))
    return components
