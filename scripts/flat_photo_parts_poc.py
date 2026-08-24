#!/usr/bin/env python3
"""Generate flat print parts from mock Artwork layer assets.

This PoC keeps each part as a constant-thickness flat plate. It uses RGBA
layer alpha only for the outside shape; it does not generate relief or
heightmap geometry from photo brightness.
"""

from __future__ import annotations

import argparse
import base64
import html
import io
import json
import math
import pathlib
import re
from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageFilter


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARTWORK = ROOT / "contracts" / "mock" / "artwork.json"
DEFAULT_ASSETS = ROOT / "contracts" / "assets"
DEFAULT_OUT = ROOT / "tmp" / "flat-photo-parts-poc"
EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


@dataclass(frozen=True)
class FlatPhotoPartConfig:
    target_width_mm: float = 160.0
    part_thickness_mm: float = 1.6
    outline_margin_mm: float = 2.0
    grid_cell_mm: float = 2.0
    alpha_threshold: int = 16
    min_cell_coverage: float = 0.10
    print_layout_margin_mm: float = 10.0
    print_layout_gutter_mm: float = 6.0
    material: str = "PLA"


def _config_to_json(config: FlatPhotoPartConfig) -> dict:
    return {
        "targetWidthMm": config.target_width_mm,
        "partThicknessMm": config.part_thickness_mm,
        "outlineMarginMm": config.outline_margin_mm,
        "gridCellMm": config.grid_cell_mm,
        "alphaThreshold": config.alpha_threshold,
        "minCellCoverage": config.min_cell_coverage,
        "printLayoutMarginMm": config.print_layout_margin_mm,
        "printLayoutGutterMm": config.print_layout_gutter_mm,
        "material": config.material,
    }


def _load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return safe or "part"


def _asset_path(asset: dict, assets_dir: pathlib.Path) -> pathlib.Path:
    ext = EXT_BY_MIME.get(asset["mimeType"])
    if not ext:
        raise ValueError(f"Unsupported asset mimeType: {asset['mimeType']}")
    return assets_dir / f"{asset['assetId']}.{ext}"


def _normal(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def _write_stl(
    path: pathlib.Path,
    name: str,
    triangles: Iterable[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
) -> int:
    tris = list(triangles)
    with path.open("w", encoding="utf-8", newline="\n") as f:
        f.write(f"solid {name}\n")
        for a, b, c in tris:
            nx, ny, nz = _normal(a, b, c)
            f.write(f"  facet normal {nx:.6f} {ny:.6f} {nz:.6f}\n")
            f.write("    outer loop\n")
            for x, y, z in (a, b, c):
                f.write(f"      vertex {x:.6f} {y:.6f} {z:.6f}\n")
            f.write("    endloop\n")
            f.write("  endfacet\n")
        f.write(f"endsolid {name}\n")
    return len(tris)


def _quad(
    a: tuple[float, float, float],
    b: tuple[float, float, float],
    c: tuple[float, float, float],
    d: tuple[float, float, float],
) -> list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]:
    return [(a, b, c), (a, c, d)]


def _grid_triangles(
    occupied: set[tuple[int, int]],
    columns: int,
    rows: int,
    width_mm: float,
    height_mm: float,
    thickness_mm: float,
) -> list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]:
    cell_w = width_mm / columns
    cell_h = height_mm / rows
    tris = []

    for row, col in sorted(occupied):
        x0 = col * cell_w
        x1 = (col + 1) * cell_w
        y0 = row * cell_h
        y1 = (row + 1) * cell_h
        z0 = 0.0
        z1 = thickness_mm

        # Top and bottom faces.
        tris += _quad((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1))
        tris += _quad((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0))

        if (row - 1, col) not in occupied:
            tris += _quad((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1))
        if (row + 1, col) not in occupied:
            tris += _quad((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1))
        if (row, col - 1) not in occupied:
            tris += _quad((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1))
        if (row, col + 1) not in occupied:
            tris += _quad((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1))

    return tris


def _threshold_alpha(image: Image.Image, threshold: int) -> Image.Image:
    return image.getchannel("A").point(lambda value: 255 if value >= threshold else 0)


