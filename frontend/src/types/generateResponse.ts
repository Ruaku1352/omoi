/**
 * 生成成功Response の型。Schemaは `/contracts/generate-success-response.schema.json`。
 *
 * `POST /api/v1/artworks/generate` の最終成功Result。
 * Artwork Data と Asset Manifest を束ねるだけの層なので、両者の型はここで再定義せず
 * それぞれの正本写像（`./artwork` / `./assetManifest`）を参照する。
 *
 * **外側のKey名（artwork / assetManifest）は【確認待ち：チーム】。**
 * Drive「技術設計」にまだ定義が無く、Backendが返している形へ合わせた暫定案でFIXではない。
 * 変わったときの影響をここだけに閉じ込めるため、Response型はこのFileにまとめる。
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
