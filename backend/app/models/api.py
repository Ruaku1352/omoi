"""API境界のResponse Model。

生成成功時の最終Resultは **Artwork Data + Asset Manifest**（AGENTS.md §3.3, §4）。
同期 / 非同期どちらになっても、この最終成功Resultの形は変えない。
"""

from __future__ import annotations

from app.models.artwork import Artwork, ContractModel
from app.models.asset_manifest import AssetManifest


class GenerateArtworkResponse(ContractModel):
    artwork: Artwork
    asset_manifest: AssetManifest
