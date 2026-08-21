"""JSON Schema では表現できない Artwork の規則を検証する。

`scripts/validate_contracts.py` と同じ規則をRuntime側でも通す。
AI Moduleの自己申告を信用せず、Backendが必ずここを通してから返す（AGENTS.md §5）。
Schemaを満たさないArtworkやAssetが欠けたArtworkを成功扱いしない（AGENTS.md §9）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from ai.types import AssetBlob
from app.models.artwork import Artwork, AssetRef


def _all_asset_refs(artwork: Artwork) -> Iterable[tuple[str, AssetRef]]:
    for photo in artwork.source_photos:
        yield photo.source_photo_id, photo.asset
    for layer in artwork.layers:
        yield layer.layer_id, layer.asset
        for candidate in layer.replacement_candidates:
            yield candidate.candidate_id, candidate.asset


def check_artwork_rules(artwork: Artwork) -> list[str]:
    errors: list[str] = []

    indexes = sorted(layer.layer_index for layer in artwork.layers)
    if indexes != list(range(len(artwork.layers))):
        errors.append(
            f"layerIndex は 0..{len(artwork.layers) - 1} の重複なし連番である必要がある "
            f"(actual: {indexes})"
        )

    photo_ids = {photo.source_photo_id for photo in artwork.source_photos}
    if len(photo_ids) != len(artwork.source_photos):
        errors.append("sourcePhotoId が重複している")

    layer_ids: set[str] = set()
    candidate_ids: set[str] = set()
    for layer in artwork.layers:
        if layer.layer_id in layer_ids:
            errors.append(f"layerId が重複している: {layer.layer_id}")
        layer_ids.add(layer.layer_id)

        # P0 の Artwork Data に rotation は持たせない【FIX】
        if "rotation" in layer.model_extra:
            errors.append(f"{layer.layer_id}: rotation は P0 の Artwork Data に持たせない")

        if layer.source_photo_id not in photo_ids:
            errors.append(
                f"{layer.layer_id}: sourcePhotoId "
                f"'{layer.source_photo_id}' が sourcePhotos[] に無い"
            )

        for candidate in layer.replacement_candidates:
            if candidate.candidate_id in candidate_ids:
                errors.append(f"candidateId が重複している: {candidate.candidate_id}")
            candidate_ids.add(candidate.candidate_id)
            if candidate.source_photo_id not in photo_ids:
                errors.append(
                    f"{candidate.candidate_id}: sourcePhotoId "
                    f"'{candidate.source_photo_id}' が sourcePhotos[] に無い"
                )

    seen_assets: dict[str, AssetRef] = {}
    for owner, asset in _all_asset_refs(artwork):
        known = seen_assets.get(asset.asset_id)
        if known is None:
            seen_assets[asset.asset_id] = asset
        elif (known.mime_type, known.width_px, known.height_px) != (
            asset.mime_type,
            asset.width_px,
            asset.height_px,
        ):
            errors.append(f"{owner}: assetId '{asset.asset_id}' のMetadataが一致しない")

    return errors


def check_assets_present(artwork: Artwork, assets: Sequence[AssetBlob]) -> list[str]:
    """Artworkが参照する全Assetの実体が揃っているかを見る。"""

    errors: list[str] = []
    by_id = {asset.asset_id: asset for asset in assets}

    for owner, ref in _all_asset_refs(artwork):
        blob = by_id.get(ref.asset_id)
        if blob is None:
            errors.append(f"{owner}: Asset実体が無い: {ref.asset_id}")
            continue
        if blob.mime_type != ref.mime_type:
            errors.append(
                f"{owner}: {ref.asset_id} の mimeType が一致しない "
                f"({blob.mime_type} != {ref.mime_type})"
            )
        if (blob.width_px, blob.height_px) != (ref.width_px, ref.height_px):
            errors.append(
                f"{owner}: {ref.asset_id} の実寸 {blob.width_px}x{blob.height_px} が "
                f"Metadata {ref.width_px}x{ref.height_px} と一致しない"
            )

    return errors
