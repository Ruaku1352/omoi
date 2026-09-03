"""Physical Output export builder.

FastAPIから確定Artwork Data + Assetsを受け取り、2.5D物理出力用の
STL / 貼り込みPDF / SVGを生成する。Artwork DataはSSOTとして読み取り専用で扱い、
mm値や製造条件はPhysicalOutputConfig側へ分離する。
"""

from __future__ import annotations

import copy
import importlib.util
import io
import json
import logging
import math
import pathlib
import sys
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import dataclass, fields
from functools import lru_cache
from typing import Any

from PIL import Image, ImageOps
from pydantic import ValidationError

from ai.types import AssetBlob
from app.config import REPO_ROOT, Settings
from app.models.artwork import Artwork
from app.services.validation import check_artwork_rules

logger = logging.getLogger(__name__)

_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_MIME_BY_EXT = {value: key for key, value in _EXT_BY_MIME.items()} | {"jpeg": "image/jpeg"}
_GENERATOR_PATH = REPO_ROOT / "scripts" / "flat_photo_parts_poc.py"


class PhysicalOutputInputError(ValueError):
    """User supplied Artwork / Assets cannot be converted."""

    def __init__(self, issues: Sequence[str]) -> None:
        self.issues = list(issues)
        super().__init__("; ".join(self.issues))


class PhysicalOutputBuildError(RuntimeError):
    """Physical output export failed after input validation."""


@dataclass(frozen=True)
class UploadedAsset:
    filename: str
    content_type: str | None
    data: bytes


@dataclass(frozen=True)
class PhysicalOutputArchive:
    filename: str
    content: bytes
    media_type: str
    report: dict[str, Any]


