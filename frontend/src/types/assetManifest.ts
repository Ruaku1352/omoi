/**
 * Asset Manifest の型。正本は `/contracts/asset-manifest.schema.json`。
 *
 * assetId を Browser から取得可能な url へ解決するための分離レイヤー。
 * Artwork Data 本体へ Runtime依存URLを埋め込まないための境界（AGENTS.md §3.3）。
 */

import type { AssetMimeType } from './artwork'

export interface AssetManifestEntry {
  assetId: string
  /** Browser から取得可能なURL。http(s) / blob: を想定。 */
  url: string
  mimeType: AssetMimeType
  widthPx: number
  heightPx: number
}

export interface AssetManifest {
  assets: AssetManifestEntry[]
}
