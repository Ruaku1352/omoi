"""API境界のResponse Model。

生成成功時の最終Resultは **Artwork Data + Asset Manifest**（AGENTS.md §3.3, §4）。
Schemaは `/contracts/generate-success-response.schema.json`。

**外側のKey名（artwork / assetManifest）は【確認待ち：チーム】。**
Drive「技術設計」にまだ定義が無く、この実装に合わせたRepository側の暫定案であり
FIXではない。変わったらSchema / Mock / Frontend型を同時に直す。
`$ref` 先の artwork.schema.json / asset-manifest.schema.json は【FIX】された正本。

同期 / 非同期どちらになっても、この最終成功Resultの形は変えない。
失敗時は `app/errors.py` のError形式であり、本Modelではない。
"""

from __future__ import annotations

from app.models.artwork import Artwork, ContractModel
from app.models.asset_manifest import AssetManifest


class GenerateSuccessResponse(ContractModel):
    artwork: Artwork
    asset_manifest: AssetManifest
