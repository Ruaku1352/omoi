/**
 * POST /api/v1/physical-output/exports
 *
 * 確定Artworkをもとに、Backend(Physical Output)側でSTL ZIPまたは
 * 写真貼り付け用PDFを生成してもらうための呼び出し。
 * STL/PDFの生成ロジック自体はBackend側の責務（AGENTS.md §2.3 / §8）。
 * Frontendは artwork + layers[] が参照するAsset画像一式を渡し、
 * 返ってきたファイルをダウンロードさせるだけ。
 * （印藤さん共有分、#大阪_team-g 2026-09-04スレッド）
 *
 * physicalOutputConfig はBackend側の既定仕様に任せる想定のため、ここでは送らない。
 * mm単位の物理寸法・slot番号・supportMode等はArtwork Dataへ混ぜない（AGENTS.md §8）。
 */
import { apiBaseUrl } from '../config/env'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import type { Artwork, AssetMimeType } from '../types/artwork'
import { toApiError } from './errors'

export type PhysicalOutputFormat = 'stlZip' | 'photoPdf'

const EXT_BY_MIME: Record<AssetMimeType, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
}

const FILE_NAME_BY_FORMAT: Record<PhysicalOutputFormat, string> = {
  stlZip: 'omoi-print-data.zip',
  photoPdf: 'omoi-photo.pdf',
}

export interface ExportPhysicalOutputResult {
  blob: Blob
  fileName: string
}

/** 現在の layers[] が参照している Layer Asset の assetId を、重複なく集める。 */
function collectLayerAssetIds(artwork: Artwork): Map<string, AssetMimeType> {
  const ids = new Map<string, AssetMimeType>()
  for (const layer of artwork.layers) {
    ids.set(layer.asset.assetId, layer.asset.mimeType)
  }
  return ids
}

export async function exportPhysicalOutput(
  artwork: Artwork,
  assets: AssetIndex,
  outputFormat: PhysicalOutputFormat,
): Promise<ExportPhysicalOutputResult> {
  const assetIds = collectLayerAssetIds(artwork)

  // アップロードするファイル名は assetId.拡張子（拡張子を除いた名前が Asset ID と一致する形）
  const assetFiles = await Promise.all(
    Array.from(assetIds, async ([assetId, mimeType]) => {
      const url = resolveAssetUrl(assets, assetId)
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error(`Assetの取得に失敗しました: ${assetId}`)
      }
      const blob = await res.blob()
      const ext = EXT_BY_MIME[mimeType]
      return new File([blob], `${assetId}.${ext}`, { type: mimeType })
    }),
  )

  const form = new FormData()
  form.append('artwork', JSON.stringify(artwork))
  for (const file of assetFiles) {
    form.append('assets', file)
  }
  form.append('outputFormat', outputFormat)

  const res = await fetch(`${apiBaseUrl}/api/v1/physical-output/exports`, {
    method: 'POST',
    body: form,
  })
  if (!res.ok) {
    throw await toApiError(res)
  }
  const blob = await res.blob()
  return { blob, fileName: FILE_NAME_BY_FORMAT[outputFormat] }
}