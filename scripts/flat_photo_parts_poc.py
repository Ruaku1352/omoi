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

from PIL import Image, ImageDraw, ImageFilter, ImageFont


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARTWORK = ROOT / "contracts" / "mock" / "artwork.json"
DEFAULT_ASSETS = ROOT / "contracts" / "assets"
DEFAULT_OUT = ROOT / "tmp" / "flat-photo-parts-poc"
EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}

PHOTO_2L_LANDSCAPE_WIDTH_MM = 178.0
PHOTO_2L_LANDSCAPE_HEIGHT_MM = 127.0
PHOTO_PRINT_DPI = 300.0
PHOTO_JPEG_QUALITY = 95


@dataclass(frozen=True)
class PhotoPdfPlacement:
    page_index: int
    x_mm: float
    y_mm: float
    width_mm: float
    height_mm: float
    overflows_page: bool


@dataclass(frozen=True)
class PhotoPdfLayout:
    page_width_mm: float
    page_height_mm: float
    placements: list[PhotoPdfPlacement]


@dataclass(frozen=True)
class FlatPhotoPartConfig:
    target_width_mm: float = 178.0
    part_thickness_mm: float = 1.6
    outline_margin_mm: float = 0.35
    shape_mode: str = "grid"
    contour_simplify_mm: float = 0.10
    grid_cell_mm: float = 0.6
    support_bridge_width_mm: float = 1.8
    vertical_support_width_mm: float = 4.0
    vertical_support_min_height_mm: float = 1.0
    support_root_pad_width_mm: float = 12.0
    support_root_pad_height_mm: float = 5.0
    support_root_overlap_mm: float = 2.0
    support_mode: str = "rail"
    tree_branch_width_mm: float = 2.4
    tree_support_edge_margin_mm: float = 4.0
    rail_body_height_mm: float = 4.0
    rail_support_width_mm: float = 10.0
    rail_edge_margin_mm: float = 0.0
    mount_mode: str = "front-tab"
    tab_width_mm: float = 12.0
    tab_height_mm: float = 5.0
    tab_overlap_mm: float = 2.0
    tab_edge_margin_mm: float = 4.0
    slot_clearance_mm: float = 0.35
    slot_side_clearance_mm: float = 0.8
    base_mode: str = "square-grid"
    base_width_mm: float = 170.0
    base_depth_mm: float = 121.0
    base_layer_capacity: int = 4
    base_slots_per_layer: int = 3
    base_slot_length_mm: float = 12.0
    base_margin_x_mm: float = 12.0
    base_margin_y_mm: float = 11.0
    base_back_margin_y_mm: float = 5.0
    base_layer_gap_mm: float = 7.0
    base_height_mm: float = 5.0
    base_slot_label_engrave_depth_mm: float = 0.45
    base_slot_label_digit_height_mm: float = 6.0
    base_slot_label_offset_y_mm: float = 1.0
    base_slot_label_gap_mm: float = 0.7
    part_slot_label_engrave_depth_mm: float = 0.35
    part_slot_label_digit_height_mm: float = 4.0
    part_slot_label_offset_y_mm: float = 0.4
    part_slot_label_gap_mm: float = 0.45
    part_slot_label_mirror_for_back_side: bool = True
    alpha_threshold: int = 16
    min_cell_coverage: float = 0.10
    background_fill_mode: str = "cover-2l"
    print_layout_margin_mm: float = 10.0
    print_layout_gutter_mm: float = 6.0
    print_layout_page_width_mm: float = PHOTO_2L_LANDSCAPE_WIDTH_MM
    print_layout_page_height_mm: float = PHOTO_2L_LANDSCAPE_HEIGHT_MM
    print_layout_dpi: float = PHOTO_PRINT_DPI
    photo_jpeg_quality: int = PHOTO_JPEG_QUALITY
    material: str = "PLA"


def _config_to_json(config: FlatPhotoPartConfig) -> dict:
    return {
        "targetWidthMm": config.target_width_mm,
        "partThicknessMm": config.part_thickness_mm,
        "outlineMarginMm": config.outline_margin_mm,
        "shapeMode": config.shape_mode,
        "contourSimplifyMm": config.contour_simplify_mm,
        "gridCellMm": config.grid_cell_mm,
        "supportBridgeWidthMm": config.support_bridge_width_mm,
        "verticalSupportWidthMm": config.vertical_support_width_mm,
        "verticalSupportMinHeightMm": config.vertical_support_min_height_mm,
        "supportRootPadWidthMm": config.support_root_pad_width_mm,
        "supportRootPadHeightMm": config.support_root_pad_height_mm,
        "supportRootOverlapMm": config.support_root_overlap_mm,
        "supportMode": config.support_mode,
        "treeBranchWidthMm": config.tree_branch_width_mm,
        "treeSupportEdgeMarginMm": config.tree_support_edge_margin_mm,
        "railBodyHeightMm": config.rail_body_height_mm,
        "railSupportWidthMm": config.rail_support_width_mm,
        "railEdgeMarginMm": config.rail_edge_margin_mm,
        "mountMode": config.mount_mode,
        "tabWidthMm": config.tab_width_mm,
        "tabHeightMm": config.tab_height_mm,
        "tabOverlapMm": config.tab_overlap_mm,
        "tabEdgeMarginMm": config.tab_edge_margin_mm,
        "slotClearanceMm": config.slot_clearance_mm,
        "slotSideClearanceMm": config.slot_side_clearance_mm,
        "baseMode": config.base_mode,
        "baseWidthMm": config.base_width_mm,
        "baseDepthMm": config.base_depth_mm,
        "baseLayerCapacity": config.base_layer_capacity,
        "baseSlotsPerLayer": config.base_slots_per_layer,
        "baseSlotLengthMm": config.base_slot_length_mm,
        "baseMarginXMm": config.base_margin_x_mm,
        "baseFrontMarginYMm": config.base_margin_y_mm,
        "baseBackMarginYMm": config.base_back_margin_y_mm,
        "baseLayerGapMm": config.base_layer_gap_mm,
        "baseHeightMm": config.base_height_mm,
        "baseSlotLabelEngraveDepthMm": config.base_slot_label_engrave_depth_mm,
        "baseSlotLabelDigitHeightMm": config.base_slot_label_digit_height_mm,
        "baseSlotLabelOffsetYMm": config.base_slot_label_offset_y_mm,
        "baseSlotLabelGapMm": config.base_slot_label_gap_mm,
        "partSlotLabelEngraveDepthMm": config.part_slot_label_engrave_depth_mm,
        "partSlotLabelDigitHeightMm": config.part_slot_label_digit_height_mm,
        "partSlotLabelOffsetYMm": config.part_slot_label_offset_y_mm,
        "partSlotLabelGapMm": config.part_slot_label_gap_mm,
        "partSlotLabelMirrorForBackSide": config.part_slot_label_mirror_for_back_side,
        "alphaThreshold": config.alpha_threshold,
        "minCellCoverage": config.min_cell_coverage,
        "backgroundFillMode": config.background_fill_mode,
        "printLayoutMarginMm": config.print_layout_margin_mm,
        "printLayoutGutterMm": config.print_layout_gutter_mm,
        "printLayoutPageWidthMm": config.print_layout_page_width_mm,
        "printLayoutPageHeightMm": config.print_layout_page_height_mm,
        "printLayoutDpi": config.print_layout_dpi,
        "photoJpegQuality": config.photo_jpeg_quality,
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


def _display_path(path: pathlib.Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(resolved).replace("\\", "/")


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


def _thick_segment_polygon(
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    width: float,
) -> list[tuple[float, float]]:
    dx = x1 - x0
    dy = y1 - y0
    length = math.hypot(dx, dy)
    if length <= 1e-9 or width <= 0:
        return []

    nx = -dy / length * width / 2
    ny = dx / length * width / 2
    return [
        (x0 + nx, y0 + ny),
        (x1 + nx, y1 + ny),
        (x1 - nx, y1 - ny),
        (x0 - nx, y0 - ny),
    ]


def _bottom_engraved_box_triangles(
    min_x: float,
    min_y: float,
    min_z: float,
    max_x: float,
    max_y: float,
    max_z: float,
    engrave_rects: list[tuple[float, float, float, float]],
    engrave_depth: float,
) -> list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]:
    if min_x >= max_x or min_y >= max_y or min_z >= max_z:
        return []

    clipped_rects = [
        clipped
        for rect in engrave_rects
        if (clipped := _clipped_rect(rect, max_x, max_y, min_x, min_y)) is not None
    ]
    depth = max(0.0, min(engrave_depth, max_z - min_z - 0.2))
    if not clipped_rects or depth <= 0:
        return _box_triangles(min_x, min_y, min_z, max_x, max_y, max_z)

    engraved_min_z = min_z + depth
    x_edges = {round(min_x, 6), round(max_x, 6)}
    y_edges = {round(min_y, 6), round(max_y, 6)}
    for x0, y0, x1, y1 in clipped_rects:
        x_edges.update((round(x0, 6), round(x1, 6)))
        y_edges.update((round(y0, 6), round(y1, 6)))

    sorted_x_edges = sorted(x_edges)
    sorted_y_edges = sorted(y_edges)
    rows = len(sorted_y_edges) - 1
    columns = len(sorted_x_edges) - 1
    bottom_rows: list[list[float]] = []
    for row in range(rows):
        y0 = sorted_y_edges[row]
        y1 = sorted_y_edges[row + 1]
        center_y = (y0 + y1) / 2
        bottom_row = []
        for column in range(columns):
            x0 = sorted_x_edges[column]
            x1 = sorted_x_edges[column + 1]
            center_x = (x0 + x1) / 2
            if any(_rect_contains(rect, center_x, center_y) for rect in clipped_rects):
                bottom_row.append(engraved_min_z)
            else:
                bottom_row.append(min_z)
        bottom_rows.append(bottom_row)

    triangles = []

    def bottom_at(row: int, column: int) -> float | None:
        if row < 0 or row >= rows or column < 0 or column >= columns:
            return None
        return bottom_rows[row][column]

    for row in range(rows):
        y0 = sorted_y_edges[row]
        y1 = sorted_y_edges[row + 1]
        for column in range(columns):
            x0 = sorted_x_edges[column]
            x1 = sorted_x_edges[column + 1]
            bottom = bottom_rows[row][column]
            top = max_z

            triangles += _quad((x0, y0, top), (x1, y0, top), (x1, y1, top), (x0, y1, top))
            triangles += _quad(
                (x0, y1, bottom),
                (x1, y1, bottom),
                (x1, y0, bottom),
                (x0, y0, bottom),
            )

            neighbors = {
                "front": bottom_at(row - 1, column),
                "back": bottom_at(row + 1, column),
                "left": bottom_at(row, column - 1),
                "right": bottom_at(row, column + 1),
            }
            if neighbors["front"] is None:
                triangles += _quad(
                    (x0, y0, bottom),
                    (x1, y0, bottom),
                    (x1, y0, top),
                    (x0, y0, top),
                )
            elif neighbors["front"] > bottom:
                neighbor = neighbors["front"]
                triangles += _quad(
                    (x0, y0, bottom),
                    (x1, y0, bottom),
                    (x1, y0, neighbor),
                    (x0, y0, neighbor),
                )

            if neighbors["back"] is None:
                triangles += _quad(
                    (x1, y1, bottom),
                    (x0, y1, bottom),
                    (x0, y1, top),
                    (x1, y1, top),
                )
            elif neighbors["back"] > bottom:
                neighbor = neighbors["back"]
                triangles += _quad(
                    (x1, y1, bottom),
                    (x0, y1, bottom),
                    (x0, y1, neighbor),
                    (x1, y1, neighbor),
                )

            if neighbors["left"] is None:
                triangles += _quad(
                    (x0, y1, bottom),
                    (x0, y0, bottom),
                    (x0, y0, top),
                    (x0, y1, top),
                )
            elif neighbors["left"] > bottom:
                neighbor = neighbors["left"]
                triangles += _quad(
                    (x0, y1, bottom),
                    (x0, y0, bottom),
                    (x0, y0, neighbor),
                    (x0, y1, neighbor),
                )

            if neighbors["right"] is None:
                triangles += _quad(
                    (x1, y0, bottom),
                    (x1, y1, bottom),
                    (x1, y1, top),
                    (x1, y0, top),
                )
            elif neighbors["right"] > bottom:
                neighbor = neighbors["right"]
                triangles += _quad(
                    (x1, y0, bottom),
                    (x1, y1, bottom),
                    (x1, y1, neighbor),
                    (x1, y0, neighbor),
                )

    return triangles


def _translate_triangles(
    triangles: list[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
    dx: float,
    dy: float,
    dz: float,
) -> list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]:
    return [
        tuple((x + dx, y + dy, z + dz) for x, y, z in triangle)
        for triangle in triangles
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


def _cell_neighbors(
    cell: tuple[int, int],
    columns: int,
    rows: int,
) -> list[tuple[int, int]]:
    row, col = cell
    neighbors = []
    if row > 0:
        neighbors.append((row - 1, col))
    if row < rows - 1:
        neighbors.append((row + 1, col))
    if col > 0:
        neighbors.append((row, col - 1))
    if col < columns - 1:
        neighbors.append((row, col + 1))
    return neighbors


def _occupied_components(
    occupied: set[tuple[int, int]],
    columns: int,
    rows: int,
) -> list[set[tuple[int, int]]]:
    remaining = set(occupied)
    components: list[set[tuple[int, int]]] = []

    while remaining:
        start = remaining.pop()
        component = {start}
        stack = [start]
        while stack:
            current = stack.pop()
            for neighbor in _cell_neighbors(current, columns, rows):
                if neighbor not in remaining:
                    continue
                remaining.remove(neighbor)
                component.add(neighbor)
                stack.append(neighbor)
        components.append(component)

    return sorted(components, key=len, reverse=True)


def _trace_cell_path(
    previous: dict[tuple[int, int], tuple[int, int] | None],
    start: tuple[int, int],
) -> list[tuple[int, int]]:
    path = [start]
    current = start
    while previous.get(current) is not None:
        current = previous[current]
        path.append(current)
    return path


def _paint_bridge_cells(
    occupied: set[tuple[int, int]],
    path: list[tuple[int, int]],
    columns: int,
    rows: int,
    radius_cells: int,
) -> set[tuple[int, int]]:
    painted: set[tuple[int, int]] = set()
    for row, col in path:
        for dy in range(-radius_cells, radius_cells + 1):
            for dx in range(-radius_cells, radius_cells + 1):
                if dx * dx + dy * dy > radius_cells * radius_cells:
                    continue
                next_row = row + dy
                next_col = col + dx
                if 0 <= next_row < rows and 0 <= next_col < columns:
                    cell = (next_row, next_col)
                    occupied.add(cell)
                    painted.add(cell)
    return painted


def _bridge_component_to_connected(
    occupied: set[tuple[int, int]],
    connected: set[tuple[int, int]],
    component: set[tuple[int, int]],
    columns: int,
    rows: int,
    radius_cells: int,
) -> bool:
    queue = list(component)
    previous: dict[tuple[int, int], tuple[int, int] | None] = {
        cell: None for cell in component
    }
    cursor = 0

    while cursor < len(queue):
        current = queue[cursor]
        cursor += 1

        for neighbor in _cell_neighbors(current, columns, rows):
            if neighbor in connected:
                painted = _paint_bridge_cells(
                    occupied,
                    _trace_cell_path(previous, current),
                    columns,
                    rows,
                    radius_cells,
                )
                connected.update(component)
                connected.update(painted)
                return True
            if neighbor in occupied or neighbor in previous:
                continue
            previous[neighbor] = current
            queue.append(neighbor)

    return False


def _connect_occupied_components(
    occupied: set[tuple[int, int]],
    columns: int,
    rows: int,
    config: FlatPhotoPartConfig,
) -> dict:
    components = _occupied_components(occupied, columns, rows)
    bridge_count = 0
    radius_cells = max(
        0,
        math.floor(config.support_bridge_width_mm / config.grid_cell_mm / 2),
    )

    connected = set(components[0]) if components else set()
    for component in components[1:]:
        if _bridge_component_to_connected(
            occupied,
            connected,
            component,
            columns,
            rows,
            radius_cells,
        ):
            bridge_count += 1

    connected_components = _occupied_components(occupied, columns, rows)
    return {
        "originalComponentCount": len(components),
        "floatingComponentCount": max(len(components) - 1, 0),
        "supportBridgeCount": bridge_count,
        "connectedComponentCount": len(connected_components),
        "supportBridgeWidthMm": round(config.support_bridge_width_mm, 3),
    }


def _signed_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for i, current in enumerate(points):
        nxt = points[(i + 1) % len(points)]
        area += current[0] * nxt[1] - nxt[0] * current[1]
    return area / 2.0


def _cross(
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _point_in_triangle(
    point: tuple[float, float],
    a: tuple[float, float],
    b: tuple[float, float],
    c: tuple[float, float],
) -> bool:
    d1 = _cross(point, a, b)
    d2 = _cross(point, b, c)
    d3 = _cross(point, c, a)
    has_neg = d1 < -1e-9 or d2 < -1e-9 or d3 < -1e-9
    has_pos = d1 > 1e-9 or d2 > 1e-9 or d3 > 1e-9
    return not (has_neg and has_pos)


def _dedupe_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for point in points:
        if not deduped or math.dist(deduped[-1], point) > 1e-6:
            deduped.append(point)
    if len(deduped) > 1 and math.dist(deduped[0], deduped[-1]) <= 1e-6:
        deduped.pop()
    return deduped


def _triangulate_polygon(
    points: list[tuple[float, float]],
) -> list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]]:
    polygon = _dedupe_points(points)
    if len(polygon) < 3:
        return []
    if _signed_area(polygon) < 0:
        polygon.reverse()

    remaining = list(range(len(polygon)))
    triangles: list[tuple[tuple[float, float], tuple[float, float], tuple[float, float]]] = []
    guard = len(polygon) * len(polygon)

    while len(remaining) > 3 and guard > 0:
        guard -= 1
        clipped = False
        for pos, index in enumerate(remaining):
            prev_index = remaining[pos - 1]
            next_index = remaining[(pos + 1) % len(remaining)]
            a, b, c = polygon[prev_index], polygon[index], polygon[next_index]
            if _cross(a, b, c) <= 1e-9:
                continue

            has_inside = False
            for other_index in remaining:
                if other_index in (prev_index, index, next_index):
                    continue
                if _point_in_triangle(polygon[other_index], a, b, c):
                    has_inside = True
                    break
            if has_inside:
                continue

            triangles.append((a, b, c))
            del remaining[pos]
            clipped = True
            break

        if not clipped:
            return []

    if len(remaining) == 3:
        a, b, c = (polygon[i] for i in remaining)
        if abs(_cross(a, b, c)) > 1e-9:
            triangles.append((a, b, c))
    return triangles


def _polygon_triangles(
    polygon: list[tuple[float, float]],
    thickness_mm: float,
) -> list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]:
    points = _dedupe_points(polygon)
    if len(points) < 3:
        return []
    if _signed_area(points) < 0:
        points.reverse()

    surface_triangles = _triangulate_polygon(points)
    if not surface_triangles:
        return []

    tris = []
    for a, b, c in surface_triangles:
        tris.append(((a[0], a[1], thickness_mm), (b[0], b[1], thickness_mm), (c[0], c[1], thickness_mm)))
        tris.append(((c[0], c[1], 0.0), (b[0], b[1], 0.0), (a[0], a[1], 0.0)))

    for i, current in enumerate(points):
        nxt = points[(i + 1) % len(points)]
        tris += _quad(
            (current[0], current[1], 0.0),
            (nxt[0], nxt[1], 0.0),
            (nxt[0], nxt[1], thickness_mm),
            (current[0], current[1], thickness_mm),
        )
    return tris


