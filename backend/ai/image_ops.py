"""Decode、座標変換、MaskからRGBA Layerを作る純粋な画像処理。"""

from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO

import numpy as np
from PIL import Image, ImageOps

from ai.errors import AiError
from ai.internal_models import Box2D
from ai.types import InputPhoto

BoxPx = tuple[int, int, int, int]


@dataclass(frozen=True)
class DecodedPhoto:
    input_photo: InputPhoto
    image: Image.Image


def decode_photo(photo: InputPhoto) -> DecodedPhoto:
    """EXIF Orientationを反映し、常にRGB Imageとして保持する。"""

    try:
        with Image.open(BytesIO(photo.data)) as source:
            image = ImageOps.exif_transpose(source).convert("RGB")
    except Exception as exc:
        raise AiError("入力画像をdecodeできません") from exc
    return DecodedPhoto(input_photo=photo, image=image)


def thumbnail(image: Image.Image, max_side: int) -> Image.Image:
    result = image.copy()
    result.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return result


def gemini_box_to_px(box: Box2D, image_size: tuple[int, int]) -> BoxPx:
    """0..1000の ``ymin,xmin,ymax,xmax`` を ``x0,y0,x1,y1`` pixelへ変換する。"""

    width, height = image_size
    x0 = max(0, min(width - 1, round(box.x_min / 1000 * width)))
    y0 = max(0, min(height - 1, round(box.y_min / 1000 * height)))
    x1 = max(x0 + 1, min(width, round(box.x_max / 1000 * width)))
    y1 = max(y0 + 1, min(height, round(box.y_max / 1000 * height)))
    return x0, y0, x1, y1


def expand_box(box: BoxPx, image_size: tuple[int, int], fraction: float = 0.05) -> BoxPx:
    """bounded retry用にbboxを少しだけ広げる。"""

    x0, y0, x1, y1 = box
    width, height = image_size
    margin_x = max(1, round((x1 - x0) * fraction))
    margin_y = max(1, round((y1 - y0) * fraction))
    return (
        max(0, x0 - margin_x),
        max(0, y0 - margin_y),
        min(width, x1 + margin_x),
        min(height, y1 + margin_y),
    )


def union_masks(masks: list[np.ndarray]) -> np.ndarray:
    if not masks:
        raise AiError("統合するMaskがありません")
    shape = masks[0].shape
    if len(shape) != 2 or any(mask.shape != shape for mask in masks):
        raise AiError("Maskのshapeが一致しません")
    return np.logical_or.reduce(masks).astype(bool, copy=False)


def mask_to_rgba_png(
    image: Image.Image,
    mask: np.ndarray,
    *,
    padding_px: int,
) -> tuple[bytes, int, int]:
    """Maskをalphaとして適用し、余白つきtight cropのRGBA PNGを返す。"""

    if mask.shape != (image.height, image.width):
        raise AiError("Maskと画像のサイズが一致しません")
    ys, xs = np.nonzero(mask)
    if not len(xs):
        raise AiError("空のMaskからLayerは作れません")

    x0 = max(0, int(xs.min()) - padding_px)
    y0 = max(0, int(ys.min()) - padding_px)
    x1 = min(image.width, int(xs.max()) + 1 + padding_px)
    y1 = min(image.height, int(ys.max()) + 1 + padding_px)

    rgba = image.convert("RGBA")
    alpha = Image.fromarray(np.where(mask, 255, 0).astype(np.uint8), mode="L")
    rgba.putalpha(alpha)
    cropped = rgba.crop((x0, y0, x1, y1))
    output = BytesIO()
    cropped.save(output, format="PNG", optimize=True)
    return output.getvalue(), cropped.width, cropped.height


def crop_to_rgba_png(image: Image.Image, box: BoxPx) -> tuple[bytes, int, int]:
    """範囲Layer用に、指定範囲を不透明RGBA PNGとして切り出す。"""

    x0, y0, x1, y1 = box
    if not (0 <= x0 < x1 <= image.width and 0 <= y0 < y1 <= image.height):
        raise AiError("Crop範囲が画像内に収まりません")
    cropped = image.crop(box).convert("RGBA")
    output = BytesIO()
    cropped.save(output, format="PNG", optimize=True)
    return output.getvalue(), cropped.width, cropped.height


def image_to_png(image: Image.Image) -> bytes:
    output = BytesIO()
    image.save(output, format="PNG", optimize=True)
    return output.getvalue()
