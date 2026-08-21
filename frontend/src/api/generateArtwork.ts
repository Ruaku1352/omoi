/**
 * POST /api/v1/artworks/generate
 *
 * 唯一FIXされている生成Endpoint（AGENTS.md §4）。
 * 成功Resultは Artwork Data + Asset Manifest。同期/非同期どちらになっても
 * 最終成功Resultの形は変わらないので、呼び出し側はこの戻り値だけを見る。
 */

import { apiBaseUrl } from '../config/env'
import type { Artwork } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'
import { ApiError, toApiError } from './errors'

export interface GenerateArtworkResult {
  artwork: Artwork
  assetManifest: AssetManifest
}

export interface GenerateArtworkInput {
  /** 可変長。固定5枚ではない（AGENTS.md §4）。 */
  photos: readonly File[]
  /** 任意。未入力可。 */
  memoryText?: string
  signal?: AbortSignal
}

export async function generateArtwork(
  input: GenerateArtworkInput,
): Promise<GenerateArtworkResult> {
  const form = new FormData()
  for (const photo of input.photos) {
    form.append('photos', photo)
  }
  if (input.memoryText) {
    form.append('memoryText', input.memoryText)
  }

  const response = await fetch(`${apiBaseUrl}/api/v1/artworks/generate`, {
    method: 'POST',
    body: form,
    signal: input.signal,
  })

  if (!response.ok) {
    throw await toApiError(response)
  }

  const result = (await response.json()) as GenerateArtworkResult
  if (!result?.artwork || !result?.assetManifest) {
    throw new ApiError({
      code: 'INTERNAL_ERROR',
      message: '作品の生成に失敗しました。もう一度お試しください。',
      retryable: true,
      status: response.status,
    })
  }
  return result
}