@lru_cache
def _generator_module() -> Any:
    if not _GENERATOR_PATH.is_file():
        raise PhysicalOutputBuildError("physical output generator is missing")

    spec = importlib.util.spec_from_file_location(
        "omoi_flat_photo_parts_poc",
        _GENERATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise PhysicalOutputBuildError("physical output generator cannot be loaded")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _safe_slug(value: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value).strip("-")
    return safe or "artwork"


def parse_artwork_payload(payload: str) -> Artwork:
    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PhysicalOutputInputError(["artwork must be valid JSON"]) from exc

    try:
        artwork = Artwork.model_validate(raw)
    except ValidationError as exc:
        issues = [
            f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        ]
        raise PhysicalOutputInputError(issues[:20]) from exc

    rule_errors = check_artwork_rules(artwork)
    if rule_errors:
        raise PhysicalOutputInputError(rule_errors[:20])
    return artwork


def parse_physical_output_config(payload: str | None) -> Any:
    module = _generator_module()
    config_cls = module.FlatPhotoPartConfig
    if payload is None or not payload.strip():
        return config_cls()

    try:
        raw = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise PhysicalOutputInputError(["physicalOutputConfig must be valid JSON"]) from exc
    if not isinstance(raw, dict):
        raise PhysicalOutputInputError(["physicalOutputConfig must be a JSON object"])

    field_by_alias = {
        _snake_to_camel(field.name): field.name
        for field in fields(config_cls)
    }
    unknown = sorted(set(raw) - set(field_by_alias))
    if unknown:
        raise PhysicalOutputInputError(
            [f"unknown physicalOutputConfig field: {name}" for name in unknown[:20]]
        )

    kwargs = {field_by_alias[key]: value for key, value in raw.items()}
    config = config_cls(**kwargs)
    issues = _validate_config(config)
    if issues:
        raise PhysicalOutputInputError(issues)
    return config


def build_asset_blobs(
    artwork: Artwork,
    uploads: Sequence[UploadedAsset],
    settings: Settings,
) -> list[AssetBlob]:
    if not uploads:
        raise PhysicalOutputInputError(["assets[] is required"])

    required_asset_ids = required_layer_asset_ids(artwork)
    total_bytes = 0
    by_asset_id: dict[str, AssetBlob] = {}
    for upload in uploads:
        asset_id, filename_mime = _asset_identity_from_filename(upload.filename)
        if asset_id not in required_asset_ids:
            continue

        total_bytes += len(upload.data)
        if len(upload.data) > settings.max_physical_asset_bytes:
            raise PhysicalOutputInputError([f"{upload.filename}: file is too large"])
        if total_bytes > settings.max_physical_total_asset_bytes:
            raise PhysicalOutputInputError(["assets[] total size is too large"])

        mime_type = upload.content_type if upload.content_type in _EXT_BY_MIME else filename_mime
        if mime_type not in _EXT_BY_MIME:
            raise PhysicalOutputInputError([f"{upload.filename}: unsupported asset type"])
        if asset_id in by_asset_id:
            raise PhysicalOutputInputError([f"duplicate asset file: {asset_id}"])

        width_px, height_px = _image_size(upload.data, upload.filename)
        by_asset_id[asset_id] = AssetBlob(
            asset_id=asset_id,
            mime_type=mime_type,
            width_px=width_px,
            height_px=height_px,
            data=upload.data,
        )

    asset_blobs = list(by_asset_id.values())
    presence_errors = _check_layer_assets_present(artwork, asset_blobs)
    if presence_errors:
        raise PhysicalOutputInputError(presence_errors[:20])
    return asset_blobs


def required_layer_asset_ids(artwork: Artwork) -> set[str]:
    return {layer.asset.asset_id for layer in artwork.layers}


def build_physical_output_archive(
    *,
    artwork: Artwork,
    assets: Sequence[AssetBlob],
    config: Any,
) -> PhysicalOutputArchive:
    return _build_physical_output_export(
        artwork=artwork,
        assets=assets,
        config=config,
        output_format="stlZip",
    )


def build_physical_output_pdf(
    *,
    artwork: Artwork,
    assets: Sequence[AssetBlob],
    config: Any,
) -> PhysicalOutputArchive:
    return _build_physical_output_export(
        artwork=artwork,
        assets=assets,
        config=config,
        output_format="photoPdf",
    )


def _build_physical_output_export(
    *,
    artwork: Artwork,
    assets: Sequence[AssetBlob],
    config: Any,
    output_format: str,
) -> PhysicalOutputArchive:
    module = _generator_module()
    artwork_payload = artwork.model_dump(by_alias=True, exclude_none=True)

    with tempfile.TemporaryDirectory(prefix="omoi-physical-output-") as workspace:
        workspace_path = pathlib.Path(workspace)
        input_dir = workspace_path / "input"
        assets_dir = input_dir / "assets"
        output_dir = workspace_path / "output"
        assets_dir.mkdir(parents=True)

        artwork_path = input_dir / "artwork.json"
        artwork_path.write_text(
            json.dumps(artwork_payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        for asset in assets:
            ext = _EXT_BY_MIME[asset.mime_type]
            (assets_dir / f"{asset.asset_id}.{ext}").write_bytes(asset.data)

        report = module.build_poc(
            artwork_path,
            assets_dir,
            output_dir,
            config,
            set(),
            True,
        )
        if not report.get("parts"):
            raise PhysicalOutputBuildError("physical output generator produced no parts")

        if output_format == "stlZip":
            archive_report = _sanitize_report_for_archive(report, include_print_files=False)
            content = _zip_output(
                artwork=artwork_payload,
                report=archive_report,
                output_dir=output_dir,
                config_json=archive_report["flatPhotoPartConfig"],
            )
            filename = f"omoi-physical-output-{_safe_slug(artwork.artwork_id)}.zip"
            media_type = "application/zip"
        elif output_format == "photoPdf":
            archive_report = _sanitize_report_for_archive(report, include_print_files=True)
            pdf_path = output_dir / "flat-photo-print-layout.pdf"
            if not pdf_path.is_file():
                raise PhysicalOutputBuildError("photo print layout PDF was not generated")
            content = pdf_path.read_bytes()
            filename = f"omoi-photo-print-layout-{_safe_slug(artwork.artwork_id)}.pdf"
            media_type = "application/pdf"
        else:
            raise PhysicalOutputBuildError("unknown physical output format")

    return PhysicalOutputArchive(
        filename=filename,
        content=content,
        media_type=media_type,
        report=archive_report,
    )


def _snake_to_camel(value: str) -> str:
    parts = value.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def _validate_config(config: Any) -> list[str]:
    issues: list[str] = []
    positive_fields = (
        "target_width_mm",
        "part_thickness_mm",
        "grid_cell_mm",
        "vertical_support_width_mm",
        "support_root_pad_width_mm",
        "support_root_pad_height_mm",
        "tree_branch_width_mm",
        "rail_body_height_mm",
        "tab_width_mm",
        "tab_height_mm",
        "base_width_mm",
        "base_depth_mm",
        "base_height_mm",
        "part_slot_label_digit_height_mm",
        "print_layout_page_width_mm",
        "print_layout_page_height_mm",
    )
    for field_name in positive_fields:
        value = getattr(config, field_name)
        if not _is_finite_number(value):
            issues.append(f"{_snake_to_camel(field_name)} must be a finite number")
        elif value <= 0:
            issues.append(f"{_snake_to_camel(field_name)} must be greater than 0")
    nonnegative_fields = (
        "base_slot_label_engrave_depth_mm",
        "part_slot_label_engrave_depth_mm",
        "part_slot_label_offset_y_mm",
        "vertical_support_min_height_mm",
        "support_root_overlap_mm",
        "tree_support_edge_margin_mm",
        "rail_edge_margin_mm",
    )
    for field_name in nonnegative_fields:
        value = getattr(config, field_name)
        if not _is_finite_number(value):
            issues.append(f"{_snake_to_camel(field_name)} must be a finite number")
        elif value < 0:
            issues.append(f"{_snake_to_camel(field_name)} must be greater than or equal to 0")
    if config.shape_mode not in {"grid", "contour"}:
        issues.append("shapeMode must be grid or contour")
    if config.mount_mode not in {"front-tab", "rear"}:
        issues.append("mountMode must be front-tab or rear")
    if config.support_mode not in {"straight", "tree", "rail"}:
        issues.append("supportMode must be straight, tree, or rail")
    if config.base_mode not in {"square-grid", "part-tabs"}:
        issues.append("baseMode must be square-grid or part-tabs")
    if config.background_fill_mode not in {"none", "cover-2l"}:
        issues.append("backgroundFillMode must be none or cover-2l")
    for field_name in ("base_layer_capacity", "base_slots_per_layer"):
        value = getattr(config, field_name)
        if not isinstance(value, int) or isinstance(value, bool):
            issues.append(f"{_snake_to_camel(field_name)} must be an integer")
        elif value < 1:
            issues.append(f"{_snake_to_camel(field_name)} must be greater than 0")
    if not isinstance(config.alpha_threshold, int) or isinstance(config.alpha_threshold, bool):
        issues.append("alphaThreshold must be an integer")
    elif not 0 <= config.alpha_threshold <= 255:
        issues.append("alphaThreshold must be between 0 and 255")
    return issues


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _asset_identity_from_filename(filename: str) -> tuple[str, str | None]:
    normalized = filename.replace("\\", "/").split("/")[-1]
    path = pathlib.PurePosixPath(normalized)
    suffix = path.suffix.lower().lstrip(".")
    if not path.stem or not suffix:
        raise PhysicalOutputInputError([f"{filename}: asset filename must be assetId.ext"])
    return path.stem, _MIME_BY_EXT.get(suffix)


def _check_layer_assets_present(artwork: Artwork, assets: Sequence[AssetBlob]) -> list[str]:
    """Physical Outputで使う現在のLayer Assetだけを必須にする。

    sourcePhotos[] や replacementCandidates[] の画像は受け取ってもよいが、
    STL / 貼り込みPDF生成では使わないため必須にしない。
    """

    errors: list[str] = []
    by_id = {asset.asset_id: asset for asset in assets}

    for layer in artwork.layers:
        ref = layer.asset
        blob = by_id.get(ref.asset_id)
        if blob is None:
            errors.append(f"{layer.layer_id}: Layer Asset実体が無い: {ref.asset_id}")
            continue
        if blob.mime_type != ref.mime_type:
            errors.append(
                f"{layer.layer_id}: {ref.asset_id} の mimeType が一致しない "
                f"({blob.mime_type} != {ref.mime_type})"
            )
        if (blob.width_px, blob.height_px) != (ref.width_px, ref.height_px):
            errors.append(
                f"{layer.layer_id}: {ref.asset_id} の実寸 {blob.width_px}x{blob.height_px} が "
                f"Metadata {ref.width_px}x{ref.height_px} と一致しない"
            )

    return errors


def _image_size(data: bytes, filename: str) -> tuple[int, int]:
    try:
        with Image.open(io.BytesIO(data)) as image:
            normalized = ImageOps.exif_transpose(image)
            normalized.load()
            return normalized.size
    except Exception as exc:
        raise PhysicalOutputInputError([f"{filename}: image cannot be decoded"]) from exc


def _sanitize_report_for_archive(
    report: dict[str, Any],
    *,
    include_print_files: bool,
) -> dict[str, Any]:
    sanitized = copy.deepcopy(report)
    sanitized["archiveLayoutVersion"] = "physical-output-api-v1"
    sanitized["input"] = {
        "artwork": "artwork.json",
        "assets": "request multipart assets[]",
    }
    sanitized["outputs"]["report"] = "flat-photo-parts-report.json"
    sanitized["outputs"]["printLayoutSvg"] = (
        "print/flat-photo-print-layout.svg" if include_print_files else None
    )
    sanitized["outputs"]["printLayoutPdf"] = (
        "print/flat-photo-print-layout.pdf" if include_print_files else None
    )

    stl_files = []
    for part in sanitized["parts"]:
        part["outputStl"] = f"stl/{_basename(part['outputStl'])}"
        part["inputAsset"] = f"assets/{part['assetId']}"
        part.pop("assetPath", None)
        stl_files.append(part["outputStl"])
    if sanitized.get("base"):
        sanitized["base"]["outputStl"] = f"stl/{_basename(sanitized['base']['outputStl'])}"
        stl_files.append(sanitized["base"]["outputStl"])
    sanitized["outputs"]["stlFiles"] = stl_files
    return sanitized


def _basename(value: str) -> str:
    return value.replace("\\", "/").rstrip("/").split("/")[-1]


def _zip_output(
    *,
    artwork: dict[str, Any],
    report: dict[str, Any],
    output_dir: pathlib.Path,
    config_json: dict[str, Any],
) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "artwork.json",
            json.dumps(artwork, ensure_ascii=False, indent=2) + "\n",
        )
        archive.writestr(
            "physical-output-config.json",
            json.dumps(config_json, ensure_ascii=False, indent=2) + "\n",
        )
        archive.writestr(
            "flat-photo-parts-report.json",
            json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        )
        archive.writestr(
            "README.md",
            _archive_readme(report),
        )

        for stl_path in sorted(output_dir.glob("*.stl")):
            archive.write(stl_path, f"stl/{stl_path.name}")
    return buffer.getvalue()


def _archive_readme(report: dict[str, Any]) -> str:
    return f"""# omoi Physical Output Export

Input is confirmed Artwork Data + Assets. The included `artwork.json` is copied
for traceability and is not rewritten with physical millimeter values.

## Files

- `stl/`: flat layer parts and the numbered slot base for 3D printing
- `physical-output-config.json`: manufacturing values used for this export
- `flat-photo-parts-report.json`: dimensions, warnings, and assembly metadata

Download the photo-paper layout separately with `outputFormat=photoPdf`.

## Assembly

Use the numbered base slots from front-left to back-right. Parts keep their
Artwork `layerIndex`; details are in `flat-photo-parts-report.json`.

Artwork ID: {report["artworkId"]}
"""
