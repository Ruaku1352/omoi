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
import { exportMaxAssetDimension } from '../config/artworkEditing'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import type { Artwork, AssetMimeType } from '../types/artwork'
import { toApiError } from './errors'

export type PhysicalOutputFormat = 'stlZip' | 'photoPdf' | 'photoJpegZip'

const EXT_BY_MIME: Record<AssetMimeType, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
}

const FILE_NAME_BY_FORMAT: Record<PhysicalOutputFormat, string> = {
  stlZip: 'omoi-print-data.zip',
  photoPdf: 'omoi-photo.pdf',
  // コンビニ2L写真プリント用のJPEG一式（背景Layerも含む）。
  // Backend側で既に対応済み（印藤さん共有分、#大阪_team-g PR #9）。
  photoJpegZip: 'omoi-photo-jpeg.zip',
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

/**
 * Layer Asset画像が大きすぎる場合に、長辺 `exportMaxAssetDimension` px まで縮小する。
 *
 * AIが返す透過PNGは実寸大のため、数枚まとめて送るとリクエストが上限を超えて
 * 413 Content Too Large になる（2026-09-04、まなみん報告）。
 * 透過（アルファ）を保つ必要があるので再圧縮先はPNGのまま。縦横比も保つので、
 * Artwork Data 側の x / y / scale（正規化値）や Asset の Aspect Ratio との整合は崩れない。
 * 縮小できない環境・形式のときは元のBlobをそのまま返す。
 */
async function shrinkIfNeeded(blob: Blob, mimeType: AssetMimeType): Promise<Blob> {
  if (exportMaxAssetDimension <= 0) return blob

  try {
    const bitmap = await createImageBitmap(blob)
    const { width, height } = bitmap
    if (Math.max(width, height) <= exportMaxAssetDimension) {
      bitmap.close()
      return blob
    }

    const scale = exportMaxAssetDimension / Math.max(width, height)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      bitmap.close()
      return blob
    }
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()

    const shrunk = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, mimeType),
    )
    // 縮小に失敗した場合や、かえって大きくなった場合は元のまま送る
    if (!shrunk || shrunk.size >= blob.size) return blob
    return shrunk
  } catch {
    return blob
  }
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
      const blob = await shrinkIfNeeded(await res.blob(), mimeType)
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