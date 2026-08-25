"""API境界のResponse Model。

生成成功時の最終Resultは **Artwork Data + Asset Manifest**（AGENTS.md §3.3, §4）。
Schema正本は `/contracts/generate-success-response.schema.json`【FIX】（技術設計 §14.2）。
ここはその写像であって別の正本ではない。

外側のKeyは `artwork` / `assetManifest`【FIX】。
**P0では `data` 等の追加Envelopeを設けない**【FIX】。

同期 / 非同期どちらになっても、この最終成功Resultの形は変えない。
失敗時は `app/errors.py` のError形式であり、本Modelではない。
"""

from __future__ import annotations

from app.models.artwork import Artwork, ContractModel
from app.models.asset_manifest import AssetManifest


class GenerateSuccessResponse(ContractModel):
    artwork: Artwork
    asset_manifest: AssetManifest