def _dilate(mask: Image.Image, radius_px: int) -> Image.Image:
    if radius_px <= 0:
        return mask
    size = radius_px * 2 + 1
    return mask.filter(ImageFilter.MaxFilter(size))


def _occupancy_from_mask(mask: Image.Image, columns: int, rows: int, config: FlatPhotoPartConfig) -> set[tuple[int, int]]:
    pixels = mask.load()
    occupied: set[tuple[int, int]] = set()
    width_px, height_px = mask.size

    for row in range(rows):
        y0 = int(row * height_px / rows)
        y1 = max(y0 + 1, int(math.ceil((row + 1) * height_px / rows)))
        for col in range(columns):
            x0 = int(col * width_px / columns)
            x1 = max(x0 + 1, int(math.ceil((col + 1) * width_px / columns)))
            total = 0
            filled = 0
            for y in range(y0, min(y1, height_px)):
                for x in range(x0, min(x1, width_px)):
                    total += 1
                    if pixels[x, y] >= config.alpha_threshold:
                        filled += 1
            if total > 0 and filled / total >= config.min_cell_coverage:
                occupied.add((row, col))

    return occupied


def _layer_conversion(layer: dict, target_width_mm: float, target_height_mm: float) -> dict:
    asset = layer["asset"]
    layer_width_mm = layer["scale"] * target_width_mm
    layer_height_mm = layer_width_mm * asset["heightPx"] / asset["widthPx"]
    x_mm = layer["x"] * target_width_mm
    y_mm = layer["y"] * target_height_mm
    return {
        "xMm": round(x_mm, 3),
        "yMm": round(y_mm, 3),
        "layerWidthMm": round(layer_width_mm, 3),
        "layerHeightMm": round(layer_height_mm, 3),
        "mmPerPx": layer_width_mm / asset["widthPx"],
    }


def _part_from_layer(
    layer: dict,
    artwork: dict,
    assets_dir: pathlib.Path,
    out_dir: pathlib.Path,
    config: FlatPhotoPartConfig,
) -> tuple[dict | None, Image.Image | None]:
    asset = layer["asset"]
    path = _asset_path(asset, assets_dir)
    if asset["mimeType"] != "image/png":
        return None, None
    if not path.exists():
        raise FileNotFoundError(path)

    image = Image.open(path).convert("RGBA")
    target_height_mm = config.target_width_mm / artwork["canvas"]["aspectRatio"]
    layer_mm = _layer_conversion(layer, config.target_width_mm, target_height_mm)
    mm_per_px = layer_mm["mmPerPx"]

    mask = _threshold_alpha(image, config.alpha_threshold)
    opaque_bbox = mask.getbbox()
    if opaque_bbox is None:
        return None, None

    dilation_px = math.ceil(config.outline_margin_mm / mm_per_px)
    backing_mask = _dilate(mask, dilation_px)
    backing_bbox = backing_mask.getbbox()
    if backing_bbox is None:
        return None, None

    cropped_mask = backing_mask.crop(backing_bbox)
    cropped_image = image.crop(backing_bbox)
    crop_w_px, crop_h_px = cropped_mask.size
    width_mm = crop_w_px * mm_per_px
    height_mm = crop_h_px * mm_per_px
    columns = max(1, math.ceil(width_mm / config.grid_cell_mm))
    rows = max(1, math.ceil(height_mm / config.grid_cell_mm))
    occupied = _occupancy_from_mask(cropped_mask, columns, rows, config)
    if not occupied:
        return None, None

    name = f"flat-part-{layer['layerIndex']}-{_slug(layer['layerId'])}"
    stl_path = out_dir / f"{name}.stl"
    triangles = _grid_triangles(
        occupied,
        columns,
        rows,
        width_mm,
        height_mm,
        config.part_thickness_mm,
    )
    triangle_count = _write_stl(stl_path, name, triangles)

    crop_center_x_px = (backing_bbox[0] + backing_bbox[2]) / 2
    crop_center_y_px = (backing_bbox[1] + backing_bbox[3]) / 2
    center_x_mm = layer_mm["xMm"] + (crop_center_x_px - asset["widthPx"] / 2) * mm_per_px
    center_y_mm = layer_mm["yMm"] + (crop_center_y_px - asset["heightPx"] / 2) * mm_per_px

    part = {
        "layerId": layer["layerId"],
        "label": layer["label"],
        "sourcePhotoId": layer["sourcePhotoId"],
        "sourceLayerId": layer["sourceLayerId"],
        "assetId": asset["assetId"],
        "assetPath": str(path.relative_to(ROOT)).replace("\\", "/"),
        "layerIndex": layer["layerIndex"],
        "outputStl": str(stl_path.relative_to(ROOT)).replace("\\", "/"),
        "triangles": triangle_count,
        "flatSurface": True,
        "usesRelief": False,
        "usesHeightmap": False,
        "dimensionsMm": {
            "widthMm": round(width_mm, 3),
            "heightMm": round(height_mm, 3),
            "thicknessMm": round(config.part_thickness_mm, 3),
        },
        "artworkPlacementMm": {
            "centerXMm": round(center_x_mm, 3),
            "centerYMm": round(center_y_mm, 3),
            "layerWidthMm": layer_mm["layerWidthMm"],
            "layerHeightMm": layer_mm["layerHeightMm"],
        },
        "alphaCropPx": {
            "opaque": {
                "left": opaque_bbox[0],
                "top": opaque_bbox[1],
                "right": opaque_bbox[2],
                "bottom": opaque_bbox[3],
            },
            "backing": {
                "left": backing_bbox[0],
                "top": backing_bbox[1],
                "right": backing_bbox[2],
                "bottom": backing_bbox[3],
            },
        },
        "grid": {
            "columns": columns,
            "rows": rows,
            "occupiedCells": len(occupied),
            "totalCells": columns * rows,
        },
    }
    return part, cropped_image


