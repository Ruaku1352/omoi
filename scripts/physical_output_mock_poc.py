#!/usr/bin/env python3
"""Generate a small Physical Output PoC from the shared mock Artwork.

The script intentionally keeps manufacturing values in PhysicalOutputConfig
instead of writing millimeter values back into Artwork Data.
"""

from __future__ import annotations

import argparse
import json
import math
import pathlib
import re
from dataclasses import dataclass
from typing import Iterable


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARTWORK = ROOT / "contracts" / "mock" / "artwork.json"
DEFAULT_MANIFEST = ROOT / "contracts" / "mock" / "asset-manifest.json"
DEFAULT_OUT = ROOT / "tmp" / "physical-output-poc"


@dataclass(frozen=True)
class PhysicalOutputConfig:
    target_width_mm: float = 160.0
    plate_thickness_mm: float = 2.0
    layer_gap_mm: float = 6.0
    slot_clearance_mm: float = 0.6
    base_margin_x_mm: float = 10.0
    base_margin_y_mm: float = 8.0
    base_end_cap_mm: float = 8.0
    base_height_mm: float = 10.0
    guide_frame_width_mm: float = 1.2
    guide_frame_height_mm: float = 0.6
    printer: str = "PoC generic FDM"
    material: str = "PLA"


def _config_to_json(config: PhysicalOutputConfig) -> dict:
    return {
        "targetWidthMm": config.target_width_mm,
        "plateThicknessMm": config.plate_thickness_mm,
        "layerGapMm": config.layer_gap_mm,
        "slotClearanceMm": config.slot_clearance_mm,
        "baseMarginXMm": config.base_margin_x_mm,
        "baseMarginYMm": config.base_margin_y_mm,
        "baseEndCapMm": config.base_end_cap_mm,
        "baseHeightMm": config.base_height_mm,
        "guideFrameWidthMm": config.guide_frame_width_mm,
        "guideFrameHeightMm": config.guide_frame_height_mm,
        "printer": config.printer,
        "material": config.material,
    }


def _load_json(path: pathlib.Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _slug(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip("-")
    return safe or "layer"


def _normal(a: tuple[float, float, float], b: tuple[float, float, float], c: tuple[float, float, float]) -> tuple[float, float, float]:
    ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
    vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
    nx = uy * vz - uz * vy
    ny = uz * vx - ux * vz
    nz = ux * vy - uy * vx
    length = math.sqrt(nx * nx + ny * ny + nz * nz)
    if length == 0:
        return (0.0, 0.0, 0.0)
    return (nx / length, ny / length, nz / length)


def _box(
    min_x: float,
    min_y: float,
    min_z: float,
    max_x: float,
    max_y: float,
    max_z: float,
) -> list[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]]:
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
        (v000, v010, v110), (v000, v110, v100),  # bottom
        (v001, v101, v111), (v001, v111, v011),  # top
        (v000, v100, v101), (v000, v101, v001),  # front
        (v010, v011, v111), (v010, v111, v110),  # back
        (v000, v001, v011), (v000, v011, v010),  # left
        (v100, v110, v111), (v100, v111, v101),  # right
    ]


def _write_stl(
    path: pathlib.Path,
    name: str,
    triangles: Iterable[tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]],
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


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return min(max(value, min_value), max_value)


def _layer_conversion(layer: dict, target_width_mm: float, target_height_mm: float) -> dict:
    asset = layer["asset"]
    layer_width_mm = layer["scale"] * target_width_mm
    layer_height_mm = layer_width_mm * asset["heightPx"] / asset["widthPx"]
    x_mm = layer["x"] * target_width_mm
    y_mm = layer["y"] * target_height_mm
    left_mm = x_mm - layer_width_mm / 2
    right_mm = x_mm + layer_width_mm / 2
    top_mm = y_mm - layer_height_mm / 2
    bottom_mm = y_mm + layer_height_mm / 2
    clipped = (
        left_mm < 0
        or right_mm > target_width_mm
        or top_mm < 0
        or bottom_mm > target_height_mm
    )
    return {
        "layerId": layer["layerId"],
        "label": layer["label"],
        "sourcePhotoId": layer["sourcePhotoId"],
        "sourceLayerId": layer["sourceLayerId"],
        "assetId": asset["assetId"],
        "layerIndex": layer["layerIndex"],
        "xMm": round(x_mm, 3),
        "yMm": round(y_mm, 3),
        "layerWidthMm": round(layer_width_mm, 3),
        "layerHeightMm": round(layer_height_mm, 3),
        "footprintMm": {
            "left": round(left_mm, 3),
            "top": round(top_mm, 3),
            "right": round(right_mm, 3),
            "bottom": round(bottom_mm, 3),
        },
        "clippedByCanvas": clipped,
    }