def _contour_shape_triangles(
    mask: Image.Image,
    mm_per_px: float,
    config: FlatPhotoPartConfig,
) -> tuple[
    list[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
    dict,
] | None:
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None

    data = np.array(mask, dtype=np.uint8)
    contours, _ = cv2.findContours(data, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return None

    epsilon_px = max(config.contour_simplify_mm / mm_per_px, 0.5)
    min_area_px = max(4.0, (0.5 / mm_per_px) ** 2)
    triangles = []
    contour_reports = []

    for contour in sorted(contours, key=cv2.contourArea, reverse=True):
        area_px = float(cv2.contourArea(contour))
        if area_px < min_area_px:
            continue
        approx = cv2.approxPolyDP(contour, epsilon_px, True)
        points = [
            (float(point[0][0]) * mm_per_px, float(point[0][1]) * mm_per_px)
            for point in approx
        ]
        polygon_tris = _polygon_triangles(points, config.part_thickness_mm)
        if not polygon_tris:
            continue
        triangles += polygon_tris
        contour_reports.append(
            {
                "areaPx": round(area_px, 3),
                "vertices": len(_dedupe_points(points)),
                "triangles": len(polygon_tris),
            }
        )

    if not triangles:
        return None
    if len(contour_reports) > 1:
        return None

    return triangles, {
        "strategy": "contour",
        "contours": contour_reports,
        "contourCount": len(contour_reports),
        "fallbackUsed": False,
        "originalComponentCount": 1,
        "floatingComponentCount": 0,
        "supportBridgeCount": 0,
        "connectedComponentCount": 1,
    }


def _grid_shape_triangles(
    mask: Image.Image,
    width_mm: float,
    height_mm: float,
    config: FlatPhotoPartConfig,
) -> tuple[
    list[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
    dict,
]:
    columns = max(1, math.ceil(width_mm / config.grid_cell_mm))
    rows = max(1, math.ceil(height_mm / config.grid_cell_mm))
    occupied = _occupancy_from_mask(mask, columns, rows, config)
    connectivity = _connect_occupied_components(occupied, columns, rows, config)
    return (
        _grid_triangles(
            occupied,
            columns,
            rows,
            width_mm,
            height_mm,
            config.part_thickness_mm,
        ),
        {
            "strategy": "grid",
            "fallbackUsed": config.shape_mode == "contour",
            "columns": columns,
            "rows": rows,
            "occupiedCells": len(occupied),
            "totalCells": columns * rows,
            **connectivity,
        },
    )


def _flat_shape_triangles(
    mask: Image.Image,
    width_mm: float,
    height_mm: float,
    mm_per_px: float,
    config: FlatPhotoPartConfig,
) -> tuple[
    list[
        tuple[
            tuple[float, float, float],
            tuple[float, float, float],
            tuple[float, float, float],
        ]
    ],
    dict,
]:
    if config.shape_mode == "contour":
        contour_result = _contour_shape_triangles(mask, mm_per_px, config)
        if contour_result is not None:
            return contour_result
    return _grid_shape_triangles(mask, width_mm, height_mm, config)


def _threshold_alpha(image: Image.Image, threshold: int) -> Image.Image:
    return image.getchannel("A").point(lambda value: 255 if value >= threshold else 0)


def _dilate(mask: Image.Image, radius_px: int) -> Image.Image:
    if radius_px <= 0:
        return mask
    size = radius_px * 2 + 1
    return mask.filter(ImageFilter.MaxFilter(size))


def _is_cover_background_layer(
    layer: dict,
    mask: Image.Image,
    config: FlatPhotoPartConfig,
) -> bool:
    bbox = mask.getbbox()
    return (
        config.background_fill_mode == "cover-2l"
        and layer["layerIndex"] == 0
        and bbox == (0, 0, mask.width, mask.height)
    )


def _cover_crop_box(
    source_width_px: int,
    source_height_px: int,
    target_width_mm: float,
    target_height_mm: float,
) -> tuple[int, int, int, int]:
    source_aspect = source_width_px / source_height_px
    target_aspect = target_width_mm / target_height_mm

    if source_aspect < target_aspect:
        crop_height = max(1, min(source_height_px, round(source_width_px / target_aspect)))
        top = max(0, (source_height_px - crop_height) // 2)
        return (0, top, source_width_px, top + crop_height)

    crop_width = max(1, min(source_width_px, round(source_height_px * target_aspect)))
    left = max(0, (source_width_px - crop_width) // 2)
    return (left, 0, left + crop_width, source_height_px)


def _cover_crop_report(
    crop_box: tuple[int, int, int, int],
    source_width_px: int,
    source_height_px: int,
    target_width_mm: float,
    target_height_mm: float,
) -> dict:
    left, top, right, bottom = crop_box
    return {
        "mode": "cover-2l",
        "sourceSizePx": {
            "widthPx": source_width_px,
            "heightPx": source_height_px,
        },
        "cropPx": {
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "widthPx": right - left,
            "heightPx": bottom - top,
        },
        "targetSizeMm": {
            "widthMm": round(target_width_mm, 3),
            "heightMm": round(target_height_mm, 3),
        },
    }


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


def _bottom_support_intervals(mask: Image.Image, mm_per_px: float) -> list[tuple[float, float]]:
    bbox = mask.getbbox()
    if bbox is None:
        return []

    scan_px = max(1, math.ceil(4.0 / mm_per_px))
    y0 = max(bbox[1], bbox[3] - scan_px)
    y1 = bbox[3]
    pixels = mask.load()
    intervals: list[tuple[float, float]] = []
    start: int | None = None

    for x in range(bbox[0], bbox[2]):
        filled = any(pixels[x, y] >= 255 for y in range(y0, y1))
        if filled and start is None:
            start = x
        elif not filled and start is not None:
            intervals.append((start * mm_per_px, x * mm_per_px))
            start = None
    if start is not None:
        intervals.append((start * mm_per_px, bbox[2] * mm_per_px))

    return intervals


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(max(value, minimum), maximum)


def _rail_support_span(
    interval: tuple[float, float],
    desired_width_mm: float,
    anchor_ratio: float,
) -> dict | None:
    start_mm, end_mm = interval
    interval_width_mm = end_mm - start_mm
    if interval_width_mm <= 0:
        return None

    width_mm = min(desired_width_mm, interval_width_mm)
    center_mm = start_mm + interval_width_mm * anchor_ratio
    x_start_mm = _clamp(center_mm - width_mm / 2, start_mm, end_mm - width_mm)
    x_end_mm = x_start_mm + width_mm
    return {
        "xStartMm": round(x_start_mm, 3),
        "xEndMm": round(x_end_mm, 3),
        "anchorXMm": round((x_start_mm + x_end_mm) / 2, 3),
        "widthMm": round(width_mm, 3),
        "imageBottomIntervalMm": {
            "xStartMm": round(start_mm, 3),
            "xEndMm": round(end_mm, 3),
            "widthMm": round(interval_width_mm, 3),
        },
    }


def _rail_support_spans(
    support_intervals: list[tuple[float, float]],
    image_width_mm: float,
    config: FlatPhotoPartConfig,
) -> list[dict]:
    desired_width_mm = max(config.rail_support_width_mm, config.vertical_support_width_mm, 0.1)
    min_interval_width_mm = max(config.vertical_support_width_mm, desired_width_mm * 0.45, 0.5)
    intervals = [
        (max(0.0, start_mm), min(image_width_mm, end_mm))
        for start_mm, end_mm in support_intervals
        if end_mm > start_mm
    ]
    valid = [
        interval
        for interval in intervals
        if interval[1] - interval[0] >= min_interval_width_mm
    ]

    if not valid:
        fallback_width_mm = min(desired_width_mm, max(image_width_mm, 0.1))
        center_mm = image_width_mm / 2
        x_start_mm = _clamp(center_mm - fallback_width_mm / 2, 0.0, image_width_mm - fallback_width_mm)
        return [
            {
                "xStartMm": round(x_start_mm, 3),
                "xEndMm": round(x_start_mm + fallback_width_mm, 3),
                "anchorXMm": round(x_start_mm + fallback_width_mm / 2, 3),
                "widthMm": round(fallback_width_mm, 3),
                "imageBottomIntervalMm": None,
            }
        ]

    widest = max(valid, key=lambda interval: interval[1] - interval[0])
    widest_width_mm = widest[1] - widest[0]
    spans: list[dict] = []
    if widest_width_mm >= desired_width_mm * 2.4:
        for anchor_ratio in (0.25, 0.75):
            span = _rail_support_span(widest, desired_width_mm, anchor_ratio)
            if span:
                spans.append(span)
        return spans

    if len(valid) >= 2 and valid[-1][1] - valid[0][0] >= desired_width_mm * 2.4:
        for interval in (valid[0], valid[-1]):
            span = _rail_support_span(interval, desired_width_mm, 0.5)
            if span:
                spans.append(span)
        return spans

    span = _rail_support_span(widest, desired_width_mm, 0.5)
    return [span] if span else []


def _support_root_pad_spec(
    *,
    anchor_x: float,
    support_width_mm: float,
    image_width_mm: float,
    image_height_mm: float,
    overlap_mm: float,
    config: FlatPhotoPartConfig,
) -> dict:
    root_overlap = min(max(config.support_root_overlap_mm, 0.0), image_height_mm)
    root_width = max(support_width_mm, config.support_root_pad_width_mm)
    root_width = min(root_width, image_width_mm + root_overlap * 2)
    root_x = anchor_x - root_width / 2
    root_y = image_height_mm - root_overlap
    root_height = max(config.support_root_pad_height_mm, overlap_mm + root_overlap)
    return {
        "xMm": round(root_x, 3),
        "yMm": round(root_y, 3),
        "widthMm": round(root_width, 3),
        "heightMm": round(root_height, 3),
        "overlapIntoImageMm": round(root_overlap, 3),
    }


def _tab_specs(
    width_mm: float,
    image_height_mm: float,
    config: FlatPhotoPartConfig,
    support_intervals: list[tuple[float, float]],
    vertical_support_height_mm: float = 0.0,
    slot_assignment: dict | None = None,
) -> list[dict]:
    edge_margin = min(config.tab_edge_margin_mm, max(width_mm * 0.15, 1.0))
    usable_width = max(width_mm - edge_margin * 2, 1.0)
    tab_width = min(config.tab_width_mm, usable_width)
    overlap = min(config.tab_overlap_mm, max(image_height_mm * 0.25, 0.0))
    mount_mode = config.mount_mode
    support_height = max(vertical_support_height_mm, 0.0) if mount_mode == "front-tab" else 0.0
    tab_y = image_height_mm + support_height - overlap
    tab_height = config.tab_height_mm + overlap if mount_mode == "front-tab" else overlap

    if config.base_mode == "square-grid":
        tab_width = config.tab_width_mm
        support_anchor_x = width_mm / 2
        valid = [
            (start, end)
            for start, end in support_intervals
            if end - start >= max(0.5, tab_width * 0.2)
        ]
        if config.support_mode == "rail" and slot_assignment:
            slot_spans = _grid_slot_x_spans(config, config.base_width_mm)
            rail_support_spans = _rail_support_spans(support_intervals, width_mm, config)
            rail_base_left = min(
                max(config.rail_edge_margin_mm, 0.0),
                max(config.base_width_mm / 2 - 0.5, 0.0),
            )
            rail_width = max(config.base_width_mm - rail_base_left * 2, config.tab_width_mm)
            rail_height = max(config.rail_body_height_mm, 0.2)
            rail_y = image_height_mm + support_height - overlap
            tab_y = rail_y + rail_height - overlap
            tab_height = config.tab_height_mm + overlap
            target_base_x = slot_assignment["targetBaseXCenterMm"]
            rail_x = support_anchor_x - target_base_x + rail_base_left
            rail = {
                "railId": "rail-1",
                "xMm": round(rail_x, 3),
                "yMm": round(rail_y, 3),
                "widthMm": round(rail_width, 3),
                "heightMm": round(rail_height, 3),
                "supportAnchorXMm": round(support_anchor_x, 3),
                "targetBaseXCenterMm": round(target_base_x, 3),
                "railBaseXStartMm": round(rail_base_left, 3),
                "railBaseXEndMm": round(rail_base_left + rail_width, 3),
                "railSupportWidthMm": round(
                    max(config.rail_support_width_mm, config.vertical_support_width_mm),
                    3,
                ),
                "railSupportSpansMm": rail_support_spans,
            }
            tabs = []
            for slot_column_index, (slot_start, slot_end) in enumerate(slot_spans):
                tab_x = rail_x + slot_start - rail_base_left
                slot_tab_width = slot_end - slot_start
                tabs.append(
                    {
                        "tabId": f"tab-{slot_column_index + 1}",
                        "xMm": round(tab_x, 3),
                        "yMm": round(tab_y, 3),
                        "widthMm": round(slot_tab_width, 3),
                        "heightMm": round(tab_height, 3),
                        "depthMm": round(config.tab_height_mm, 3),
                        "insertDepthMm": round(config.tab_height_mm, 3),
                        "frontExtensionMm": round(max(tab_y + tab_height - image_height_mm, 0.0), 3),
                        "mountDirection": "front-down",
                        "overlapMm": round(overlap, 3),
                        "verticalSupportHeightMm": round(support_height, 3),
                        "supportAnchorXMm": round(support_anchor_x, 3),
                        "supportOffsetFromTabCenterMm": round(
                            support_anchor_x - (tab_x + slot_tab_width / 2),
                            3,
                        ),
                        "railSlotIndex": slot_column_index,
                        "carriesSupport": slot_column_index == 0,
                        "railId": rail["railId"],
                        "rail": rail if slot_column_index == 0 else None,
                    }
                )
            return tabs
        if config.support_mode == "tree" and slot_assignment:
            base_offset = slot_assignment["targetBaseXCenterMm"] - slot_assignment["slotXCenterMm"]
            edge_margin = min(config.tree_support_edge_margin_mm, max(tab_width / 2 - 0.1, 0.0))
            support_on_tab = _clamp(
                tab_width / 2 + base_offset,
                edge_margin,
                tab_width - edge_margin,
            )
            center = support_anchor_x - (support_on_tab - tab_width / 2)
        elif valid:
            widest = max(valid, key=lambda item: item[1] - item[0])
            center = (widest[0] + widest[1]) / 2
            support_anchor_x = center
        else:
            center = width_mm / 2
            support_anchor_x = center
        starts = [center - tab_width / 2]
        return [
            {
                "tabId": "tab-1",
                "xMm": round(start, 3),
                "yMm": round(tab_y, 3),
                "widthMm": round(tab_width, 3),
                "heightMm": round(tab_height, 3),
                "depthMm": round(config.tab_height_mm, 3),
                "insertDepthMm": round(config.tab_height_mm, 3),
                "frontExtensionMm": round(
                    config.tab_height_mm + support_height if mount_mode == "front-tab" else 0.0,
                    3,
                ),
                "mountDirection": "front-down" if mount_mode == "front-tab" else "rear",
                "overlapMm": round(overlap, 3),
                "verticalSupportHeightMm": round(support_height, 3),
                "supportAnchorXMm": round(support_anchor_x, 3),
                "supportOffsetFromTabCenterMm": round(support_anchor_x - (start + tab_width / 2), 3),
            }
            for start in starts
        ]

    if support_intervals:
        valid = [
            (start, end)
            for start, end in support_intervals
            if end - start >= max(0.5, tab_width * 0.2)
        ]
    else:
        valid = []

    if valid:
        valid.sort(key=lambda item: item[0])
        span = valid[-1][1] - valid[0][0]
        if len(valid) >= 2 and span >= tab_width * 2:
            centers = [
                (valid[0][0] + valid[0][1]) / 2,
                (valid[-1][0] + valid[-1][1]) / 2,
            ]
        else:
            widest = max(valid, key=lambda item: item[1] - item[0])
            centers = [(widest[0] + widest[1]) / 2]
        starts = [
            _clamp(center - tab_width / 2, 0.0, max(width_mm - tab_width, 0.0))
            for center in centers
        ]
    else:
        tab_count = 2 if usable_width >= config.tab_width_mm * 2 + edge_margin else 1
        if tab_count == 1:
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
            "yMm": round(tab_y, 3),
            "widthMm": round(tab_width, 3),
            "heightMm": round(tab_height, 3),
            "depthMm": round(config.tab_height_mm, 3),
            "insertDepthMm": round(config.tab_height_mm, 3),
            "frontExtensionMm": round(
                config.tab_height_mm + support_height if mount_mode == "front-tab" else 0.0,
                3,
            ),
            "mountDirection": "front-down" if mount_mode == "front-tab" else "rear",
            "overlapMm": round(overlap, 3),
            "verticalSupportHeightMm": round(support_height, 3),
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


def _layer_visible_bottom_y_mm(
    layer_mm: dict,
    asset: dict,
    backing_bbox: tuple[int, int, int, int],
    mm_per_px: float,
) -> float:
    return layer_mm["yMm"] + (backing_bbox[3] - asset["heightPx"] / 2) * mm_per_px


def _vertical_support_height_mm(
    *,
    layer_mm: dict,
    asset: dict,
    backing_bbox: tuple[int, int, int, int],
    mm_per_px: float,
    target_height_mm: float,
    config: FlatPhotoPartConfig,
) -> tuple[float, float]:
    bottom_y_mm = _layer_visible_bottom_y_mm(layer_mm, asset, backing_bbox, mm_per_px)
    raw_gap_mm = max(target_height_mm - bottom_y_mm, 0.0)
    if config.mount_mode != "front-tab" or raw_gap_mm < config.vertical_support_min_height_mm:
        return 0.0, bottom_y_mm
    return raw_gap_mm, bottom_y_mm


def _vertical_support_specs(
    tabs: list[dict],
    image_width_mm: float,
    image_height_mm: float,
    support_height_mm: float,
    config: FlatPhotoPartConfig,
) -> list[dict]:
    if config.mount_mode != "front-tab" or support_height_mm <= 0:
        return []

    if config.support_mode == "rail":
        rail_tab = next((tab for tab in tabs if tab.get("rail")), None)
        if rail_tab is None:
            return []

        rail = rail_tab.get("rail") or {}
        overlap = rail_tab.get("overlapMm", 0.0)
        y_mm = image_height_mm - overlap
        height_mm = support_height_mm + overlap
        if height_mm <= 0:
            return []

        supports = []
        for index, span in enumerate(rail.get("railSupportSpansMm") or []):
            x_start_mm = float(span["xStartMm"])
            x_end_mm = float(span["xEndMm"])
            width_mm = max(0.1, x_end_mm - x_start_mm)
            anchor_x = (x_start_mm + x_end_mm) / 2
            supports.append(
                {
                    "supportId": f"{rail.get('railId', 'rail')}-vertical-support-{index + 1}",
                    "tabId": rail_tab["tabId"],
                    "railId": rail.get("railId"),
                    "supportMode": config.support_mode,
                    "xMm": round(x_start_mm, 3),
                    "yMm": round(y_mm, 3),
                    "widthMm": round(width_mm, 3),
                    "heightMm": round(height_mm, 3),
                    "anchorXMm": round(anchor_x, 3),
                    "supportHeightMm": round(support_height_mm, 3),
                    "overlapMm": round(overlap, 3),
                    "rootPad": _support_root_pad_spec(
                        anchor_x=anchor_x,
                        support_width_mm=width_mm,
                        image_width_mm=image_width_mm,
                        image_height_mm=image_height_mm,
                        overlap_mm=overlap,
                        config=config,
                    ),
                    "bodyAnchorSpanMm": {
                        "xStartMm": round(x_start_mm, 3),
                        "xEndMm": round(x_end_mm, 3),
                        "widthMm": round(width_mm, 3),
                    },
                    "imageBottomIntervalMm": span.get("imageBottomIntervalMm"),
                    "branches": [],
                }
            )
        return supports

    supports = []
    for tab in tabs:
        overlap = tab.get("overlapMm", 0.0)
        width_mm = max(0.1, min(config.vertical_support_width_mm, tab["widthMm"]))
        anchor_x = tab.get("supportAnchorXMm", tab["xMm"] + tab["widthMm"] / 2)
        x_mm = anchor_x - width_mm / 2
        y_mm = image_height_mm - overlap
        height_mm = support_height_mm + overlap
        if height_mm <= 0:
            continue
        branches = []
        if config.support_mode == "tree" and support_height_mm >= 4.0:
            branch_width = max(0.8, min(config.tree_branch_width_mm, width_mm * 0.85))
            branch_end_y = y_mm + height_mm
            branch_rise = min(max(support_height_mm * 0.55, 4.0), support_height_mm - 0.3)
            branch_join_y = branch_end_y - branch_rise
            edge_margin = min(
                config.tree_support_edge_margin_mm,
                max(tab["widthMm"] / 2 - 0.1, 0.0),
            )
            base_points = [
                tab["xMm"] + edge_margin,
                tab["xMm"] + tab["widthMm"] - edge_margin,
            ]
            for branch_index, base_x in enumerate(base_points):
                if abs(base_x - anchor_x) < width_mm * 0.4:
                    continue
                polygon = _thick_segment_polygon(
                    base_x,
                    branch_end_y,
                    anchor_x,
                    branch_join_y,
                    branch_width,
                )
                if not polygon:
                    continue
                branches.append(
                    {
                        "branchId": f"{tab['tabId']}-tree-branch-{branch_index + 1}",
                        "widthMm": round(branch_width, 3),
                        "points": [
                            {"xMm": round(point_x, 3), "yMm": round(point_y, 3)}
                            for point_x, point_y in polygon
                        ],
                    }
                )
        supports.append(
            {
                "supportId": f"{tab['tabId']}-vertical-support",
                "tabId": tab["tabId"],
                "supportMode": config.support_mode,
                "xMm": round(x_mm, 3),
                "yMm": round(y_mm, 3),
                "widthMm": round(width_mm, 3),
                "heightMm": round(height_mm, 3),
                "anchorXMm": round(anchor_x, 3),
                "supportHeightMm": round(support_height_mm, 3),
                "overlapMm": round(overlap, 3),
                "rootPad": _support_root_pad_spec(
                    anchor_x=anchor_x,
                    support_width_mm=width_mm,
                    image_width_mm=image_width_mm,
                    image_height_mm=image_height_mm,
                    overlap_mm=overlap,
                    config=config,
                ),
                "branches": branches,
            }
        )
    return supports


def _slot_assignments_for_layers(
    layers: list[dict],
    artwork: dict,
    config: FlatPhotoPartConfig,
) -> dict[str, dict]:
    if config.base_mode != "square-grid":
        return {}

    x_spans = _grid_slot_x_spans(config, config.base_width_mm)
    if not x_spans:
        return {}

    target_height_mm = config.target_width_mm / artwork["canvas"]["aspectRatio"]
    front_to_back_layers = sorted(layers, key=lambda layer: layer["layerIndex"], reverse=True)
    assignments = {}
    for slot_index, layer in enumerate(front_to_back_layers):
        layer_mm = _layer_conversion(layer, config.target_width_mm, target_height_mm)
        desired_x = config.base_width_mm * layer_mm["xMm"] / config.target_width_mm
        desired_x = _clamp(desired_x, 0.0, config.base_width_mm)
        if config.support_mode == "rail":
            slot_numbers = [
                slot_index * len(x_spans) + column_index + 1
                for column_index in range(len(x_spans))
            ]
            assembly_label = (
                f"{slot_numbers[0]}-{slot_numbers[-1]}"
                if len(slot_numbers) > 1
                else str(slot_numbers[0])
            )
            assignments[layer["layerId"]] = {
                "slotIndex": slot_index,
                "columnIndex": None,
                "slotNumbers": slot_numbers,
                "assemblyLabel": assembly_label,
                "selectedBy": "rowRail",
                "targetBaseXCenterMm": round(desired_x, 3),
                "slotXCenterMm": round(desired_x, 3),
                "supportOffsetFromSlotCenterMm": 0.0,
                "railBaseXStartMm": round(max(config.rail_edge_margin_mm, 0.0), 3),
                "railBaseXEndMm": round(config.base_width_mm - max(config.rail_edge_margin_mm, 0.0), 3),
            }
            continue
        column_index, span = min(
            enumerate(x_spans),
            key=lambda item: abs(((item[1][0] + item[1][1]) / 2) - desired_x),
        )
        slot_number = slot_index * len(x_spans) + column_index + 1
        assignments[layer["layerId"]] = {
            "slotIndex": slot_index,
            "columnIndex": column_index,
            "slotNumber": slot_number,
            "assemblyLabel": str(slot_number),
            "selectedBy": "artworkX",
            "targetBaseXCenterMm": round(desired_x, 3),
            "slotXCenterMm": round((span[0] + span[1]) / 2, 3),
        }
    return assignments


def _part_from_layer(
    layer: dict,
    artwork: dict,
    assets_dir: pathlib.Path,
    out_dir: pathlib.Path,
    config: FlatPhotoPartConfig,
    slot_assignment: dict | None = None,
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

    background_fill: dict | None = None
    if _is_cover_background_layer(layer, mask, config):
        background_width_mm = config.print_layout_page_width_mm
        background_height_mm = config.print_layout_page_height_mm
        backing_bbox = _cover_crop_box(
            image.width,
            image.height,
            background_width_mm,
            background_height_mm,
        )
        cropped_image = image.crop(backing_bbox)
        cropped_mask = Image.new("L", cropped_image.size, 255)
        crop_w_px, crop_h_px = cropped_mask.size
        width_mm = background_width_mm
        height_mm = background_height_mm
        mm_per_px = width_mm / crop_w_px
        support_intervals = [(0.0, width_mm)]
        support_height_mm = 0.0
        visible_bottom_y_mm = height_mm
        center_x_mm = width_mm / 2
        center_y_mm = height_mm / 2
        background_fill = _cover_crop_report(
            backing_bbox,
            image.width,
            image.height,
            background_width_mm,
            background_height_mm,
        )
    else:
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
        support_intervals = _bottom_support_intervals(cropped_mask, mm_per_px)
        support_height_mm, visible_bottom_y_mm = _vertical_support_height_mm(
            layer_mm=layer_mm,
            asset=asset,
            backing_bbox=backing_bbox,
            mm_per_px=mm_per_px,
            target_height_mm=target_height_mm,
            config=config,
        )
        crop_center_x_px = (backing_bbox[0] + backing_bbox[2]) / 2
        crop_center_y_px = (backing_bbox[1] + backing_bbox[3]) / 2
        center_x_mm = layer_mm["xMm"] + (crop_center_x_px - asset["widthPx"] / 2) * mm_per_px
        center_y_mm = layer_mm["yMm"] + (crop_center_y_px - asset["heightPx"] / 2) * mm_per_px

    if background_fill:
        triangles = _box_triangles(
            0.0,
            0.0,
            0.0,
            width_mm,
            height_mm,
            config.part_thickness_mm,
        )
        geometry = {
            "strategy": "solid-rect",
            "fallbackUsed": False,
            "originalComponentCount": 1,
            "floatingComponentCount": 0,
            "supportBridgeCount": 0,
            "connectedComponentCount": 1,
        }
    else:
        triangles, geometry = _flat_shape_triangles(
            cropped_mask,
            width_mm,
            height_mm,
            mm_per_px,
            config,
        )
    if not triangles:
        return None, None

    tabs = _tab_specs(width_mm, height_mm, config, support_intervals, support_height_mm, slot_assignment)
    rails = []
    seen_rail_ids = set()
    for tab in tabs:
        rail = tab.get("rail")
        if not rail:
            continue
        rail_id = rail.get("railId")
        if rail_id in seen_rail_ids:
            continue
        seen_rail_ids.add(rail_id)
        rails.append(rail)
    vertical_supports = _vertical_support_specs(tabs, width_mm, height_mm, support_height_mm, config)
    name = f"flat-part-{layer['layerIndex']}-{_slug(layer['layerId'])}"
    stl_path = out_dir / f"{name}.stl"
    assembly_marks = []
    for rail in rails:
        label_rects = []
        label_info = {}
        if slot_assignment and config.mount_mode == "front-tab":
            rail["assemblyLabel"] = slot_assignment["assemblyLabel"]
            label_rects, label_info = _part_slot_label_rects(
                slot_assignment["assemblyLabel"],
                rail,
                config,
            )
        triangles += _bottom_engraved_box_triangles(
            rail["xMm"],
            rail["yMm"],
            0.0,
            rail["xMm"] + rail["widthMm"],
            rail["yMm"] + rail["heightMm"],
            config.part_thickness_mm,
            label_rects,
            config.part_slot_label_engrave_depth_mm,
        )
        if label_info:
            label_info["railId"] = rail["railId"]
            label_info["location"] = "back side of full-row rail"
            assembly_marks.append(label_info)
    for support in vertical_supports:
        root_pad = support.get("rootPad")
        if root_pad:
            triangles += _box_triangles(
                root_pad["xMm"],
                root_pad["yMm"],
                0.0,
                root_pad["xMm"] + root_pad["widthMm"],
                root_pad["yMm"] + root_pad["heightMm"],
                config.part_thickness_mm,
            )
        triangles += _box_triangles(
            support["xMm"],
            support["yMm"],
            0.0,
            support["xMm"] + support["widthMm"],
            support["yMm"] + support["heightMm"],
            config.part_thickness_mm,
        )
        for branch in support.get("branches", []):
            points = [(point["xMm"], point["yMm"]) for point in branch["points"]]
            triangles += _polygon_triangles(points, config.part_thickness_mm)
    for tab in tabs:
        if config.mount_mode == "front-tab":
            label_rects = []
            label_info = {}
            if slot_assignment and config.support_mode != "rail":
                tab["assemblyLabel"] = slot_assignment["assemblyLabel"]
                label_rects, label_info = _part_slot_label_rects(
                    slot_assignment["assemblyLabel"],
                    tab,
                    config,
                )
            triangles += _bottom_engraved_box_triangles(
                tab["xMm"],
                tab["yMm"],
                0.0,
                tab["xMm"] + tab["widthMm"],
                tab["yMm"] + tab["heightMm"],
                config.part_thickness_mm,
                label_rects,
                config.part_slot_label_engrave_depth_mm,
            )
            if label_info:
                label_info["tabId"] = tab["tabId"]
                assembly_marks.append(label_info)
        else:
            triangles += _box_triangles(
                tab["xMm"],
                tab["yMm"],
                config.part_thickness_mm,
                tab["xMm"] + tab["widthMm"],
                min(tab["yMm"] + tab["heightMm"], height_mm),
                config.part_thickness_mm + tab["depthMm"],
            )
    branch_x_values = [
        point["xMm"]
        for support in vertical_supports
        for branch in support.get("branches", [])
        for point in branch["points"]
    ]
    root_pads = [
        support["rootPad"]
        for support in vertical_supports
        if support.get("rootPad")
    ]
    min_part_x = min(
        [0.0]
        + [rail["xMm"] for rail in rails]
        + [tab["xMm"] for tab in tabs]
        + [support["xMm"] for support in vertical_supports]
        + [pad["xMm"] for pad in root_pads]
        + branch_x_values
    )
    max_part_x = max(
        [width_mm]
        + [rail["xMm"] + rail["widthMm"] for rail in rails]
        + [tab["xMm"] + tab["widthMm"] for tab in tabs]
        + [support["xMm"] + support["widthMm"] for support in vertical_supports]
        + [pad["xMm"] + pad["widthMm"] for pad in root_pads]
        + branch_x_values
    )
    shift_x = -min_part_x if min_part_x < 0 else 0.0
    if shift_x:
        triangles = _translate_triangles(triangles, shift_x, 0.0, 0.0)
        for rail in rails:
            rail["xMm"] = round(rail["xMm"] + shift_x, 3)
            rail["supportAnchorXMm"] = round(rail["supportAnchorXMm"] + shift_x, 3)
            for span in rail.get("railSupportSpansMm", []):
                span["xStartMm"] = round(span["xStartMm"] + shift_x, 3)
                span["xEndMm"] = round(span["xEndMm"] + shift_x, 3)
                span["anchorXMm"] = round(span["anchorXMm"] + shift_x, 3)
        for tab in tabs:
            tab["xMm"] = round(tab["xMm"] + shift_x, 3)
            if "supportAnchorXMm" in tab:
                tab["supportAnchorXMm"] = round(tab["supportAnchorXMm"] + shift_x, 3)
        for support in vertical_supports:
            support["xMm"] = round(support["xMm"] + shift_x, 3)
            support["anchorXMm"] = round(support["anchorXMm"] + shift_x, 3)
            body_anchor = support.get("bodyAnchorSpanMm")
            if body_anchor:
                body_anchor["xStartMm"] = round(body_anchor["xStartMm"] + shift_x, 3)
                body_anchor["xEndMm"] = round(body_anchor["xEndMm"] + shift_x, 3)
            root_pad = support.get("rootPad")
            if root_pad:
                root_pad["xMm"] = round(root_pad["xMm"] + shift_x, 3)
            for branch in support.get("branches", []):
                for point in branch["points"]:
                    point["xMm"] = round(point["xMm"] + shift_x, 3)
        for mark in assembly_marks:
            mark["xCenterMm"] = round(mark["xCenterMm"] + shift_x, 3)
    part_width_mm = max_part_x - min_part_x
    image_x_mm = shift_x
    triangle_count = _write_stl(stl_path, name, triangles)
    geometry_bottoms = (
        [height_mm]
        + [rail["yMm"] + rail["heightMm"] for rail in rails]
        + [tab["yMm"] + tab["heightMm"] for tab in tabs]
        + [support["yMm"] + support["heightMm"] for support in vertical_supports]
        + [pad["yMm"] + pad["heightMm"] for pad in root_pads]
        + [
            point["yMm"]
            for support in vertical_supports
            for branch in support.get("branches", [])
            for point in branch["points"]
        ]
    )
    part_height_mm = max(geometry_bottoms)
    part_depth_mm = config.part_thickness_mm + (config.tab_height_mm if config.mount_mode == "rear" else 0.0)

    part = {
        "layerId": layer["layerId"],
        "label": layer["label"],
        "sourcePhotoId": layer["sourcePhotoId"],
        "sourceLayerId": layer["sourceLayerId"],
        "assetId": asset["assetId"],
        "assetPath": _display_path(path),
        "layerIndex": layer["layerIndex"],
        "outputStl": _display_path(stl_path),
        "triangles": triangle_count,
        "flatSurface": True,
        "usesRelief": False,
        "usesHeightmap": False,
        "mountMode": config.mount_mode,
        "dimensionsMm": {
            "widthMm": round(part_width_mm, 3),
            "heightMm": round(part_height_mm, 3),
            "thicknessMm": round(part_depth_mm, 3),
            "frontHeightMm": round(height_mm, 3),
            "verticalSupportHeightMm": round(support_height_mm, 3),
            "bodyThicknessMm": round(config.part_thickness_mm, 3),
        },
        "imageAreaMm": {
            "xMm": round(image_x_mm, 3),
            "yMm": 0.0,
            "widthMm": round(width_mm, 3),
            "heightMm": round(height_mm, 3),
        },
        "rails": rails,
        "tabs": tabs,
        "verticalSupports": vertical_supports,
        "slotAssignment": slot_assignment,
        "assemblyMarks": assembly_marks,
        "bottomSupportIntervalsMm": [
            {"xStartMm": round(start, 3), "xEndMm": round(end, 3)}
            for start, end in support_intervals
        ],
        "geometry": geometry,
        "artworkPlacementMm": {
            "centerXMm": round(center_x_mm, 3),
            "centerYMm": round(center_y_mm, 3),
            "visibleBottomYMm": round(visible_bottom_y_mm, 3),
            "bottomGapToCanvasMm": round(max(target_height_mm - visible_bottom_y_mm, 0.0), 3),
            "layerWidthMm": layer_mm["layerWidthMm"],
            "layerHeightMm": layer_mm["layerHeightMm"],
            "canvasHeightMm": round(target_height_mm, 3),
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
    }
    if background_fill:
        part["backgroundFill"] = background_fill
    if geometry["strategy"] == "grid":
        part["grid"] = {
            "columns": geometry["columns"],
            "rows": geometry["rows"],
            "occupiedCells": geometry["occupiedCells"],
            "totalCells": geometry["totalCells"],
        }
    if geometry["strategy"] == "contour":
        part["contour"] = {
            "contourCount": geometry["contourCount"],
            "contours": geometry["contours"],
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


def _grid_slot_x_spans(config: FlatPhotoPartConfig, base_width: float) -> list[tuple[float, float]]:
    slot_count = max(1, config.base_slots_per_layer)
    if config.support_mode == "tree" and slot_count > 1:
        band_width = base_width / slot_count
        slot_length = min(config.base_slot_length_mm, max(band_width - config.slot_side_clearance_mm * 2, 1.0))
        return [
            (
                index * band_width + (band_width - slot_length) / 2,
                index * band_width + (band_width + slot_length) / 2,
            )
            for index in range(slot_count)
        ]

    slot_length = min(config.base_slot_length_mm, base_width / (slot_count * 1.5))
    usable = base_width - config.base_margin_x_mm * 2 - slot_length * slot_count
    if slot_count == 1:
        starts = [(base_width - slot_length) / 2]
    else:
        gap = max(usable / (slot_count - 1), 2.0)
        total_width = slot_length * slot_count + gap * (slot_count - 1)
        start_x = (base_width - total_width) / 2
        starts = [start_x + index * (slot_length + gap) for index in range(slot_count)]
    return [(start, start + slot_length) for start in starts]


_DIGIT_SEGMENTS: dict[str, tuple[str, ...]] = {
    "0": ("a", "b", "c", "d", "e", "f"),
    "1": ("b", "c"),
    "2": ("a", "b", "g", "e", "d"),
    "3": ("a", "b", "g", "c", "d"),
    "4": ("f", "g", "b", "c"),
    "5": ("a", "f", "g", "c", "d"),
    "6": ("a", "f", "g", "e", "c", "d"),
    "7": ("a", "b", "c"),
    "8": ("a", "b", "c", "d", "e", "f", "g"),
    "9": ("a", "b", "c", "d", "f", "g"),
}


def _seven_segment_rects(
    x: float,
    y: float,
    width: float,
    height: float,
    stroke: float,
    segments: tuple[str, ...],
) -> list[tuple[float, float, float, float]]:
    mid_low = y + height / 2 - stroke / 2
    mid_high = y + height / 2 + stroke / 2
    rects = {
        "a": (x + stroke, y + height - stroke, x + width - stroke, y + height),
        "b": (x + width - stroke, mid_high, x + width, y + height - stroke),
        "c": (x + width - stroke, y + stroke, x + width, mid_low),
        "d": (x + stroke, y, x + width - stroke, y + stroke),
        "e": (x, y + stroke, x + stroke, mid_low),
        "f": (x, mid_high, x + stroke, y + height - stroke),
        "g": (x + stroke, mid_low, x + width - stroke, mid_high),
    }
    return [rects[segment] for segment in segments]


def _base_slot_label_rects(
    label: str,
    center_x: float,
    slot_front: float,
    config: FlatPhotoPartConfig,
) -> tuple[list[tuple[float, float, float, float]], dict]:
    digit_height = config.base_slot_label_digit_height_mm
    if config.base_slot_label_engrave_depth_mm <= 0 or digit_height <= 0:
        return [], {}

    digit_width = digit_height * 0.58
    stroke = max(digit_height * 0.14, 0.45)
    gap = config.base_slot_label_gap_mm
    total_width = len(label) * digit_width + max(len(label) - 1, 0) * gap
    origin_x = center_x - total_width / 2
    top_y = slot_front - config.base_slot_label_offset_y_mm
    origin_y = max(0.8, top_y - digit_height)

    rects = []
    cursor_x = origin_x
    for char in label:
        segments = _DIGIT_SEGMENTS.get(char)
        if segments:
            rects.extend(_seven_segment_rects(
                cursor_x,
                origin_y,
                digit_width,
                digit_height,
                stroke,
                segments,
            ))
        cursor_x += digit_width + gap

    return rects, {
        "label": label,
        "xCenterMm": round(center_x, 3),
        "yCenterMm": round(origin_y + digit_height / 2, 3),
        "widthMm": round(total_width, 3),
        "heightMm": round(digit_height, 3),
        "engraveDepthMm": round(config.base_slot_label_engrave_depth_mm, 3),
    }


def _part_slot_label_rects(
    label: str,
    tab: dict,
    config: FlatPhotoPartConfig,
) -> tuple[list[tuple[float, float, float, float]], dict]:
    digit_height = config.part_slot_label_digit_height_mm
    engrave_depth = config.part_slot_label_engrave_depth_mm
    if engrave_depth <= 0 or digit_height <= 0 or not label:
        return [], {}

    margin = 0.65
    max_width = max(tab["widthMm"] - margin * 2, 0.0)
    max_height = max(tab["heightMm"] - margin * 2, 0.0)
    if max_width <= 0 or max_height <= 0:
        return [], {}

    digit_width = digit_height * 0.58
    stroke = max(digit_height * 0.14, 0.32)
    gap = config.part_slot_label_gap_mm
    total_width = len(label) * digit_width + max(len(label) - 1, 0) * gap
    if total_width > max_width:
        scale = max_width / total_width
        digit_height *= scale
        digit_width *= scale
        stroke = max(stroke * scale, 0.28)
        gap *= scale
        total_width = max_width
    if digit_height > max_height:
        scale = max_height / digit_height
        digit_height *= scale
        digit_width *= scale
        stroke = max(stroke * scale, 0.28)
        gap *= scale
        total_width = len(label) * digit_width + max(len(label) - 1, 0) * gap

    center_x = tab["xMm"] + tab["widthMm"] / 2
    origin_x = center_x - total_width / 2
    origin_y = tab["yMm"] + config.part_slot_label_offset_y_mm
    max_origin_y = tab["yMm"] + tab["heightMm"] - margin - digit_height
    origin_y = _clamp(origin_y, tab["yMm"] + margin, max_origin_y)

    rects = []
    cursor_x = origin_x
    for char in label:
        segments = _DIGIT_SEGMENTS.get(char)
        if segments:
            rects.extend(
                _seven_segment_rects(
                    cursor_x,
                    origin_y,
                    digit_width,
                    digit_height,
                    stroke,
                    segments,
                )
            )
        cursor_x += digit_width + gap

    if config.part_slot_label_mirror_for_back_side:
        rects = [
            (2 * center_x - x1, y0, 2 * center_x - x0, y1)
            for x0, y0, x1, y1 in rects
        ]

    return rects, {
        "label": label,
        "location": "back side of tab root",
        "xCenterMm": round(center_x, 3),
        "yCenterMm": round(origin_y + digit_height / 2, 3),
        "widthMm": round(total_width, 3),
        "heightMm": round(digit_height, 3),
        "engraveDepthMm": round(engrave_depth, 3),
        "mirroredForBackSide": config.part_slot_label_mirror_for_back_side,
    }


def _height_field_triangles(
    x_edges: list[float],
    y_edges: list[float],
    heights: list[list[float]],
) -> list[
    tuple[
        tuple[float, float, float],
        tuple[float, float, float],
        tuple[float, float, float],
    ]
]:
    rows = len(y_edges) - 1
    columns = len(x_edges) - 1
    triangles = []

    def height_at(row: int, column: int) -> float:
        if row < 0 or row >= rows or column < 0 or column >= columns:
            return 0.0
        return heights[row][column]

    for row in range(rows):
        y0 = y_edges[row]
        y1 = y_edges[row + 1]
        for column in range(columns):
            top = heights[row][column]
            if top <= 0:
                continue

            x0 = x_edges[column]
            x1 = x_edges[column + 1]
            triangles += _quad((x0, y0, top), (x1, y0, top), (x1, y1, top), (x0, y1, top))
            triangles += _quad((x0, y1, 0.0), (x1, y1, 0.0), (x1, y0, 0.0), (x0, y0, 0.0))

            left = height_at(row, column - 1)
            right = height_at(row, column + 1)
            front = height_at(row - 1, column)
            back = height_at(row + 1, column)
            if left < top:
                triangles += _quad((x0, y1, left), (x0, y0, left), (x0, y0, top), (x0, y1, top))
            if right < top:
                triangles += _quad((x1, y0, right), (x1, y1, right), (x1, y1, top), (x1, y0, top))
            if front < top:
                triangles += _quad((x0, y0, front), (x1, y0, front), (x1, y0, top), (x0, y0, top))
            if back < top:
                triangles += _quad((x1, y1, back), (x0, y1, back), (x0, y1, top), (x1, y1, top))

    return triangles


def _rect_contains(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
    x0, y0, x1, y1 = rect
    return x0 <= x <= x1 and y0 <= y <= y1


def _clipped_rect(
    rect: tuple[float, float, float, float],
    max_x: float,
    max_y: float,
    min_x: float = 0.0,
    min_y: float = 0.0,
) -> tuple[float, float, float, float] | None:
    x0, y0, x1, y1 = rect
    clipped = (max(min_x, x0), max(min_y, y0), min(max_x, x1), min(max_y, y1))
    if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
        return None
    return clipped


def _square_grid_base_triangles_for_parts(parts: list[dict], config: FlatPhotoPartConfig) -> tuple[list, dict]:
    front_to_back_parts = sorted(parts, key=lambda part: part["layerIndex"], reverse=True)
    layer_capacity = max(config.base_layer_capacity, len(front_to_back_parts), 1)
    slot_width = config.part_thickness_mm + config.slot_clearance_mm
    base_width = config.base_width_mm
    base_depth = config.base_depth_mm
    usable_depth = base_depth - config.base_margin_y_mm - config.base_back_margin_y_mm - slot_width * layer_capacity
    layer_gap = max(usable_depth / max(layer_capacity - 1, 1), 2.0) if layer_capacity > 1 else 0.0
    if usable_depth < 0:
        base_depth = config.base_margin_y_mm + config.base_back_margin_y_mm + slot_width * layer_capacity
        layer_gap = 0.0

    slot_labels = []
    slots = []
    slot_openings: list[tuple[float, float, float, float]] = []
    label_rectangles: list[tuple[float, float, float, float]] = []
    x_spans = _grid_slot_x_spans(config, base_width)

    for slot_index in range(layer_capacity):
        part = front_to_back_parts[slot_index] if slot_index < len(front_to_back_parts) else None
        slot_front = config.base_margin_y_mm + slot_index * (slot_width + layer_gap)
        slot_back = slot_front + slot_width

        tab_slots = []
        openings = [
            (
                x_start - config.slot_side_clearance_mm / 2,
                x_end + config.slot_side_clearance_mm / 2,
            )
            for x_start, x_end in x_spans
        ]
        for column_index, (opening, span) in enumerate(zip(openings, x_spans)):
            x_start, x_end = opening
            slot_openings.append((x_start, slot_front, x_end, slot_back))
            slot_number = slot_index * len(x_spans) + column_index + 1
            assembly_label = str(slot_number)
            label_rects, label_info = _base_slot_label_rects(
                assembly_label,
                (span[0] + span[1]) / 2,
                slot_front,
                config,
            )
            label_rectangles += label_rects
            if label_info:
                label_info.update({
                    "slotNumber": slot_number,
                    "slotIndex": slot_index,
                    "columnIndex": column_index,
                })
                slot_labels.append(label_info)
            tab_slot = {
                "slotId": f"slot-{slot_index + 1}-{column_index + 1}",
                "assemblyLabel": assembly_label,
                "slotNumber": slot_number,
                "columnIndex": column_index,
                "xStartMm": round(x_start, 3),
                "xEndMm": round(x_end, 3),
                "frontMm": round(slot_front, 3),
                "backMm": round(slot_back, 3),
                "nominalSlotLengthMm": round(span[1] - span[0], 3),
            }
            tab_slots.append(tab_slot)

        slot = {
            "slotIndex": slot_index,
            "layerId": part["layerId"] if part else None,
            "layerIndex": part["layerIndex"] if part else None,
            "frontMm": round(slot_front, 3),
            "backMm": round(slot_back, 3),
            "slotWidthMm": round(slot_width, 3),
            "tabSlots": tab_slots,
        }
        if part:
            assignment = part.get("slotAssignment") or {}
            selected_tab_slot = None
            selected_tab_slots = []
            row_rail = assignment.get("selectedBy") == "rowRail"
            if row_rail and assignment.get("slotIndex") == slot_index:
                selected_tab_slots = tab_slots
                selected_tab_slot = tab_slots[0]
            elif assignment.get("slotIndex") == slot_index:
                column_index = assignment.get("columnIndex")
                if isinstance(column_index, int) and 0 <= column_index < len(tab_slots):
                    selected_tab_slot = tab_slots[column_index]
            if selected_tab_slot is None:
                selected_tab_slot = tab_slots[len(tab_slots) // 2]
            if not selected_tab_slots:
                selected_tab_slots = [selected_tab_slot]
            part["slotAssignment"] = {
                **assignment,
                "slotId": selected_tab_slot["slotId"],
                "assemblyLabel": selected_tab_slot["assemblyLabel"],
                "slotNumber": selected_tab_slot["slotNumber"],
                "columnIndex": selected_tab_slot["columnIndex"],
                "slotIds": [tab_slot["slotId"] for tab_slot in selected_tab_slots],
                "slotNumbers": [tab_slot["slotNumber"] for tab_slot in selected_tab_slots],
                "slotLabels": [tab_slot["assemblyLabel"] for tab_slot in selected_tab_slots],
                "xStartMm": selected_tab_slot["xStartMm"],
                "xEndMm": selected_tab_slot["xEndMm"],
                "frontMm": selected_tab_slot["frontMm"],
                "backMm": selected_tab_slot["backMm"],
            }
            if row_rail:
                first_label = selected_tab_slots[0]["assemblyLabel"]
                last_label = selected_tab_slots[-1]["assemblyLabel"]
                rail_label = first_label if first_label == last_label else f"{first_label}-{last_label}"
                part["slotAssignment"]["assemblyLabel"] = rail_label
                part["slotAssignment"]["slotId"] = ",".join(
                    tab_slot["slotId"] for tab_slot in selected_tab_slots
                )
            part["baseSlot"] = {
                "slotIndex": slot_index,
                "frontMm": round(slot_front, 3),
                "backMm": round(slot_back, 3),
                "slotWidthMm": round(slot_width, 3),
                "availableSlotCount": len(tab_slots),
                "compatibleSlotIds": [tab_slot["slotId"] for tab_slot in tab_slots],
                "compatibleSlotLabels": [tab_slot["assemblyLabel"] for tab_slot in tab_slots],
                "selectedSlotId": selected_tab_slot["slotId"],
                "selectedSlotIds": [tab_slot["slotId"] for tab_slot in selected_tab_slots],
                "selectedSlotLabel": selected_tab_slot["assemblyLabel"],
                "selectedSlotLabels": [tab_slot["assemblyLabel"] for tab_slot in selected_tab_slots],
                "selectedSlotNumber": selected_tab_slot["slotNumber"],
                "selectedSlotNumbers": [tab_slot["slotNumber"] for tab_slot in selected_tab_slots],
            }
            for tab in part["tabs"]:
                tab_slot_index = tab.get("railSlotIndex")
                tab_selected_slot = selected_tab_slot
                if row_rail and isinstance(tab_slot_index, int) and 0 <= tab_slot_index < len(tab_slots):
                    tab_selected_slot = tab_slots[tab_slot_index]
                tab["baseSlotOptions"] = tab_slots
                tab["selectedBaseSlot"] = tab_selected_slot
                tab["assemblyLabel"] = tab_selected_slot["assemblyLabel"]
            for rail in part.get("rails", []):
                rail["baseSlotOptions"] = tab_slots
                rail["selectedBaseSlots"] = selected_tab_slots
                rail["assemblyLabel"] = part["slotAssignment"]["assemblyLabel"]
        slots.append(slot)

    clipped_slots = [
        clipped
        for rect in slot_openings
        if (clipped := _clipped_rect(rect, base_width, base_depth)) is not None
    ]
    clipped_labels = [
        clipped
        for rect in label_rectangles
        if (clipped := _clipped_rect(rect, base_width, base_depth)) is not None
    ]

    x_edges = {0.0, round(base_width, 6)}
    y_edges = {0.0, round(base_depth, 6)}
    for x0, y0, x1, y1 in clipped_slots + clipped_labels:
        x_edges.update((round(x0, 6), round(x1, 6)))
        y_edges.update((round(y0, 6), round(y1, 6)))

    sorted_x_edges = sorted(x_edges)
    sorted_y_edges = sorted(y_edges)
    engraved_height = max(config.base_height_mm - config.base_slot_label_engrave_depth_mm, 0.2)
    height_rows = []
    for row in range(len(sorted_y_edges) - 1):
        y0 = sorted_y_edges[row]
        y1 = sorted_y_edges[row + 1]
        center_y = (y0 + y1) / 2
        height_row = []
        for column in range(len(sorted_x_edges) - 1):
            x0 = sorted_x_edges[column]
            x1 = sorted_x_edges[column + 1]
            center_x = (x0 + x1) / 2
            if any(_rect_contains(rect, center_x, center_y) for rect in clipped_slots):
                height_row.append(0.0)
            elif any(_rect_contains(rect, center_x, center_y) for rect in clipped_labels):
                height_row.append(engraved_height)
            else:
                height_row.append(config.base_height_mm)
        height_rows.append(height_row)

    tris = _height_field_triangles(sorted_x_edges, sorted_y_edges, height_rows)

    base = {
        "baseMode": config.base_mode,
        "mountMode": config.mount_mode,
        "assemblyDirection": "square base with four front-to-back layer rows",
        "slotNumbering": "front-left-to-right sequential numbers",
        "frontEdgeMm": 0.0,
        "backEdgeMm": round(base_depth, 3),
        "frontMarginMm": round(config.base_margin_y_mm, 3),
        "backMarginMm": round(config.base_back_margin_y_mm, 3),
        "layerCapacity": layer_capacity,
        "slotsPerLayer": len(x_spans),
        "frontToBackLayerOrder": [part["layerId"] for part in front_to_back_parts],
        "emptyLayerSlots": max(layer_capacity - len(front_to_back_parts), 0),
        "dimensionsMm": {
            "widthMm": round(base_width, 3),
            "depthMm": round(base_depth, 3),
            "heightMm": round(config.base_height_mm, 3),
            "plateHeightMm": round(config.base_height_mm, 3),
            "slotLabelEngraveDepthMm": round(max(config.base_slot_label_engrave_depth_mm, 0.0), 3),
        },
        "slotLabels": slot_labels,
        "slots": slots,
    }
    return tris, base


def _base_triangles_for_parts(parts: list[dict], config: FlatPhotoPartConfig) -> tuple[list, dict]:
    if config.base_mode == "square-grid":
        return _square_grid_base_triangles_for_parts(parts, config)

    front_to_back_parts = sorted(parts, key=lambda part: part["layerIndex"], reverse=True)
    slot_width = config.part_thickness_mm + config.slot_clearance_mm
    pitch = slot_width + config.base_layer_gap_mm
    base_width = config.target_width_mm + config.base_margin_x_mm * 2
    base_depth = (
        config.base_margin_y_mm
        + config.base_back_margin_y_mm
        + slot_width * len(parts)
        + config.base_layer_gap_mm * max(len(parts) - 1, 0)
    )
    tris = []
    slots = []

    y_spans: list[tuple[float, float, list[tuple[float, float]]]] = []
    cursor = 0.0
    for slot_index, part in enumerate(front_to_back_parts):
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
        "mountMode": config.mount_mode,
        "assemblyDirection": "base extends behind the front view" if config.mount_mode == "rear" else "front tabs insert into base slots",
        "frontEdgeMm": 0.0,
        "backEdgeMm": round(base_depth, 3),
        "frontMarginMm": round(config.base_margin_y_mm, 3),
        "backMarginMm": round(config.base_back_margin_y_mm, 3),
        "frontToBackLayerOrder": [part["layerId"] for part in front_to_back_parts],
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


def _text_width_units(value: str) -> float:
    return sum(1.0 if ord(char) > 127 else 0.55 for char in value)


def _fit_svg_text(value: str, max_width_mm: float, font_size_mm: float) -> str:
    max_units = max(max_width_mm / max(font_size_mm, 0.1), 4.0)
    if _text_width_units(value) <= max_units:
        return value

    suffix = "..."
    budget = max(max_units - _text_width_units(suffix), 1.0)
    used = 0.0
    chars = []
    for char in value:
        width = 1.0 if ord(char) > 127 else 0.55
        if used + width > budget:
            break
        chars.append(char)
        used += width
    return "".join(chars).rstrip() + suffix


def _layout_label(part: dict, max_width_mm: float, font_size_mm: float) -> str:
    return _fit_svg_text(f"L{part['layerIndex']} {part['label']}", max_width_mm, font_size_mm)


def _print_layout_placements(
    parts: list[dict],
    config: FlatPhotoPartConfig,
    *,
    min_page_height_mm: float = 80.0,
) -> tuple[float, float, list[tuple[float, float]]]:
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

    return page_width, max(min_page_height_mm, y + row_height + margin), placements


def _write_print_layout(
    path: pathlib.Path,
    parts: list[dict],
    cropped_images: list[Image.Image],
    config: FlatPhotoPartConfig,
) -> None:
    page_width, page_height, placements = _print_layout_placements(parts, config)
    label_gap = 3.0
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_width:.3f}mm" '
            f'height="{page_height:.3f}mm" viewBox="0 0 {page_width:.3f} {page_height:.3f}">'
        ),
        '<rect x="0" y="0" width="100%" height="100%" fill="white"/>',
        (
            '<text x="10" y="6" font-family="Arial, sans-serif" font-size="3" '
            'fill="#111">写真紙100%印刷 / 赤い破線で切る / タブは残す</text>'
        ),
    ]

    for (x, y), part, image in zip(placements, parts, cropped_images):
        width = part["dimensionsMm"]["widthMm"]
        height = part["dimensionsMm"]["heightMm"]
        image_height = part["imageAreaMm"]["heightMm"]
        label = html.escape(_layout_label(part, width, 3.5))
        full_label = html.escape(f"{part['layerId']} / {part['label']}")
        mount_mode = part.get("mountMode", config.mount_mode)
        image_x = x + part["imageAreaMm"].get("xMm", 0.0)
        image_width = part["imageAreaMm"]["widthMm"]
        layout_title = "背面支え込み" if mount_mode == "rear" else "切り取り範囲"
        lines.extend(
            [
                "<g>",
                f"<title>{full_label}</title>",
                (
                    f'<rect x="{x:.3f}" y="{y:.3f}" width="{width:.3f}" '
                    f'height="{height:.3f}" fill="#f8f8f8" stroke="#e11d48" '
                    'stroke-width="0.35" stroke-dasharray="1.5 1"/>'
                ),
                (
                    f'<image x="{image_x:.3f}" y="{y:.3f}" width="{image_width:.3f}" '
                    f'height="{image_height:.3f}" href="{_image_data_uri(image)}" '
                    'preserveAspectRatio="none"/>'
                ),
                (
                    f'<rect x="{image_x:.3f}" y="{y:.3f}" width="{image_width:.3f}" '
                    f'height="{image_height:.3f}" fill="none" stroke="#111" '
                    'stroke-width="0.25"/>'
                ),
                (
                    f'<line x1="{image_x:.3f}" y1="{(y + image_height):.3f}" '
                    f'x2="{(image_x + image_width):.3f}" y2="{(y + image_height):.3f}" '
                    'stroke="#e11d48" stroke-width="0.25" stroke-dasharray="1 1"/>'
                ),
                (
                    f'<text x="{x:.3f}" y="{(y + height + label_gap + 3.5):.3f}" '
                    'font-family="Arial, sans-serif" font-size="3.5" '
                    f'fill="#111">{label}</text>'
                ),
            ]
        )
        for support in part.get("verticalSupports", []):
            root_pad = support.get("rootPad")
            if root_pad:
                pad_x = x + root_pad["xMm"]
                pad_y = y + root_pad["yMm"]
                lines.append(
                    (
                        f'<rect x="{pad_x:.3f}" y="{pad_y:.3f}" '
                        f'width="{root_pad["widthMm"]:.3f}" height="{root_pad["heightMm"]:.3f}" '
                        'fill="none" stroke="#ea580c" stroke-width="0.45" '
                        'stroke-dasharray="1 0.8"/>'
                    )
                )
            for branch in support.get("branches", []):
                points = " ".join(
                    f'{(x + point["xMm"]):.3f},{(y + point["yMm"]):.3f}'
                    for point in branch["points"]
                )
                lines.append(
                    f'<polygon points="{points}" fill="none" stroke="#fb923c" '
                    'stroke-width="0.35" stroke-dasharray="1 0.8"/>'
                )
            support_x = x + support["xMm"]
            support_y = y + support["yMm"]
            lines.extend(
                [
                    (
                        f'<rect x="{support_x:.3f}" y="{support_y:.3f}" '
                        f'width="{support["widthMm"]:.3f}" height="{support["heightMm"]:.3f}" '
                        'fill="none" stroke="#fb923c" stroke-width="0.35" '
                        'stroke-dasharray="1 0.8"/>'
                    ),
                ]
            )
        for rail in part.get("rails", []):
            rail_x = x + rail["xMm"]
            rail_y = y + rail["yMm"]
            rail_label = html.escape(rail.get("assemblyLabel", "rail"))
            lines.extend(
                [
                    (
                        f'<rect x="{rail_x:.3f}" y="{rail_y:.3f}" '
                        f'width="{rail["widthMm"]:.3f}" height="{rail["heightMm"]:.3f}" '
                        'fill="none" stroke="#f97316" stroke-width="0.45" '
                        'stroke-dasharray="1 0.8"/>'
                    ),
                    (
                        f'<text x="{(rail_x + rail["widthMm"] / 2):.3f}" '
                        f'y="{(rail_y + rail["heightMm"] / 2 + 1.1):.3f}" '
                        'font-family="Arial, sans-serif" font-size="2.5" '
                        f'text-anchor="middle" fill="#c2410c">{rail_label}</text>'
                    ),
                ]
            )
        for tab in part["tabs"]:
            tab_x = x + tab["xMm"]
            tab_y = y + tab["yMm"]
            tab_is_rear = tab.get("mountDirection") == "rear"
            tab_label = html.escape(tab["tabId"].replace("tab", "rear") if tab_is_rear else tab["tabId"])
            tab_fill = "#e0f2fe" if tab_is_rear else "#fce7f3"
            tab_stroke = "#0284c7" if tab_is_rear else "#e11d48"
            tab_text = "#075985" if tab_is_rear else "#9f1239"
            tab_dash = ' stroke-dasharray="0.8 0.8"' if tab_is_rear else ""
            lines.extend(
                [
                    (
                        f'<rect x="{tab_x:.3f}" y="{tab_y:.3f}" width="{tab["widthMm"]:.3f}" '
                        f'height="{tab["heightMm"]:.3f}" fill="{tab_fill}" stroke="{tab_stroke}" '
                        f'stroke-width="0.35"{tab_dash}/>'
                    ),
                    (
                        f'<text x="{(tab_x + tab["widthMm"] / 2):.3f}" '
                        f'y="{(tab_y + tab["heightMm"] / 2 + 1.1):.3f}" '
                        'font-family="Arial, sans-serif" font-size="2.5" '
                        f'text-anchor="middle" fill="{tab_text}">{tab_label}</text>'
                    ),
                ]
            )
        lines.extend(
            [
                (
                    f'<text x="{x:.3f}" y="{(y - 2.0):.3f}" '
                    'font-family="Arial, sans-serif" font-size="3" '
                    f'fill="#111">{layout_title}</text>'
                ),
                "</g>",
            ]
        )

    lines.append("</svg>")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _draw_dashed_rect(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int, int, int],
    *,
    fill: str,
    width: int,
    dash: int,
    gap: int,
) -> None:
    x0, y0, x1, y1 = xy
    cursor = x0
    while cursor < x1:
        draw.line((cursor, y0, min(cursor + dash, x1), y0), fill=fill, width=width)
        draw.line((cursor, y1, min(cursor + dash, x1), y1), fill=fill, width=width)
        cursor += dash + gap
    cursor = y0
    while cursor < y1:
        draw.line((x0, cursor, x0, min(cursor + dash, y1)), fill=fill, width=width)
        draw.line((x1, cursor, x1, min(cursor + dash, y1)), fill=fill, width=width)
        cursor += dash + gap


def _draw_text_safe(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    fill: str = "#111111",
) -> None:
    # Pillowの既定Fontは日本語glyphを持たない環境があるため、PDF側はASCIIへ寄せる。
    ascii_text = text.encode("ascii", "ignore").decode("ascii") or "layer"
    draw.text(xy, ascii_text, fill=fill, font=ImageFont.load_default())


def _photo_pdf_layout_placements(
    parts: list[dict],
    config: FlatPhotoPartConfig,
) -> PhotoPdfLayout:
    page_width = config.print_layout_page_width_mm
    page_height = config.print_layout_page_height_mm
    placements: list[PhotoPdfPlacement] = []

    for page_index, part in enumerate(parts):
        image_area = part["imageAreaMm"]
        width = float(image_area["widthMm"])
        height = float(image_area["heightMm"])
        x = max(0.0, (page_width - width) / 2.0)
        y = max(0.0, (page_height - height) / 2.0)
        placements.append(
            PhotoPdfPlacement(
                page_index=page_index,
                x_mm=x,
                y_mm=y,
                width_mm=width,
                height_mm=height,
                overflows_page=width > page_width or height > page_height,
            )
        )

    return PhotoPdfLayout(
        page_width_mm=page_width,
        page_height_mm=page_height,
        placements=placements,
    )


def _photo_pdf_layout_report(layout: PhotoPdfLayout, config: FlatPhotoPartConfig) -> dict:
    paper = "2L landscape"
    if not (
        math.isclose(layout.page_width_mm, PHOTO_2L_LANDSCAPE_WIDTH_MM)
        and math.isclose(layout.page_height_mm, PHOTO_2L_LANDSCAPE_HEIGHT_MM)
    ):
        paper = "custom"
    page_width_px, page_height_px = _photo_print_pixel_size(layout, config)

    return {
        "photoPdfPaper": paper,
        "photoPdfPageSizeMm": {
            "widthMm": round(layout.page_width_mm, 3),
            "heightMm": round(layout.page_height_mm, 3),
        },
        "photoPdfPageCount": len(layout.placements),
        "photoPdfPlacementMode": "oneImageAreaPerPage",
        "photoPdfOverflowPageCount": sum(1 for placement in layout.placements if placement.overflows_page),
        "photoImageFormat": "JPEG",
        "photoImageDpi": round(config.print_layout_dpi, 3),
        "photoImagePixelSize": {
            "widthPx": page_width_px,
            "heightPx": page_height_px,
        },
    }


def _photo_print_pixel_size(
    layout: PhotoPdfLayout,
    config: FlatPhotoPartConfig,
) -> tuple[int, int]:
    px_per_mm = config.print_layout_dpi / 25.4
    return (
        max(1, round(layout.page_width_mm * px_per_mm)),
        max(1, round(layout.page_height_mm * px_per_mm)),
    )


def _render_photo_print_pages(
    parts: list[dict],
    cropped_images: list[Image.Image],
    config: FlatPhotoPartConfig,
) -> tuple[PhotoPdfLayout, list[Image.Image]]:
    px_per_mm = config.print_layout_dpi / 25.4
    layout = _photo_pdf_layout_placements(parts, config)

    def mm_to_px(value: float) -> int:
        return round(value * px_per_mm)

    def mm_size_to_px(value: float) -> int:
        return max(1, mm_to_px(value))

    page_width_px, page_height_px = _photo_print_pixel_size(layout, config)
    canvases: list[Image.Image] = []

    for placement, part, image in zip(layout.placements, parts, cropped_images):
        canvas = Image.new("RGB", (page_width_px, page_height_px), "white")
        draw = ImageDraw.Draw(canvas)
        image_width_px = mm_size_to_px(placement.width_mm)
        image_height_px = mm_size_to_px(placement.height_mm)
        paste_x = mm_to_px(placement.x_mm)
        paste_y = mm_to_px(placement.y_mm)

        image_rgba = image.convert("RGBA").resize(
            (image_width_px, image_height_px),
            Image.Resampling.LANCZOS,
        )
        image_backing = Image.new("RGBA", image_rgba.size, "white")
        image_backing.alpha_composite(image_rgba)
        visible_width = max(0, min(image_backing.width, page_width_px - paste_x))
        visible_height = max(0, min(image_backing.height, page_height_px - paste_y))
        if visible_width and visible_height:
            visible_image = image_backing.crop((0, 0, visible_width, visible_height))
            canvas.paste(visible_image.convert("RGB"), (paste_x, paste_y))

        right = min(page_width_px - 1, paste_x + visible_width - 1)
        bottom = min(page_height_px - 1, paste_y + visible_height - 1)
        if right > paste_x and bottom > paste_y:
            _draw_dashed_rect(
                draw,
                (paste_x, paste_y, right, bottom),
                fill="#e11d48",
                width=2,
                dash=12,
                gap=8,
            )

        label_y_mm: float | None = None
        label_height_mm = 4.0
        label_margin_mm = 2.0
        if placement.y_mm >= label_height_mm + label_margin_mm:
            label_y_mm = placement.y_mm - label_height_mm - 0.5
        elif placement.y_mm + placement.height_mm + label_height_mm + label_margin_mm <= layout.page_height_mm:
            label_y_mm = placement.y_mm + placement.height_mm + label_margin_mm
        if label_y_mm is not None:
            _draw_text_safe(
                draw,
                (paste_x, mm_to_px(label_y_mm)),
                f"L{part['layerIndex']} {part['layerId']}",
            )

        part["photoPrintLayoutMm"] = {
            "pageIndex": placement.page_index,
            "xMm": round(placement.x_mm, 3),
            "yMm": round(placement.y_mm, 3),
            "widthMm": round(placement.width_mm, 3),
            "heightMm": round(placement.height_mm, 3),
            "pageWidthMm": round(layout.page_width_mm, 3),
            "pageHeightMm": round(layout.page_height_mm, 3),
            "overflowsPage": placement.overflows_page,
        }
        canvases.append(canvas)

    return layout, canvases


def _write_print_layout_pdf(
    path: pathlib.Path,
    parts: list[dict],
    cropped_images: list[Image.Image],
    config: FlatPhotoPartConfig,
) -> PhotoPdfLayout:
    layout, canvases = _render_photo_print_pages(parts, cropped_images, config)

    if canvases:
        canvases[0].save(
            path,
            "PDF",
            resolution=config.print_layout_dpi,
            save_all=True,
            append_images=canvases[1:],
        )

    return layout


def _write_photo_jpeg_pages(
    out_dir: pathlib.Path,
    parts: list[dict],
    cropped_images: list[Image.Image],
    config: FlatPhotoPartConfig,
) -> list[pathlib.Path]:
    _layout, canvases = _render_photo_print_pages(parts, cropped_images, config)
    out_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[pathlib.Path] = []
    dpi = round(config.print_layout_dpi)

    for part, canvas in zip(parts, canvases):
        filename = f"photo-2l-layer-{part['layerIndex']}-{_slug(part['layerId'])}.jpg"
        path = out_dir / filename
        canvas.save(
            path,
            "JPEG",
            quality=config.photo_jpeg_quality,
            subsampling=0,
            dpi=(dpi, dpi),
        )
        outputs.append(path)

    return outputs


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
    slot_assignments = _slot_assignments_for_layers(selected_layers, artwork, config)

    for layer in selected_layers:
        part, cropped_image = _part_from_layer(
            layer,
            artwork,
            assets_dir,
            out_dir,
            config,
            slot_assignments.get(layer["layerId"]),
        )
        if part is None or cropped_image is None:
            warnings.append(f"{layer['layerId']}: flat part was not generated")
            continue
        if part["geometry"].get("fallbackUsed"):
            warnings.append(f"{layer['layerId']}: 輪郭生成に失敗したためグリッド方式へフォールバック")
        if part["geometry"].get("connectedComponentCount", 1) > 1:
            warnings.append(f"{layer['layerId']}: STL内に未接続の島が残っている")
        parts.append(part)
        cropped_images.append(cropped_image)

    base = None
    base_path = out_dir / "flat-photo-parts-slot-base.stl"
    if parts:
        base_triangles, base = _base_triangles_for_parts(parts, config)
        base["outputStl"] = _display_path(base_path)
        base["triangles"] = _write_stl(base_path, "flat-photo-parts-slot-base", base_triangles)

    print_layout_path = out_dir / "flat-photo-print-layout.svg"
    print_layout_pdf_path = out_dir / "flat-photo-print-layout.pdf"
    photo_jpeg_dir = out_dir / "photo-jpeg"
    photo_pdf_layout = None
    photo_jpeg_paths: list[pathlib.Path] = []
    if parts:
        _write_print_layout(print_layout_path, parts, cropped_images, config)
        photo_pdf_layout = _write_print_layout_pdf(print_layout_pdf_path, parts, cropped_images, config)
        photo_jpeg_paths = _write_photo_jpeg_pages(photo_jpeg_dir, parts, cropped_images, config)

    report_path = out_dir / "flat-photo-parts-report.json"
    report = {
        "ok": bool(parts) and not warnings,
        "artworkId": artwork["artworkId"],
        "input": {
            "artwork": _display_path(artwork_path),
            "assetsDir": _display_path(assets_dir),
        },
        "flatPhotoPartConfig": _config_to_json(config),
        "printLayout": _photo_pdf_layout_report(photo_pdf_layout, config) if photo_pdf_layout else None,
        "parts": parts,
        "base": base,
        "outputs": {
            "report": _display_path(report_path),
            "printLayoutSvg": _display_path(print_layout_path) if parts else None,
            "printLayoutPdf": _display_path(print_layout_pdf_path) if parts else None,
            "photoJpegFiles": [_display_path(path) for path in photo_jpeg_paths],
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
    parser.add_argument("--shape-mode", choices=("contour", "grid"), default=FlatPhotoPartConfig.shape_mode)
    parser.add_argument("--contour-simplify-mm", type=float, default=FlatPhotoPartConfig.contour_simplify_mm)
    parser.add_argument("--grid-cell-mm", type=float, default=FlatPhotoPartConfig.grid_cell_mm)
    parser.add_argument("--support-bridge-width-mm", type=float, default=FlatPhotoPartConfig.support_bridge_width_mm)
    parser.add_argument("--vertical-support-width-mm", type=float, default=FlatPhotoPartConfig.vertical_support_width_mm)
    parser.add_argument(
        "--vertical-support-min-height-mm",
        type=float,
        default=FlatPhotoPartConfig.vertical_support_min_height_mm,
    )
    parser.add_argument(
        "--support-root-pad-width-mm",
        type=float,
        default=FlatPhotoPartConfig.support_root_pad_width_mm,
    )
    parser.add_argument(
        "--support-root-pad-height-mm",
        type=float,
        default=FlatPhotoPartConfig.support_root_pad_height_mm,
    )
    parser.add_argument(
        "--support-root-overlap-mm",
        type=float,
        default=FlatPhotoPartConfig.support_root_overlap_mm,
    )
    parser.add_argument("--support-mode", choices=("straight", "tree", "rail"), default=FlatPhotoPartConfig.support_mode)
    parser.add_argument("--tree-branch-width-mm", type=float, default=FlatPhotoPartConfig.tree_branch_width_mm)
    parser.add_argument(
        "--tree-support-edge-margin-mm",
        type=float,
        default=FlatPhotoPartConfig.tree_support_edge_margin_mm,
    )
    parser.add_argument("--rail-body-height-mm", type=float, default=FlatPhotoPartConfig.rail_body_height_mm)
    parser.add_argument("--rail-support-width-mm", type=float, default=FlatPhotoPartConfig.rail_support_width_mm)
    parser.add_argument("--rail-edge-margin-mm", type=float, default=FlatPhotoPartConfig.rail_edge_margin_mm)
    parser.add_argument("--mount-mode", choices=("rear", "front-tab"), default=FlatPhotoPartConfig.mount_mode)
    parser.add_argument("--tab-width-mm", type=float, default=FlatPhotoPartConfig.tab_width_mm)
    parser.add_argument("--tab-height-mm", type=float, default=FlatPhotoPartConfig.tab_height_mm)
    parser.add_argument("--tab-overlap-mm", type=float, default=FlatPhotoPartConfig.tab_overlap_mm)
    parser.add_argument("--slot-clearance-mm", type=float, default=FlatPhotoPartConfig.slot_clearance_mm)
    parser.add_argument("--base-mode", choices=("square-grid", "part-tabs"), default=FlatPhotoPartConfig.base_mode)
    parser.add_argument("--base-width-mm", type=float, default=FlatPhotoPartConfig.base_width_mm)
    parser.add_argument("--base-depth-mm", type=float, default=FlatPhotoPartConfig.base_depth_mm)
    parser.add_argument(
        "--base-side-mm",
        type=float,
        default=None,
        help="後方互換用。指定するとbase width/depthの両方を同じ値にする。",
    )
    parser.add_argument("--base-layer-capacity", type=int, default=FlatPhotoPartConfig.base_layer_capacity)
    parser.add_argument("--base-slots-per-layer", type=int, default=FlatPhotoPartConfig.base_slots_per_layer)
    parser.add_argument("--base-slot-length-mm", type=float, default=FlatPhotoPartConfig.base_slot_length_mm)
    parser.add_argument("--base-front-margin-y-mm", type=float, default=FlatPhotoPartConfig.base_margin_y_mm)
    parser.add_argument("--base-back-margin-y-mm", type=float, default=FlatPhotoPartConfig.base_back_margin_y_mm)
    parser.add_argument("--base-layer-gap-mm", type=float, default=FlatPhotoPartConfig.base_layer_gap_mm)
    parser.add_argument(
        "--base-slot-label-engrave-depth-mm",
        type=float,
        default=FlatPhotoPartConfig.base_slot_label_engrave_depth_mm,
    )
    parser.add_argument(
        "--base-slot-label-digit-height-mm",
        type=float,
        default=FlatPhotoPartConfig.base_slot_label_digit_height_mm,
    )
    parser.add_argument(
        "--base-slot-label-offset-y-mm",
        type=float,
        default=FlatPhotoPartConfig.base_slot_label_offset_y_mm,
    )
    parser.add_argument("--base-slot-label-gap-mm", type=float, default=FlatPhotoPartConfig.base_slot_label_gap_mm)
    parser.add_argument(
        "--part-slot-label-engrave-depth-mm",
        type=float,
        default=FlatPhotoPartConfig.part_slot_label_engrave_depth_mm,
    )
    parser.add_argument(
        "--part-slot-label-digit-height-mm",
        type=float,
        default=FlatPhotoPartConfig.part_slot_label_digit_height_mm,
    )
    parser.add_argument(
        "--part-slot-label-offset-y-mm",
        type=float,
        default=FlatPhotoPartConfig.part_slot_label_offset_y_mm,
    )
    parser.add_argument("--part-slot-label-gap-mm", type=float, default=FlatPhotoPartConfig.part_slot_label_gap_mm)
    parser.add_argument(
        "--no-part-slot-label-mirror",
        dest="part_slot_label_mirror_for_back_side",
        action="store_false",
        help="裏面から読める向きへのミラーを切る。",
    )
    parser.set_defaults(part_slot_label_mirror_for_back_side=True)
    parser.add_argument(
        "--background-fill-mode",
        choices=("none", "cover-2l"),
        default=FlatPhotoPartConfig.background_fill_mode,
    )
    parser.add_argument(
        "--print-layout-page-width-mm",
        type=float,
        default=FlatPhotoPartConfig.print_layout_page_width_mm,
    )
    parser.add_argument(
        "--print-layout-page-height-mm",
        type=float,
        default=FlatPhotoPartConfig.print_layout_page_height_mm,
    )
    parser.add_argument("--print-layout-dpi", type=float, default=FlatPhotoPartConfig.print_layout_dpi)
    parser.add_argument("--photo-jpeg-quality", type=int, default=FlatPhotoPartConfig.photo_jpeg_quality)
    background_group = parser.add_mutually_exclusive_group()
    background_group.add_argument("--include-background", dest="include_background", action="store_true")
    background_group.add_argument("--exclude-background", dest="include_background", action="store_false")
    parser.set_defaults(include_background=True)
    parser.add_argument("--layer-id", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    base_width_mm = args.base_side_mm if args.base_side_mm is not None else args.base_width_mm
    base_depth_mm = args.base_side_mm if args.base_side_mm is not None else args.base_depth_mm
    config = FlatPhotoPartConfig(
        target_width_mm=args.target_width_mm,
        part_thickness_mm=args.part_thickness_mm,
        outline_margin_mm=args.outline_margin_mm,
        shape_mode=args.shape_mode,
        contour_simplify_mm=args.contour_simplify_mm,
        grid_cell_mm=args.grid_cell_mm,
        support_bridge_width_mm=args.support_bridge_width_mm,
        vertical_support_width_mm=args.vertical_support_width_mm,
        vertical_support_min_height_mm=args.vertical_support_min_height_mm,
        support_root_pad_width_mm=args.support_root_pad_width_mm,
        support_root_pad_height_mm=args.support_root_pad_height_mm,
        support_root_overlap_mm=args.support_root_overlap_mm,
        support_mode=args.support_mode,
        tree_branch_width_mm=args.tree_branch_width_mm,
        tree_support_edge_margin_mm=args.tree_support_edge_margin_mm,
        rail_body_height_mm=args.rail_body_height_mm,
        rail_support_width_mm=args.rail_support_width_mm,
        rail_edge_margin_mm=args.rail_edge_margin_mm,
        mount_mode=args.mount_mode,
        tab_width_mm=args.tab_width_mm,
        tab_height_mm=args.tab_height_mm,
        tab_overlap_mm=args.tab_overlap_mm,
        slot_clearance_mm=args.slot_clearance_mm,
        base_mode=args.base_mode,
        base_width_mm=base_width_mm,
        base_depth_mm=base_depth_mm,
        base_layer_capacity=args.base_layer_capacity,
        base_slots_per_layer=args.base_slots_per_layer,
        base_slot_length_mm=args.base_slot_length_mm,
        base_margin_y_mm=args.base_front_margin_y_mm,
        base_back_margin_y_mm=args.base_back_margin_y_mm,
        base_layer_gap_mm=args.base_layer_gap_mm,
        base_slot_label_engrave_depth_mm=args.base_slot_label_engrave_depth_mm,
        base_slot_label_digit_height_mm=args.base_slot_label_digit_height_mm,
        base_slot_label_offset_y_mm=args.base_slot_label_offset_y_mm,
        base_slot_label_gap_mm=args.base_slot_label_gap_mm,
        part_slot_label_engrave_depth_mm=args.part_slot_label_engrave_depth_mm,
        part_slot_label_digit_height_mm=args.part_slot_label_digit_height_mm,
        part_slot_label_offset_y_mm=args.part_slot_label_offset_y_mm,
        part_slot_label_gap_mm=args.part_slot_label_gap_mm,
        part_slot_label_mirror_for_back_side=args.part_slot_label_mirror_for_back_side,
        background_fill_mode=args.background_fill_mode,
        print_layout_page_width_mm=args.print_layout_page_width_mm,
        print_layout_page_height_mm=args.print_layout_page_height_mm,
        print_layout_dpi=args.print_layout_dpi,
        photo_jpeg_quality=args.photo_jpeg_quality,
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
        "printLayoutPdf": report["outputs"]["printLayoutPdf"],
        "photoJpegFiles": report["outputs"]["photoJpegFiles"],
        "report": report["outputs"]["report"],
        "warnings": report["warnings"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
