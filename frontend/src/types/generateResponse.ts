/**
 * 生成成功Response の型。正本は `/contracts/generate-success-response.schema.json`。
 *
 * `POST /api/v1/artworks/generate` の最終成功Result。
 * Artwork Data と Asset Manifest を束ねるだけの層なので、両者の型はここで再定義せず
 * それぞれの正本写像（`./artwork` / `./assetManifest`）を参照する。
 *
 * 同期 / 非同期どちらの方式になっても、この形は変わらない（AGENTS.md §4）。
 * 失敗時は `../api/errors` の Error形式であり、この型ではない。
 */

import type { Artwork } from './artwork'
import type { AssetManifest } from './assetManifest'

export interface GenerateSuccessResponse {
  artwork: Artwork
  assetManifest: AssetManifest
}