def _layer_plate_triangles(layer_mm: dict, target_width_mm: float, target_height_mm: float, config: PhysicalOutputConfig):
    tris = _box(0, 0, 0, target_width_mm, target_height_mm, config.plate_thickness_mm)

    footprint = layer_mm["footprintMm"]
    left = _clamp(footprint["left"], 0, target_width_mm)
    right = _clamp(footprint["right"], 0, target_width_mm)
    top = _clamp(footprint["top"], 0, target_height_mm)
    bottom = _clamp(footprint["bottom"], 0, target_height_mm)
    frame = min(config.guide_frame_width_mm, max((right - left) / 2, 0), max((bottom - top) / 2, 0))
    z0 = config.plate_thickness_mm
    z1 = config.plate_thickness_mm + config.guide_frame_height_mm

    if frame > 0:
        tris += _box(left, top, z0, right, min(top + frame, bottom), z1)
        tris += _box(left, max(bottom - frame, top), z0, right, bottom, z1)
        tris += _box(left, min(top + frame, bottom), z0, min(left + frame, right), max(bottom - frame, top), z1)
        tris += _box(max(right - frame, left), min(top + frame, bottom), z0, right, max(bottom - frame, top), z1)

    return tris


def _base_triangles(layer_count: int, target_width_mm: float, config: PhysicalOutputConfig) -> tuple[list, list[dict], dict]:
    slot_width = config.plate_thickness_mm + config.slot_clearance_mm
    pitch = slot_width + config.layer_gap_mm
    base_width = target_width_mm + config.base_margin_x_mm * 2
    total_depth = config.base_margin_y_mm * 2 + slot_width * layer_count + config.layer_gap_mm * max(layer_count - 1, 0)

    slot_spans: list[dict] = []
    for index in range(layer_count):
        y0 = config.base_margin_y_mm + index * pitch
        y1 = y0 + slot_width
        slot_spans.append(
            {
                "layerIndex": index,
                "frontMm": round(y0, 3),
                "backMm": round(y1, 3),
                "slotWidthMm": round(slot_width, 3),
                "centerDepthMm": round((y0 + y1) / 2, 3),
            }
        )

    solid_spans: list[tuple[float, float]] = []
    cursor = 0.0
    for slot in slot_spans:
        y0 = slot["frontMm"]
        y1 = slot["backMm"]
        if cursor < y0:
            solid_spans.append((cursor, y0))
        cursor = y1
    if cursor < total_depth:
        solid_spans.append((cursor, total_depth))

    tris = []
    for y0, y1 in solid_spans:
        tris += _box(0, y0, 0, base_width, y1, config.base_height_mm)
    for slot in slot_spans:
        y0 = slot["frontMm"]
        y1 = slot["backMm"]
        tris += _box(0, y0, 0, config.base_end_cap_mm, y1, config.base_height_mm)
        tris += _box(base_width - config.base_end_cap_mm, y0, 0, base_width, y1, config.base_height_mm)

    dimensions = {
        "widthMm": round(base_width, 3),
        "depthMm": round(total_depth, 3),
        "heightMm": round(config.base_height_mm, 3),
    }
    return tris, slot_spans, dimensions


def _manifest_by_id(manifest: dict) -> dict[str, dict]:
    return {asset["assetId"]: asset for asset in manifest.get("assets", [])}


def _validate_manifest_metadata(artwork: dict, manifest: dict) -> list[str]:
    by_id = _manifest_by_id(manifest)
    warnings: list[str] = []
    for layer in artwork["layers"]:
        asset = layer["asset"]
        manifest_asset = by_id.get(asset["assetId"])
        if not manifest_asset:
            warnings.append(f"{layer['layerId']}: assetId {asset['assetId']} is missing from manifest")
            continue
        expected = (asset["mimeType"], asset["widthPx"], asset["heightPx"])
        actual = (manifest_asset["mimeType"], manifest_asset["widthPx"], manifest_asset["heightPx"])
        if expected != actual:
            warnings.append(f"{layer['layerId']}: manifest metadata {actual} does not match artwork {expected}")
    return warnings


