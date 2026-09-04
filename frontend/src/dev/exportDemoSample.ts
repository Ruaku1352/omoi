/**
 * 今画面に読み込まれているArtwork(`artwork` + `assets`)を、
 * `public/demo/` にそのまま置ける形のZIPとして書き出すための開発用ヘルパー。
 *
 * 「サンプル作品を見る」ボタン(App.tsx)が読みに行く形式
 *   - public/demo/artwork.json
 *   - public/demo/assets/<assetId>.<ext>
 * と全く同じ構造でZIPを作る。ダウンロードしたZIPを展開して
 * frontend/public/demo/ の中身をそのまま置き換えれば、サンプル作品を差し替えられる。
 *
 * P0のProduct機能ではなく、サンプル作品を用意する担当(まなみん)がローカルで使う
 * 運用ツール。Artwork Dataのcamelcase Schemaや assetId 命名規則はそのまま踏襲し、
 * 独自Fieldの追加はしない(AGENTS.md §3, §9)。
 */
import { createStoredZipBlob, type ZipFileInput } from '../print/simpleZip'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import type { Artwork, AssetMimeType } from '../types/artwork'

const EXT_BY_MIME: Record<AssetMimeType, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
}

/**
 * サンプル作品ローダー(App.tsx)と同じ範囲でAssetを集める。
 * layers[] の asset と、その replacementCandidates[] の asset のみ。
 * sourcePhotos[] はサンプル表示側で使っていないためここでも含めない。
 */
function collectAssetIds(artwork: Artwork): Map<string, AssetMimeType> {
  const ids = new Map<string, AssetMimeType>()
  for (const layer of artwork.layers) {
    ids.set(layer.asset.assetId, layer.asset.mimeType)
    for (const candidate of layer.replacementCandidates ?? []) {
      ids.set(candidate.asset.assetId, candidate.asset.mimeType)
    }
  }
  return ids
}

export async function buildDemoSampleZip(artwork: Artwork, assets: AssetIndex): Promise<Blob> {
  const assetIds = collectAssetIds(artwork)

  const assetFiles: ZipFileInput[] = await Promise.all(
    Array.from(assetIds, async ([assetId, mimeType]) => {
      const url = resolveAssetUrl(assets, assetId)
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error(`Assetの取得に失敗しました: ${assetId}`)
      }
      const bytes = new Uint8Array(await res.arrayBuffer())
      const ext = EXT_BY_MIME[mimeType]
      return { path: `assets/${assetId}.${ext}`, data: bytes }
    }),
  )

  const files: ZipFileInput[] = [
    { path: 'artwork.json', data: JSON.stringify(artwork, null, 2) },
    ...assetFiles,
  ]

  return createStoredZipBlob(files)
}