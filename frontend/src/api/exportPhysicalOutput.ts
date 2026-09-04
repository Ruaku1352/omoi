/**
 * POST /api/v1/physical-output/exports
 *
 * 確定Artworkをもとに、Backend(Physical Output)側でSTL ZIPまたは
 * 写真プリント用データを生成してもらうための呼び出し。
 * STL/写真データの生成ロジック自体はBackend側の責務（AGENTS.md §2.3 / §8）。
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

/** 送信するAsset画像1件分。実際に送るBinaryと、その実寸。 */
interface PreparedAsset {
  file: File
  widthPx: number
  heightPx: number
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
 * 送信用にAsset画像を整える。長辺が `exportMaxAssetDimension` px を超える場合だけ縮小する。
 *
 * AIが返す透過PNGは実寸大のため、数枚まとめて送るとリクエストが上限を超えて
 * 413 Content Too Large になる（2026-09-04、まなみん報告）。
 * 透過（アルファ）を保つ必要があるので再圧縮先は元のMIMEのまま。縦横比も保つ。
 *
 * 戻り値には「実際に送るBinaryの実寸」を含める。Backendは受け取った画像の実寸と
 * artwork.json の `widthPx` / `heightPx` の一致を検証する（不一致だと INVALID_INPUT）ため、
 * 呼び出し側でこの実寸をartwork側へ反映してから送る必要がある。
 * 縮小できない環境・形式のときは元のBlobをそのまま使い、実寸も測れた値をそのまま返す。
 */
async function prepareAsset(
  blob: Blob,
  fileName: string,
  mimeType: AssetMimeType,
  fallbackWidthPx: number,
  fallbackHeightPx: number,
): Promise<PreparedAsset> {
  const asFile = (source: Blob, widthPx: number, heightPx: number): PreparedAsset => ({
    file: new File([source], fileName, { type: mimeType }),
    widthPx,
    heightPx,
  })

  try {
    const bitmap = await createImageBitmap(blob)
    const { width, height } = bitmap

    // 縮小不要ならそのまま。実寸は測れた値を使う（Metadataとのズレもここで吸収される）
    if (exportMaxAssetDimension <= 0 || Math.max(width, height) <= exportMaxAssetDimension) {
      bitmap.close()
      return asFile(blob, width, height)
    }

    const scale = exportMaxAssetDimension / Math.max(width, height)
    const canvas = document.createElement('canvas')
    canvas.width = Math.max(1, Math.round(width * scale))
    canvas.height = Math.max(1, Math.round(height * scale))
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      bitmap.close()
      return asFile(blob, width, height)
    }
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()

    const shrunk = await new Promise<Blob | null>((resolve) => canvas.toBlob(resolve, mimeType))
    // 縮小に失敗した場合や、かえって大きくなった場合は元のまま送る
    if (!shrunk || shrunk.size >= blob.size) return asFile(blob, width, height)
    return asFile(shrunk, canvas.width, canvas.height)
  } catch {
    return asFile(blob, fallbackWidthPx, fallbackHeightPx)
  }
}

export async function exportPhysicalOutput(
  artwork: Artwork,
  assets: AssetIndex,
  outputFormat: PhysicalOutputFormat,
): Promise<ExportPhysicalOutputResult> {
  const assetIds = collectLayerAssetIds(artwork)
  // assetId ごとの「Metadataとして宣言されている実寸」。縮小前のフォールバック用
  const declaredSizes = new Map(
    artwork.layers.map((l) => [
      l.asset.assetId,
      { widthPx: l.asset.widthPx, heightPx: l.asset.heightPx },
    ]),
  )

  // アップロードするファイル名は assetId.拡張子（拡張子を除いた名前が Asset ID と一致する形）
  const prepared = await Promise.all(
    Array.from(assetIds, async ([assetId, mimeType]) => {
      const url = resolveAssetUrl(assets, assetId)
      const res = await fetch(url)
      if (!res.ok) {
        throw new Error(`Assetの取得に失敗しました: ${assetId}`)
      }
      const declared = declaredSizes.get(assetId)
      const ext = EXT_BY_MIME[mimeType]
      const asset = await prepareAsset(
        await res.blob(),
        `${assetId}.${ext}`,
        mimeType,
        declared?.widthPx ?? 0,
        declared?.heightPx ?? 0,
      )
      return [assetId, asset] as const
    }),
  )

  const preparedByAssetId = new Map(prepared)

  // 実際に送る画像の実寸をartwork側へ反映する。
  // Backendは「画像の実寸 == artwork.json の widthPx / heightPx」を検証しており、
  // 縮小した画像に対して元のサイズを宣言したままだと INVALID_INPUT で弾かれる
  // （2026-09-04、実機で確認）。縦横比は保たれ、x / y / scale は正規化値なので
  // レイアウト・実寸変換（AGENTS.md §8）の結果は変わらない。
  // 送信用のコピーだけを書き換え、Frontendが保持するWorking Copyには手を触れない。
  const artworkToSend: Artwork = {
    ...artwork,
    layers: artwork.layers.map((layer) => {
      const asset = preparedByAssetId.get(layer.asset.assetId)
      if (!asset) return layer
      return {
        ...layer,
        asset: { ...layer.asset, widthPx: asset.widthPx, heightPx: asset.heightPx },
      }
    }),
  }

  const form = new FormData()
  form.append('artwork', JSON.stringify(artworkToSend))
  for (const [, asset] of prepared) {
    form.append('assets', asset.file)
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