def build_poc(artwork_path: pathlib.Path, manifest_path: pathlib.Path, out_dir: pathlib.Path, config: PhysicalOutputConfig) -> dict:
    artwork = _load_json(artwork_path)
    manifest = _load_json(manifest_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    target_height_mm = config.target_width_mm / artwork["canvas"]["aspectRatio"]
    layers = sorted(artwork["layers"], key=lambda layer: layer["layerIndex"])
    converted_layers = [
        _layer_conversion(layer, config.target_width_mm, target_height_mm)
        for layer in layers
    ]

    manifest_warnings = _validate_manifest_metadata(artwork, manifest)
    stl_outputs: list[str] = []
    for converted in converted_layers:
        name = f"mock-layer-{converted['layerIndex']}-{_slug(converted['layerId'])}"
        path = out_dir / f"{name}.stl"
        triangles = _layer_plate_triangles(converted, config.target_width_mm, target_height_mm, config)
        converted["outputStl"] = str(path.relative_to(ROOT)).replace("\\", "/")
        converted["triangles"] = _write_stl(path, name, triangles)
        stl_outputs.append(converted["outputStl"])

    base_triangles, slot_spans, base_dimensions = _base_triangles(len(converted_layers), config.target_width_mm, config)
    base_path = out_dir / "mock-layered-slot-base.stl"
    base_triangles_count = _write_stl(base_path, "mock-layered-slot-base", base_triangles)
    stl_outputs.append(str(base_path.relative_to(ROOT)).replace("\\", "/"))

    config_path = out_dir / "physical-output-config.json"
    config_json = _config_to_json(config)
    config_path.write_text(json.dumps(config_json, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    report_path = out_dir / "physical-output-report.json"
    report = {
        "ok": not manifest_warnings,
        "artworkId": artwork["artworkId"],
        "input": {
            "artwork": str(artwork_path.relative_to(ROOT)).replace("\\", "/"),
            "assetManifest": str(manifest_path.relative_to(ROOT)).replace("\\", "/"),
        },
        "physicalOutputConfig": config_json,
        "canvasMm": {
            "targetWidthMm": round(config.target_width_mm, 3),
            "targetHeightMm": round(target_height_mm, 3),
            "aspectRatio": artwork["canvas"]["aspectRatio"],
        },
        "layers": converted_layers,
        "base": {
            "outputStl": str(base_path.relative_to(ROOT)).replace("\\", "/"),
            "triangles": base_triangles_count,
            "dimensionsMm": base_dimensions,
            "slots": slot_spans,
        },
        "outputs": {
            "config": str(config_path.relative_to(ROOT)).replace("\\", "/"),
            "report": str(report_path.relative_to(ROOT)).replace("\\", "/"),
            "stlFiles": stl_outputs,
        },
        "warnings": manifest_warnings
        + [
            f"{layer['layerId']}: footprint is clipped by canvas"
            for layer in converted_layers
            if layer["clippedByCanvas"]
        ],
        "schemaImpact": {
            "needsArtworkSchemaChange": False,
            "reason": "This PoC can use existing x / y / scale / layerIndex plus asset dimensions. Manufacturing values remain in PhysicalOutputConfig.",
        },
        "recommendation": {
            "runtime": "independent local script for the first PoC",
            "repositoryPlacement": "keep in scripts/ while STL runtime is PoC-after-FIX; do not add a root physical-output/ directory yet",
        },
    }
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Physical Output STL PoC from the shared mock Artwork.")
    parser.add_argument("--artwork", type=pathlib.Path, default=DEFAULT_ARTWORK)
    parser.add_argument("--asset-manifest", type=pathlib.Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--out", type=pathlib.Path, default=DEFAULT_OUT)
    parser.add_argument("--target-width-mm", type=float, default=PhysicalOutputConfig.target_width_mm)
    parser.add_argument("--plate-thickness-mm", type=float, default=PhysicalOutputConfig.plate_thickness_mm)
    parser.add_argument("--layer-gap-mm", type=float, default=PhysicalOutputConfig.layer_gap_mm)
    parser.add_argument("--slot-clearance-mm", type=float, default=PhysicalOutputConfig.slot_clearance_mm)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = PhysicalOutputConfig(
        target_width_mm=args.target_width_mm,
        plate_thickness_mm=args.plate_thickness_mm,
        layer_gap_mm=args.layer_gap_mm,
        slot_clearance_mm=args.slot_clearance_mm,
    )
    report = build_poc(args.artwork, args.asset_manifest, args.out, config)
    print(json.dumps({
        "ok": report["ok"],
        "artworkId": report["artworkId"],
        "canvasMm": report["canvasMm"],
        "stlFiles": report["outputs"]["stlFiles"],
        "report": report["outputs"]["report"],
        "warnings": report["warnings"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
