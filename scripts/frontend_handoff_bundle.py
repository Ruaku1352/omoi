"""Real AI PoC結果をFrontend向け1フォルダへまとめる開発補助。

Product APIやCloud Runの保存処理ではない。GenerationResultの公開境界は変えず、
Git管理外の ``poc-output/`` でのみ使う。
"""

from __future__ import annotations

import json
import math
import sys
from collections.abc import Mapping, Sequence
from io import BytesIO
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageOps

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from ai.gemini import GenerationObserver  # noqa: E402
from ai.internal_models import (  # noqa: E402
    SegmentationComponent,
    SemanticPlan,
    VisualElementCandidate,
)
from ai.quality import MaskQuality  # noqa: E402
from ai.segmentation import SegmentationResult  # noqa: E402
from ai.types import AssetBlob  # noqa: E402
from app.models.api import GenerateSuccessResponse  # noqa: E402
from app.models.artwork import Artwork  # noqa: E402
from app.models.asset_manifest import AssetManifest, AssetManifestEntry  # noqa: E402
from app.services.validation import check_artwork_rules, check_assets_present  # noqa: E402

_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
_BBOX_COLORS = ("#ff3b30", "#007aff", "#34c759", "#ff9500", "#af52de", "#00c7be")


class PocDebugObserver(GenerationObserver):
    """Semantic候補、実bbox、実maskをPoC用debug directoryへ保存する。"""

    def __init__(self, debug_dir: Path) -> None:
        self._debug_dir = debug_dir
        self._sources_dir = debug_dir / "sources"
        self._bbox_dir = debug_dir / "bbox"
        self._masks_dir = debug_dir / "masks"
        for path in (self._sources_dir, self._bbox_dir, self._masks_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._mask_records: list[dict[str, Any]] = []

    def semantic_plan(self, plan: SemanticPlan, images: Sequence[Image.Image]) -> None:
        _write_json(self._debug_dir / "semantic-plan.json", plan.model_dump(mode="json"))
        bbox_records: list[dict[str, Any]] = []
        for source_index, source in enumerate(images):
            preview = _thumbnail(source.convert("RGB"), 1200)
            preview.save(self._sources_dir / f"source-{source_index + 1:02d}.png")
            annotated = preview.copy()
            draw = ImageDraw.Draw(annotated)
            matching = [
                candidate
                for candidate in plan.candidates
                if candidate.source_photo_index == source_index
            ]
            for candidate_index, candidate in enumerate(matching):
                color = _BBOX_COLORS[candidate_index % len(_BBOX_COLORS)]
                for component in candidate.components:
                    box = component.box_2d
                    coords = (
                        round(box.x_min / 1000 * preview.width),
                        round(box.y_min / 1000 * preview.height),
                        round(box.x_max / 1000 * preview.width),
                        round(box.y_max / 1000 * preview.height),
                    )
                    draw.rectangle(coords, outline=color, width=max(2, preview.width // 400))
                    bbox_records.append(
                        {
                            "candidateId": candidate.candidate_id,
                            "candidateLabel": candidate.label,
                            "selectionReason": candidate.selection_reason,
                            "sourcePhotoIndex": source_index,
                            "componentId": component.component_id,
                            "componentLabel": component.label,
                            "box2d": component.box_2d.model_dump(),
                            "color": color,
                        }
                    )
            annotated.save(self._bbox_dir / f"source-{source_index + 1:02d}-bbox.png")
        _write_json(self._bbox_dir / "index.json", {"boxes": bbox_records})
        self._write_summary(plan)

    def segmentation_attempt(
        self,
        *,
        candidate: VisualElementCandidate,
        component: SegmentationComponent,
        source_photo_index: int,
        image: Image.Image,
        result: SegmentationResult,
        quality: MaskQuality,
        attempt: int,
    ) -> None:
        del image
        sequence = len(self._mask_records) + 1
        filename = f"mask-{sequence:03d}.png"
        mask_image = Image.fromarray(result.mask.astype(np.uint8) * 255, mode="L")
        _thumbnail(mask_image, 1200).save(self._masks_dir / filename)
        record = {
                "file": filename,
                "candidateId": candidate.candidate_id,
                "candidateLabel": candidate.label,
                "componentId": component.component_id,
                "componentLabel": component.label,
                "sourcePhotoIndex": source_photo_index,
                "attempt": attempt,
                "promptBoxPx": list(result.prompt_box_px),
                "accepted": quality.accepted,
                "failureReason": quality.reason,
                "score": quality.score,
                "areaRatio": quality.area_ratio,
                "bboxCoverage": quality.bbox_coverage,
                "borderTouch": quality.border_touch,
        }
        if quality.diagnostics is not None:
            record["diagnostics"] = {
                "componentCount": quality.diagnostics.component_count,
                "largestComponentRatio": quality.diagnostics.largest_component_ratio,
                "topComponentAreaRatios": list(quality.diagnostics.top_component_area_ratios),
                "tailComponentAreaRatio": quality.diagnostics.tail_component_area_ratio,
                "analysisScale": quality.diagnostics.analysis_scale,
            }
        self._mask_records.append(record)
        _write_json(self._masks_dir / "index.json", {"attempts": self._mask_records})

    def _write_summary(self, plan: SemanticPlan) -> None:
        lines = [
            "# AI生成Debug Summary",
            "",
            f"- memory summary: {plan.memory_summary}",
            f"- candidate count: {len(plan.candidates)}",
            "",
            "## Candidates",
            "",
        ]
        for candidate in plan.candidates:
            lines.extend(
                [
                    f"- `{candidate.candidate_id}` {candidate.label}",
                    f"  - source photo: {candidate.source_photo_index + 1}",
                    f"  - reason: {candidate.selection_reason}",
                    f"  - components: {len(candidate.components)}",
                ]
            )
        (self._debug_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_frontend_handoff_bundle(
    *,
    output_dir: Path,
    artwork: Artwork,
    assets: Sequence[AssetBlob],
    memory_text: str,
    metrics: Mapping[str, Any],
    selected_photo_files: Sequence[str],
    api_asset_base_url: str = "https://poc.omoi.invalid/assets",
    preview_width_px: int = 1600,
) -> None:
    """検証済みReal生成結果からAPI互換版とローカル版のBundleを完成させる。"""

    if len(selected_photo_files) != len(artwork.source_photos):
        raise ValueError("入力ファイル一覧とArtwork sourcePhotosが一致しません")
    if len(artwork.source_photos) != 5 or len(artwork.layers) != 4:
        raise ValueError("MVP Frontend handoffは写真5枚・4層である必要があります")
    if not math.isclose(artwork.canvas.aspect_ratio, 178 / 127, rel_tol=0, abs_tol=1e-12):
        raise ValueError("MVP Frontend handoffは2L判Landscapeである必要があります")
    if not memory_text.strip():
        raise ValueError("MVP Frontend handoffにはmemoryTextが必要です")
    if preview_width_px <= 0:
        raise ValueError("preview_width_pxは正の値にしてください")
    if check_artwork_rules(artwork):
        raise ValueError("ArtworkのRuntime規則を満たしていません")
    if check_assets_present(artwork, assets):
        raise ValueError("Artworkが参照するAssetが不足しています")

    _validate_debug_evidence(output_dir)

    layer_asset_ids = {layer.asset.asset_id for layer in artwork.layers}
    layer_asset_ids.update(
        candidate.asset.asset_id
        for layer in artwork.layers
        for candidate in layer.replacement_candidates
    )
    referenced_asset_ids = {
        photo.asset.asset_id for photo in artwork.source_photos
    } | layer_asset_ids
    by_id: dict[str, AssetBlob] = {}
    for asset in assets:
        if asset.asset_id in by_id:
            raise ValueError(f"AssetBlobのassetIdが重複しています: {asset.asset_id}")
        _validate_asset_bytes(asset, is_layer_asset=asset.asset_id in layer_asset_ids)
        by_id[asset.asset_id] = asset
    if by_id.keys() - referenced_asset_ids:
        raise ValueError("Artworkから参照されないAssetBlobが含まれています")

    output_dir.mkdir(parents=True, exist_ok=True)
    assets_dir = output_dir / "assets"
    debug_dir = output_dir / "debug"
    layer_preview_dir = debug_dir / "layers"
    source_preview_dir = debug_dir / "sources"
    for path in (assets_dir, debug_dir, layer_preview_dir, source_preview_dir):
        path.mkdir(parents=True, exist_ok=True)

    api_entries: list[AssetManifestEntry] = []
    bundle_entries: list[AssetManifestEntry] = []
    filename_by_id: dict[str, str] = {}
    for asset in assets:
        extension = _EXT_BY_MIME.get(asset.mime_type)
        if extension is None:
            raise ValueError(f"未対応のmimeType: {asset.mime_type}")
        filename = _asset_filename(asset.asset_id, extension)
        filename_by_id[asset.asset_id] = filename
        (assets_dir / filename).write_bytes(asset.data)
        common = {
            "asset_id": asset.asset_id,
            "mime_type": asset.mime_type,
            "width_px": asset.width_px,
            "height_px": asset.height_px,
        }
        api_entries.append(
            AssetManifestEntry(
                **common,
                url=(
                    f"{api_asset_base_url.rstrip('/')}/{artwork.artwork_id}/{filename}"
                ),
            )
        )
        bundle_entries.append(AssetManifestEntry(**common, url=f"assets/{filename}"))

    api_manifest = AssetManifest(assets=api_entries)
    bundle_manifest = AssetManifest(assets=bundle_entries)
    api_response = GenerateSuccessResponse(artwork=artwork, asset_manifest=api_manifest)
    bundle_response = GenerateSuccessResponse(artwork=artwork, asset_manifest=bundle_manifest)

    artwork_payload = artwork.model_dump(by_alias=True, exclude_none=True)
    _write_json(output_dir / "artwork.json", artwork_payload)
    _write_json(output_dir / "asset-manifest.json", api_manifest.model_dump(by_alias=True))
    _write_json(
        output_dir / "asset-manifest.bundle.json",
        bundle_manifest.model_dump(by_alias=True),
    )
    _write_json(
        output_dir / "generate-success-response.json",
        api_response.model_dump(by_alias=True, exclude_none=True),
    )
    _write_json(
        output_dir / "generate-success-response.bundle.json",
        bundle_response.model_dump(by_alias=True, exclude_none=True),
    )
    (output_dir / "memory-text.txt").write_text(memory_text.rstrip() + "\n", encoding="utf-8")
    _write_json(output_dir / "metrics.json", dict(metrics))

    _write_debug_previews(
        artwork,
        by_id,
        filename_by_id,
        debug_dir,
        source_preview_dir,
        layer_preview_dir,
        preview_width_px,
    )
    (output_dir / "README.md").write_text(
        _bundle_readme(selected_photo_files), encoding="utf-8"
    )


def render_composition_preview(
    artwork: Artwork,
    assets_by_id: Mapping[str, AssetBlob],
    output_path: Path,
    width_px: int,
) -> None:
    height_px = round(width_px / artwork.canvas.aspect_ratio)
    canvas = Image.new("RGBA", (width_px, height_px), "#F7F3EA")
    for layer in sorted(artwork.layers, key=lambda item: item.layer_index):
        asset = assets_by_id[layer.asset.asset_id]
        with Image.open(BytesIO(asset.data)) as source:
            image = source.convert("RGBA")
        display_width = max(1, round(layer.scale * width_px))
        display_height = max(1, round(display_width * image.height / image.width))
        resized = image.resize((display_width, display_height), Image.Resampling.LANCZOS)
        left = round(layer.x * width_px - display_width / 2)
        top = round(layer.y * height_px - display_height / 2)
        canvas.alpha_composite(resized, (left, top))
    canvas.save(output_path, format="PNG")


def _write_debug_previews(
    artwork: Artwork,
    assets_by_id: Mapping[str, AssetBlob],
    filename_by_id: Mapping[str, str],
    debug_dir: Path,
    source_dir: Path,
    layer_dir: Path,
    preview_width_px: int,
) -> None:
    for index, photo in enumerate(artwork.source_photos, start=1):
        asset = assets_by_id[photo.asset.asset_id]
        with Image.open(BytesIO(asset.data)) as source:
            preview = _thumbnail(ImageOps.exif_transpose(source).convert("RGB"), 1200)
        preview.save(source_dir / f"source-{index:02d}.png")
    for layer in artwork.layers:
        asset = assets_by_id[layer.asset.asset_id]
        (layer_dir / filename_by_id[asset.asset_id]).write_bytes(asset.data)
    render_composition_preview(
        artwork,
        assets_by_id,
        debug_dir / "composition-preview.png",
        preview_width_px,
    )


def _validate_asset_bytes(asset: AssetBlob, *, is_layer_asset: bool) -> None:
    try:
        with Image.open(BytesIO(asset.data)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
            if image.size != (asset.width_px, asset.height_px):
                raise ValueError(f"Asset寸法がMetadataと一致しません: {asset.asset_id}")
            if is_layer_asset:
                if image.mode != "RGBA":
                    raise ValueError(f"Layer AssetがRGBAではありません: {asset.asset_id}")
                if image.getchannel("A").getextrema()[0] != 0:
                    raise ValueError(f"Layer PNGに透明pixelがありません: {asset.asset_id}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Asset画像をdecodeできません: {asset.asset_id}") from exc


def _validate_debug_evidence(output_dir: Path) -> None:
    """成功BundleにSemantic/bbox/maskの実行根拠が揃っていることを確認する。"""

    debug_dir = output_dir / "debug"
    required_files = (
        debug_dir / "semantic-plan.json",
        debug_dir / "bbox" / "index.json",
        debug_dir / "masks" / "index.json",
    )
    if not all(path.is_file() for path in required_files):
        raise ValueError("Frontend handoffに必要なSemantic/bbox/mask記録が不足しています")
    if not any((debug_dir / "bbox").glob("*-bbox.png")):
        raise ValueError("Frontend handoffにbbox previewがありません")
    if not any((debug_dir / "masks").glob("mask-*.png")):
        raise ValueError("Frontend handoffにmask previewがありません")


def _asset_filename(asset_id: str, extension: str) -> str:
    """現在のAI生成IDをportableな単一filenameとして検証する。"""

    forbidden = '<>:"/\\|?*'
    if any(character in asset_id for character in forbidden) or asset_id.endswith((".", " ")):
        raise ValueError(f"Bundle filenameに使えないassetIdです: {asset_id}")
    reserved = {"CON", "PRN", "AUX", "NUL"} | {
        f"{prefix}{number}" for prefix in ("COM", "LPT") for number in range(1, 10)
    }
    if asset_id.upper() in reserved:
        raise ValueError(f"Windows予約名のassetIdです: {asset_id}")
    return f"{asset_id}.{extension}"


def _bundle_readme(selected_photo_files: Sequence[str]) -> str:
    inputs = "\n".join(f"- `{name}`" for name in selected_photo_files)
    return f"""# omoi Frontend Debug Bundle

このフォルダは、Real AIへ入力した5枚の写真とmemoryTextから生成した4層・2L判Landscapeの
Frontend handoffです。個人データを含むため、外部公開やGit commitはしないでください。

## BackendからFrontendへ返る基本形式

```json
{{
  "artwork": {{ ... }},
  "assetManifest": {{ "assets": [ ... ] }}
}}
```

## Responseとファイルの対応

- `generate-success-response.json`: Backend成功Responseそのものに相当する実API互換版
- `artwork.json`: 上記Responseの `artwork` を単独で取り出したもの
- `asset-manifest.json`: 上記Responseの `assetManifest` を単独で取り出した実API互換版
- `assets/`: `assetManifest` が参照するsource / layer Assetの実ファイル群
- `memory-text.txt`: 今回のReal生成入力で使った思い出テキスト
- `metrics.json`: Semantic Planning / Segmentation / Composition / Totalの計測値
- `debug/`: composition、source、bbox、mask、layerの補助確認用ファイル群

## Frontend担当がまず読む流れ

1. まず `generate-success-response.json` でBackend成功Responseの外形を見る
2. 必要に応じて `artwork.json` / `asset-manifest.json` を個別確認する
3. ローカル実行では `generate-success-response.bundle.json` を読み、Manifestが指す
   `assets/` の実ファイルを解決する
4. 同じArtwork Dataを3D Preview / 2D Editのデバッグに使う
5. 目視確認は `debug/composition-preview.png`、`debug/bbox/`、`debug/masks/`、
   `debug/layers/` を見る

## 実API互換版とBundle向け版

- `generate-success-response.json` / `asset-manifest.json` は実API互換版。URLはPoC用の
  absolute URL表現で、共有後に実際に配信されることは保証しない
- `generate-success-response.bundle.json` / `asset-manifest.bundle.json` はローカルdebug版。
  違いはManifestの `url` が `assets/...` の相対pathであることだけで、Artworkは同一
- `file://` 直開きではなく、Bundleの親Directoryで `python -m http.server 8000` 等を実行し、
  HTTP経由で相対URLを解決する

## 入力写真

{inputs}
"""


def _thumbnail(image: Image.Image, max_side: int) -> Image.Image:
    result = image.copy()
    result.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)
    return result


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
