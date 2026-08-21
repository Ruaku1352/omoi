/**
 * assetId → URL の解決。Artwork Data 内にURLを期待しない（AGENTS.md §3.3）。
 */

import type { AssetManifest, AssetManifestEntry } from '../types/assetManifest'

export type AssetIndex = ReadonlyMap<string, AssetManifestEntry>

export function buildAssetIndex(manifest: AssetManifest): AssetIndex {
  return new Map(manifest.assets.map((a) => [a.assetId, a]))
}

/**
 * 解決できない assetId は握り潰さない。
 * Assetが欠けたArtworkを成功扱いしないため（AGENTS.md §9）。
 */
export function resolveAssetUrl(index: AssetIndex, assetId: string): string {
  const entry = index.get(assetId)
  if (!entry) {
    throw new Error(`Asset Manifest に assetId '${assetId}' が無い`)
  }
  return entry.url
}
