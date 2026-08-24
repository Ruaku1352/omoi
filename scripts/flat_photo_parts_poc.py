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
    tab_width_mm: float = 8.0
    tab_height_mm: float = 7.0
    tab_edge_margin_mm: float = 4.0
    slot_clearance_mm: float = 0.4
    slot_side_clearance_mm: float = 0.8
    base_margin_x_mm: float = 12.0
    base_margin_y_mm: float = 8.0
    base_layer_gap_mm: float = 7.0
    base_height_mm: float = 8.0
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
        "tabWidthMm": config.tab_width_mm,
        "tabHeightMm": config.tab_height_mm,
        "tabEdgeMarginMm": config.tab_edge_margin_mm,
        "slotClearanceMm": config.slot_clearance_mm,
        "slotSideClearanceMm": config.slot_side_clearance_mm,
        "baseMarginXMm": config.base_margin_x_mm,
        "baseMarginYMm": config.base_margin_y_mm,
        "baseLayerGapMm": config.base_layer_gap_mm,
        "baseHeightMm": config.base_height_mm,
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


def _box_triangles(
    min_x: float,
    min_y: float,
    min_z: float,
    max_x: float,
    max_y: float,
    max_z: float,
) -> list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]:
    if min_x >= max_x or min_y >= max_y or min_z >= max_z:
        return []

    v000 = (min_x, min_y, min_z)
    v100 = (max_x, min_y, min_z)
    v110 = (max_x, max_y, min_z)
    v010 = (min_x, max_y, min_z)
    v001 = (min_x, min_y, max_z)
    v101 = (max_x, min_y, max_z)
    v111 = (max_x, max_y, max_z)
    v011 = (min_x, max_y, max_z)

    return [
        (v000, v010, v110), (v000, v110, v100),
        (v001, v101, v111), (v001, v111, v011),
        (v000, v100, v101), (v000, v101, v001),
        (v010, v011, v111), (v010, v111, v110),
        (v000, v001, v011), (v000, v011, v010),
        (v100, v110, v111), (v100, v111, v101),
    ]


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


def _tab_specs(width_mm: float, image_height_mm: float, config: FlatPhotoPartConfig) -> list[dict]:
    edge_margin = min(config.tab_edge_margin_mm, max(width_mm * 0.15, 1.0))
    usable_width = max(width_mm - edge_margin * 2, 1.0)
    tab_count = 2 if usable_width >= config.tab_width_mm * 2 + edge_margin else 1

    if tab_count == 1:
        tab_width = min(config.tab_width_mm, usable_width)
        starts = [(width_mm - tab_width) / 2]
    else:
        tab_width = min(config.tab_width_mm, usable_width / 3)
        starts = [
            edge_margin,
            width_mm - edge_margin - tab_width,
        ]

    return [
        {
            "tabId": f"tab-{index + 1}",
            "xMm": round(start, 3),
            "yMm": round(image_height_mm, 3),
            "widthMm": round(tab_width, 3),
            "heightMm": round(config.tab_height_mm, 3),
        }
        for index, start in enumerate(starts)
    ]


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

    tabs = _tab_specs(width_mm, height_mm, config)
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
    for tab in tabs:
        triangles += _box_triangles(
            tab["xMm"],
            height_mm,
            0.0,
            tab["xMm"] + tab["widthMm"],
            height_mm + config.tab_height_mm,
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
            "heightMm": round(height_mm + config.tab_height_mm, 3),
            "thicknessMm": round(config.part_thickness_mm, 3),
        },
        "imageAreaMm": {
            "xMm": 0.0,
            "yMm": 0.0,
            "widthMm": round(width_mm, 3),
            "heightMm": round(height_mm, 3),
        },
        "tabs": tabs,
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


