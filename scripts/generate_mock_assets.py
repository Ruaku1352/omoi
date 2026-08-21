#!/usr/bin/env python3
"""contracts/mock/artwork.json を読み、参照されている Asset のダミー画像を生成する。

- Layer / Candidate Asset は透過 RGBA PNG（実際に alpha=0 の領域を持つ）
- Source Photo は JPEG
- ファイル名は  <assetId>.<ext>  の規約に従い contracts/assets/ 配下へ出力する

実写真が用意できるまでの繋ぎ。実Assetへ差し替える場合も assetId とファイル名の
対応、および widthPx / heightPx の一致は維持すること。

usage: python scripts/generate_mock_assets.py
"""

from __future__ import annotations

import json
import pathlib

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
MOCK = ROOT / "contracts" / "mock" / "artwork.json"
OUT = ROOT / "contracts" / "assets"

EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

# assetId -> (塗り色, 形状)。未定義は既定値にフォールバックする。
STYLE = {
    "layer-1": ((120, 170, 220), "rect"),
    "layer-2": ((225, 130, 160), "ellipse"),
    "layer-3": ((205, 155, 95), "ellipse"),
    "layer-4": ((90, 110, 150), "person"),
    "cand-2a": ((235, 165, 110), "ellipse"),
    "cand-4a": ((110, 140, 180), "person"),
    "cand-4b": ((70, 90, 130), "person"),
}
DEFAULT_STYLE = ((150, 150, 150), "ellipse")


def _font(size: int):
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        if pathlib.Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _caption(draw: ImageDraw.ImageDraw, w: int, h: int, text: str, fill):
    font = _font(max(16, min(w, h) // 14))
    box = draw.textbbox((0, 0), text, font=font)
    draw.text(
        ((w - (box[2] - box[0])) / 2, h * 0.86 - (box[3] - box[1]) / 2),
        text,
        font=font,
        fill=fill,
    )


def make_layer_png(asset_id: str, w: int, h: int, label: str) -> Image.Image:
    """alpha=0 の余白を必ず持つ透過 PNG を作る。"""
    color, shape = STYLE.get(asset_id, DEFAULT_STYLE)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad_x, pad_y = w * 0.08, h * 0.08

    if shape == "rect":
        d.rounded_rectangle(
            [pad_x, pad_y, w - pad_x, h - pad_y],
            radius=min(w, h) * 0.04,
            fill=(*color, 255),
        )
    elif shape == "person":
        head_r = min(w, h) * 0.16
        cx = w / 2
        d.ellipse(
            [cx - head_r, pad_y, cx + head_r, pad_y + head_r * 2],
            fill=(*color, 255),
        )
        d.rounded_rectangle(
            [cx - w * 0.28, pad_y + head_r * 2.2, cx + w * 0.28, h - pad_y],
            radius=min(w, h) * 0.08,
            fill=(*color, 255),
        )
    else:
        d.ellipse([pad_x, pad_y, w - pad_x, h - pad_y], fill=(*color, 255))

    _caption(d, w, h, f"{asset_id} / {label}", (255, 255, 255, 235))
    return img


def make_photo_jpg(asset_id: str, w: int, h: int) -> Image.Image:
    img = Image.new("RGB", (w, h), (238, 236, 231))
    d = ImageDraw.Draw(img)
    step = max(1, h // 3)
    for i, band in enumerate([(206, 224, 240), (232, 226, 210), (216, 226, 208)]):
        d.rectangle([0, i * step, w, (i + 1) * step], fill=band)
    d.rectangle([2, 2, w - 3, h - 3], outline=(170, 170, 170), width=4)
    _caption(d, w, h, f"{asset_id} (dummy source photo)", (90, 90, 90))
    return img


def main() -> None:
    artwork = json.loads(MOCK.read_text(encoding="utf-8"))
    OUT.mkdir(parents=True, exist_ok=True)

    jobs: list[tuple[dict, str]] = []
    for photo in artwork["sourcePhotos"]:
        jobs.append((photo["asset"], photo["sourcePhotoId"]))
    for layer in artwork["layers"]:
        jobs.append((layer["asset"], layer["label"]))
        for cand in layer.get("replacementCandidates", []):
            jobs.append((cand["asset"], cand["label"]))

    written = 0
    for asset, label in jobs:
        asset_id = asset["assetId"]
        w, h = asset["widthPx"], asset["heightPx"]
        ext = EXT[asset["mimeType"]]
        path = OUT / f"{asset_id}.{ext}"

        if asset["mimeType"] == "image/png":
            make_layer_png(asset_id, w, h, label).save(path)
        else:
            make_photo_jpg(asset_id, w, h).save(path, quality=88)
        written += 1
        print(f"  wrote {path.relative_to(ROOT)}  ({w}x{h})")

    print(f"\n{written} assets -> {OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
