"""Asset Manifest の Pydantic Model。正本は `/contracts/asset-manifest.schema.json`。"""

from __future__ import annotations

from pydantic import Field

from app.models.artwork import AssetMimeType, ContractModel, OpaqueId


class AssetManifestEntry(ContractModel):
    model_config = ContractModel.model_config | {"extra": "allow"}

    asset_id: OpaqueId
    #: Browser から取得可能なURL。http(s) / blob: を想定。
    url: str = Field(min_length=1)
    mime_type: AssetMimeType
    width_px: int = Field(ge=1)
    height_px: int = Field(ge=1)


class AssetManifest(ContractModel):
    assets: list[AssetManifestEntry] = Field(min_length=1)
