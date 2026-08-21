/**
 * 共通Mock（`/contracts/mock/artwork.json` + `/contracts/assets/`）の読み込み。
 *
 * **開発中の動作確認用。** Real APIの失敗時にここへ落ちる経路を作らないこと（AGENTS.md §9・§11-12）。
 * 正本を `frontend/` 配下へコピーせず、常に Repository Root の `contracts/` を直接参照する。
 *
 * Artwork Data は URL を持たないので、表示に必要な `assetId` → URL は
 * Real と同じく **Asset Manifest 経由**で解決する。ここではその Manifest を
 * Vite の静的解決（`import.meta.glob`）で組み立てているだけで、
 * 消費側から見た形は Backend が返す Asset Manifest と同一。
 */

import rawArtwork from '../../../contracts/mock/artwork.json'
import type { Artwork, AssetRef } from '../types/artwork'
import type { AssetManifest, AssetManifestEntry } from '../types/assetManifest'

export const mockArtwork = rawArtwork as Artwork

const MIME_BY_EXT: Record<string, AssetManifestEntry['mimeType']> = {
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
}

const assetUrls = import.meta.glob('../../../contracts/assets/*', {
  eager: true,
  query: '?url',
  import: 'default',
}) as Record<string, string>

function assetMetadata(artwork: Artwork): Map<string, Omit<AssetManifestEntry, 'url'>> {
  const entries = new Map<string, Omit<AssetManifestEntry, 'url'>>()
  const add = (asset: AssetRef) => {
    entries.set(asset.assetId, {
      assetId: asset.assetId,
      mimeType: asset.mimeType,
      widthPx: asset.widthPx,
      heightPx: asset.heightPx,
    })
  }
  for (const photo of artwork.sourcePhotos) add(photo.asset)
  for (const layer of artwork.layers) {
    add(layer.asset)
    for (const candidate of layer.replacementCandidates) add(candidate.asset)
  }
  return entries
}

/** 共通MockのAssetを、Backendが返すのと同じ形の Asset Manifest として組み立てる。 */
export function buildMockAssetManifest(artwork: Artwork = mockArtwork): AssetManifest {
  const metadata = assetMetadata(artwork)
  const assets: AssetManifestEntry[] = []

  for (const [path, url] of Object.entries(assetUrls)) {
    const filename = path.split('/').pop() ?? ''
    const dot = filename.lastIndexOf('.')
    const assetId = filename.slice(0, dot)
    const mimeType = MIME_BY_EXT[filename.slice(dot + 1).toLowerCase()]
    const known = metadata.get(assetId)
    if (!known || !mimeType) continue
    assets.push({ ...known, mimeType, url })
  }

  return { assets }
}
