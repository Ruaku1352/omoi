/**
 * 確定Artworkを、Physical Output（ナンちゃん）が別Runtimeで受け取れる
 * Portable Artwork Bundle（ZIP）として書き出す（AGENTS.md §8）。
 *
 * 中身は artwork.json（Artwork Dataそのまま、Schemaは変えない）と
 * 参照されている Asset の実Binaryを assets/ 配下に入れるだけ。
 * mm変換・PhysicalOutputConfigはここでは作らない（Physical Output担当の領域）。
 */

import JSZip from 'jszip'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import type { Artwork, AssetMimeType } from '../types/artwork'

const EXT_BY_MIME: Record<AssetMimeType, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
}

/** Artwork内で参照されている assetId を、重複なく全部集める。 */
function collectAssetIds(artwork: Artwork): Map<string, AssetMimeType> {
  const ids = new Map<string, AssetMimeType>()
  for (const photo of artwork.sourcePhotos) {
    ids.set(photo.asset.assetId, photo.asset.mimeType)
  }
  for (const layer of artwork.layers) {
    ids.set(layer.asset.assetId, layer.asset.mimeType)
    for (const candidate of layer.replacementCandidates) {
      ids.set(candidate.asset.assetId, candidate.asset.mimeType)
    }
  }
  return ids
}

export async function buildArtworkBundle(artwork: Artwork, assets: AssetIndex): Promise<Blob> {
  const zip = new JSZip()

  zip.file('artwork.json', JSON.stringify(artwork, null, 2))

  const assetsFolder = zip.folder('assets')
  if (!assetsFolder) throw new Error('assets/ フォルダの作成に失敗しました')

  const assetIds = collectAssetIds(artwork)

  await Promise.all(
    Array.from(assetIds, async ([assetId, mimeType]) => {
      const url = resolveAssetUrl(assets, assetId)
      const response = await fetch(url)
      if (!response.ok) {
        throw new Error(`Assetの取得に失敗しました: ${assetId}`)
      }
      const blob = await response.blob()
      const ext = EXT_BY_MIME[mimeType]
      assetsFolder.file(`${assetId}.${ext}`, blob)
    }),
  )

  return zip.generateAsync({ type: 'blob' })
}

/** ZIPをBrowserのダウンロードとして落とす。 */
export async function downloadArtworkBundle(artwork: Artwork, assets: AssetIndex): Promise<void> {
  const blob = await buildArtworkBundle(artwork, assets)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `omoi-artwork-${artwork.artworkId}.zip`
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}