def _image_data_uri(image: Image.Image) -> str:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _write_print_layout(
    path: pathlib.Path,
    parts: list[dict],
    cropped_images: list[Image.Image],
    config: FlatPhotoPartConfig,
) -> None:
    page_width = 210.0
    margin = config.print_layout_margin_mm
    gutter = config.print_layout_gutter_mm
    label_gap = 3.0
    label_height = 5.0
    x = margin
    y = margin
    row_height = 0.0
    placements = []

    for part in parts:
        width = part["dimensionsMm"]["widthMm"]
        height = part["dimensionsMm"]["heightMm"]
        total_height = height + label_gap + label_height
        if x + width > page_width - margin and x > margin:
            x = margin
            y += row_height + gutter
            row_height = 0.0
        placements.append((x, y))
        part["printLayoutMm"] = {
            "xMm": round(x, 3),
            "yMm": round(y, 3),
            "widthMm": round(width, 3),
            "heightMm": round(height, 3),
        }
        x += width + gutter
        row_height = max(row_height, total_height)

    page_height = max(80.0, y + row_height + margin)
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_width:.3f}mm" '
            f'height="{page_height:.3f}mm" viewBox="0 0 {page_width:.3f} {page_height:.3f}">'
        ),
        '<rect x="0" y="0" width="100%" height="100%" fill="white"/>',
    ]

    for (x, y), part, image in zip(placements, parts, cropped_images):
        width = part["dimensionsMm"]["widthMm"]
        height = part["dimensionsMm"]["heightMm"]
        label = html.escape(f"{part['layerId']} / {part['label']}")
        lines.extend(
            [
                "<g>",
                (
                    f'<image x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" '
                    f'height="{height:.3f}" href="{_image_data_uri(image)}" '
                    'preserveAspectRatio="none"/>'
                ),
                (
                    f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" '
                    f'height="{height:.3f}" fill="none" stroke="#111" '
                    'stroke-width="0.25" stroke-dasharray="1 1"/>'
                ),
                (
                    f'<text x="{x:.3f}" y="{(y + height + label_gap + 3.5):.3f}" '
                    'font-family="Arial, sans-serif" font-size="3.5" '
                    f'fill="#111">{label}</text>'
                ),
                "</g>",
            ]
        )

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _selected_layers(artwork: dict, layer_ids: set[str], include_background: bool) -> list[dict]:
    layers = sorted(artwork["layers"], key=lambda layer: layer["layerIndex"])
    if layer_ids:
        return [layer for layer in layers if layer["layerId"] in layer_ids]
    if include_background:
        return layers
    return [layer for layer in layers if layer["layerIndex"] > 0]