def _merge_intervals(intervals: list[tuple[float, float]], min_value: float, max_value: float) -> list[tuple[float, float]]:
    clipped = [
        (max(min_value, start), min(max_value, end))
        for start, end in intervals
        if start < max_value and end > min_value
    ]
    clipped = [(start, end) for start, end in clipped if start < end]
    if not clipped:
        return []

    clipped.sort()
    merged = [clipped[0]]
    for start, end in clipped[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def _complement_intervals(intervals: list[tuple[float, float]], min_value: float, max_value: float) -> list[tuple[float, float]]:
    solid: list[tuple[float, float]] = []
    cursor = min_value
    for start, end in intervals:
        if cursor < start:
            solid.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < max_value:
        solid.append((cursor, max_value))
    return solid


def _base_triangles_for_parts(parts: list[dict], config: FlatPhotoPartConfig) -> tuple[list, dict]:
    slot_width = config.part_thickness_mm + config.slot_clearance_mm
    pitch = slot_width + config.base_layer_gap_mm
    base_width = config.target_width_mm + config.base_margin_x_mm * 2
    base_depth = config.base_margin_y_mm * 2 + slot_width * len(parts) + config.base_layer_gap_mm * max(len(parts) - 1, 0)
    tris = []
    slots = []

    y_spans: list[tuple[float, float, list[tuple[float, float]]]] = []
    cursor = 0.0
    for slot_index, part in enumerate(parts):
        slot_front = config.base_margin_y_mm + slot_index * pitch
        slot_back = slot_front + slot_width
        if cursor < slot_front:
            y_spans.append((cursor, slot_front, []))

        image_width = part["imageAreaMm"]["widthMm"]
        part_left_artwork = part["artworkPlacementMm"]["centerXMm"] - image_width / 2
        openings = []
        tab_slots = []
        for tab_index, tab in enumerate(part["tabs"]):
            tab_left = config.base_margin_x_mm + part_left_artwork + tab["xMm"]
            tab_right = tab_left + tab["widthMm"]
            opening = (
                tab_left - config.slot_side_clearance_mm / 2,
                tab_right + config.slot_side_clearance_mm / 2,
            )
            openings.append(opening)
            tab_slot = {
                "tabId": tab["tabId"],
                "slotId": f"slot-{slot_index + 1}-{tab_index + 1}",
                "xStartMm": round(opening[0], 3),
                "xEndMm": round(opening[1], 3),
                "frontMm": round(slot_front, 3),
                "backMm": round(slot_back, 3),
            }
            tab["baseSlot"] = tab_slot
            tab_slots.append(tab_slot)

        slot = {
            "slotIndex": slot_index,
            "layerId": part["layerId"],
            "layerIndex": part["layerIndex"],
            "frontMm": round(slot_front, 3),
            "backMm": round(slot_back, 3),
            "slotWidthMm": round(slot_width, 3),
            "tabSlots": tab_slots,
        }
        part["baseSlot"] = {
            "slotIndex": slot_index,
            "frontMm": round(slot_front, 3),
            "backMm": round(slot_back, 3),
            "slotWidthMm": round(slot_width, 3),
        }
        slots.append(slot)
        y_spans.append((slot_front, slot_back, openings))
        cursor = slot_back

    if cursor < base_depth:
        y_spans.append((cursor, base_depth, []))

    for y0, y1, openings in y_spans:
        merged = _merge_intervals(openings, 0.0, base_width)
        for x0, x1 in _complement_intervals(merged, 0.0, base_width):
            tris += _box_triangles(x0, y0, 0.0, x1, y1, config.base_height_mm)

    base = {
        "dimensionsMm": {
            "widthMm": round(base_width, 3),
            "depthMm": round(base_depth, 3),
            "heightMm": round(config.base_height_mm, 3),
        },
        "slots": slots,
    }
    return tris, base


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
        image_height = part["imageAreaMm"]["heightMm"]
        label = html.escape(f"{part['layerId']} / {part['label']}")
        lines.extend(
            [
                "<g>",
                (
                    f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" '
                    f'height="{height:.3f}" fill="#f8f8f8" stroke="#e11d48" '
                    'stroke-width="0.35" stroke-dasharray="1.5 1"/>'
                ),
                (
                    f'<image x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" '
                    f'height="{image_height:.3f}" href="{_image_data_uri(image)}" '
                    'preserveAspectRatio="none"/>'
                ),
                (
                    f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" '
                    f'height="{image_height:.3f}" fill="none" stroke="#111" '
                    'stroke-width="0.25"/>'
                ),
                (
                    f'<line x1="{x:.3f}" y1="{(y + image_height):.3f}" '
                    f'x2="{(x + width):.3f}" y2="{(y + image_height):.3f}" '
                    'stroke="#e11d48" stroke-width="0.25" stroke-dasharray="1 1"/>'
                ),
                (
                    f'<text x="{x:.3f}" y="{(y + height + label_gap + 3.5):.3f}" '
                    'font-family="Arial, sans-serif" font-size="3.5" '
                    f'fill="#111">{label}</text>'
                ),
            ]
        )
        for tab in part["tabs"]:
            tab_x = x + tab["xMm"]
            tab_y = y + tab["yMm"]
            tab_label = html.escape(tab["tabId"])
            lines.extend(
                [
                    (
                        f'<rect x="{tab_x:.3f}" y="{tab_y:.3f}" width="{tab["widthMm"]:.3f}" '
                        f'height="{tab["heightMm"]:.3f}" fill="#fce7f3" stroke="#e11d48" '
                        'stroke-width="0.35"/>'
                    ),
                    (
                        f'<text x="{(tab_x + tab["widthMm"] / 2):.3f}" '
                        f'y="{(tab_y + tab["heightMm"] / 2 + 1.1):.3f}" '
                        'font-family="Arial, sans-serif" font-size="2.5" '
                        f'text-anchor="middle" fill="#9f1239">{tab_label}</text>'
                    ),
                ]
            )
        lines.extend(
            [
                (
                    f'<text x="{x:.3f}" y="{(y - 2.0):.3f}" '
                    'font-family="Arial, sans-serif" font-size="3" '
                    'fill="#111">print area + cut tabs</text>'
                ),
                (
                    f'<text x="{x:.3f}" y="{(y + image_height + 4.0):.3f}" '
                    'font-family="Arial, sans-serif" font-size="2.8" '
                    'fill="#9f1239">tabs go into base slots</text>'
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

    base = None
    base_path = out_dir / "flat-photo-parts-slot-base.stl"
    if parts:
        base_triangles, base = _base_triangles_for_parts(parts, config)
        base["outputStl"] = str(base_path.relative_to(ROOT)).replace("\\", "/")
        base["triangles"] = _write_stl(base_path, "flat-photo-parts-slot-base", base_triangles)

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
        "base": base,
        "outputs": {
            "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "printLayoutSvg": str(print_layout_path.relative_to(ROOT)).replace("\\", "/") if parts else None,
            "stlFiles": [part["outputStl"] for part in parts] + ([base["outputStl"]] if base else []),
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
    parser.add_argument("--tab-width-mm", type=float, default=FlatPhotoPartConfig.tab_width_mm)
    parser.add_argument("--tab-height-mm", type=float, default=FlatPhotoPartConfig.tab_height_mm)
    parser.add_argument("--slot-clearance-mm", type=float, default=FlatPhotoPartConfig.slot_clearance_mm)
    parser.add_argument("--base-layer-gap-mm", type=float, default=FlatPhotoPartConfig.base_layer_gap_mm)
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
        tab_width_mm=args.tab_width_mm,
        tab_height_mm=args.tab_height_mm,
        slot_clearance_mm=args.slot_clearance_mm,
        base_layer_gap_mm=args.base_layer_gap_mm,
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
        "baseStl": report["base"]["outputStl"] if report["base"] else None,
        "stlFiles": report["outputs"]["stlFiles"],
        "printLayoutSvg": report["outputs"]["printLayoutSvg"],
        "report": report["outputs"]["report"],
        "warnings": report["warnings"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
