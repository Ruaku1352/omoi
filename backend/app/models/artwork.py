"""Artwork Data の Pydantic Model。

**正本は `/contracts/artwork.schema.json`。**ここはその写像であって別の正本ではない。
Schemaが変わったら同一PRで追随する。ズレていないことは
`tests/test_contract_sync.py` が正本Schemaへ突き合わせて検証する。

Schema上 `layer` / `replacementCandidate` は additionalProperties: true なので、
AI評価Score等の追加Metadataは通す（extra="allow"）。
それ以外は additionalProperties: false に合わせて弾く。
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

SCHEMA_VERSION_PATTERN = r"^[0-9]+\.[0-9]+$"
OPAQUE_ID_PATTERN = r"^[A-Za-z0-9._:-]+$"

OpaqueId = Annotated[str, Field(min_length=1, max_length=128, pattern=OPAQUE_ID_PATTERN)]
Label = Annotated[str, Field(min_length=1, max_length=64)]
AssetMimeType = Literal["image/png", "image/jpeg", "image/webp"]


class ContractModel(BaseModel):
    """contracts/ 由来のcamelCaseをそのまま読み書きする。"""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


class OpenContractModel(ContractModel):
    """Schemaが additionalProperties: true を許す位置。"""

    model_config = ConfigDict(extra="allow")


class AssetRef(ContractModel):
    """Binary本体は持たず識別子とMetadataのみ。URLは Asset Manifest 側。"""

    asset_id: OpaqueId
    mime_type: AssetMimeType
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)


class LayerAssetRef(AssetRef):
    """透過Layer Asset。RGBA PNG固定。"""

    mime_type: Literal["image/png"]


class SourcePhoto(ContractModel):
    source_photo_id: OpaqueId
    asset: AssetRef


class ReplacementCandidate(OpenContractModel):
    candidate_id: OpaqueId
    source_photo_id: OpaqueId
    source_layer_id: OpaqueId
    asset: LayerAssetRef
    label: Label


class Layer(OpenContractModel):
    layer_id: OpaqueId
    source_photo_id: OpaqueId
    source_layer_id: OpaqueId
    asset: LayerAssetRef
    label: Label
    #: Layer中心のX。原点はCanvas左上、右方向が正。
    x: float = Field(ge=0, le=1)
    #: Layer中心のY。原点はCanvas左上、下方向が正。
    y: float = Field(ge=0, le=1)
    #: Layer表示幅 / Canvas幅。高さは asset の Aspect Ratio から導出する。
    scale: float = Field(gt=0)
    #: 奥行き順。0が最背面。配列位置とは無関係。
    layer_index: int = Field(ge=0)
    replacement_candidates: list[ReplacementCandidate]


class ArtworkCanvas(ContractModel):
    aspect_ratio: float = Field(gt=0)


class PhysicalOutput(ContractModel):
    """mode表明のみ。mm値等の製造条件は PhysicalOutputConfig 側に置く。"""

    mode: str = Field(min_length=1)


class Artwork(ContractModel):
    schema_version: str = Field(pattern=SCHEMA_VERSION_PATTERN)
    artwork_id: OpaqueId
    canvas: ArtworkCanvas
    #: 可変長。固定5枚の契約にしない。
    source_photos: list[SourcePhoto] = Field(min_length=1)
    #: 可変長。配列位置に前景/中景/背景の意味を持たせない。
    layers: list[Layer] = Field(min_length=1)
    physical_output: PhysicalOutput | None = None