def build_poc(
    artwork_path: pathlib.Path,
    assets_dir: pathlib.Path,
    out_dir: pathlib.Path,
    config: FlatPhotoPartConfig,
    layer_ids: set[str],
    include_background: bool,
) -> dict:
    artwork = _load_json(artwork_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    selected_layers = _selected_layers(artwork, layer_ids, include_background)
    parts: list[dict] = []
    cropped_images: list[Image.Image] = []
    warnings: list[str] = []

    for layer in selected_layers:
        part, cropped_image = _part_from_layer(layer, artwork, assets_dir, out_dir, config)
        if part is None or cropped_image is None:
            warnings.append(f"{layer['layerId']}: flat part was not generated")
            continue
        parts.append(part)
        cropped_images.append(cropped_image)

    print_layout_path = out_dir / "flat-photo-print-layout.svg"
    if parts:
        _write_print_layout(print_layout_path, parts, cropped_images, config)

    report_path = out_dir / "flat-photo-parts-report.json"
    report = {
        "ok": bool(parts) and not warnings,
        "artworkId": artwork["artworkId"],
        "input": {
            "artwork": str(artwork_path.relative_to(ROOT)).replace("\\", "/"),
            "assetsDir": str(assets_dir.relative_to(ROOT)).replace("\\", "/"),
        },
        "flatPhotoPartConfig": _config_to_json(config),
        "parts": parts,
        "outputs": {
            "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "printLayoutSvg": str(print_layout_path.relative_to(ROOT)).replace("\\", "/") if parts else None,
            "stlFiles": [part["outputStl"] for part in parts],
        },
        "warnings": warnings,
        "schemaImpact": {
            "needsArtworkSchemaChange": False,
            "reason": "Flat parts can be generated from existing layer alpha, x / y / scale / layerIndex, and asset dimensions. Manufacturing values remain in FlatPhotoPartConfig.",
        },
        "recommendation": {
            "runtime": "independent local script for this flat-part PoC",
            "repositoryPlacement": "keep in scripts/ while STL runtime is PoC-after-FIX; do not add a root physical-output/ directory yet",
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate flat STL photo parts from shared mock Artwork layers.")
    parser.add_argument("--artwork", type=pathlib.Path, default=DEFAULT_ARTWORK)
    parser.add_argument("--assets", type=pathlib.Path, default=DEFAULT_ASSETS)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--target-width-mm", type=float, default=FlatPhotoPartConfig.target_width_mm)
    parser.add_argument("--part-thickness-mm", type=float, default=FlatPhotoPartConfig.part_thickness_mm)
    parser.add_argument("--outline-margin-mm", type=float, default=FlatPhotoPartConfig.outline_margin_mm)
    parser.add_argument("--grid-cell-mm", type=float, default=FlatPhotoPartConfig.grid_cell_mm)
    parser.add_argument("--include-background", action="store_true")
    parser.add_argument("--layer-id", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = FlatPhotoPartConfig(
        target_width_mm=args.target_width_mm,
        part_thickness_mm=args.part_thickness_mm,
        outline_margin_mm=args.outline_margin_mm,
        grid_cell_mm=args.grid_cell_mm,
    )
    report = build_poc(
        args.artwork,
        args.assets,
        args.out,
        config,
        set(args.layer_id),
        args.include_background,
    )
    print(json.dumps({
        "ok": report["ok"],
        "artworkId": report["artworkId"],
        "partCount": len(report["parts"]),
        "stlFiles": report["outputs"]["stlFiles"],
        "printLayoutSvg": report["outputs"]["printLayoutSvg"],
        "report": report["outputs"]["report"],
        "warnings": report["warnings"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
