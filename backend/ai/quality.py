"""Mask Quality Gate。PoC前の強すぎる閾値固定を避け、hard failだけを判定する。"""

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


def assess_mask(mask: np.ndarray, prompt_box_px: BoxPx, score: float | None) -> MaskQuality:
    if mask.ndim != 2 or not mask.size:
        return MaskQuality(False, "invalid_mask", 0, 0, False, score)
    area_ratio = float(np.mean(mask))
    x0, y0, x1, y1 = prompt_box_px
    prompt_region = mask[y0:y1, x0:x1]
    bbox_coverage = float(np.mean(prompt_region)) if prompt_region.size else 0.0
    border_touch = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any() or mask[:, -1].any())

    if not mask.any():
        return MaskQuality(False, "empty_mask", area_ratio, bbox_coverage, border_touch, score)
    if area_ratio >= 0.98:
        return MaskQuality(
            False, "foreground_covers_image", area_ratio, bbox_coverage, border_touch, score
        )
    if not prompt_region.any():
        return MaskQuality(
            False, "mask_outside_prompt", area_ratio, bbox_coverage, border_touch, score
        )
    return MaskQuality(True, None, area_ratio, bbox_coverage, border_touch, score)
