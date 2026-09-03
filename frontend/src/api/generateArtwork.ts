/**
 * POST /api/v1/artworks/generate
 *
 * 唯一FIXされている生成Endpoint（AGENTS.md §4）。
 * 成功Resultは Artwork Data + Asset Manifest。Schema正本は
 * `/contracts/generate-success-response.schema.json`【FIX】（技術設計 §14.2）。
 * 同期/非同期どちらになっても最終成功Resultの形は変わらないので、
 * 呼び出し側はこの戻り値だけを見る。
 */

import { apiBaseUrl } from '../config/env'
import type { GenerateSuccessResponse } from '../types/generateResponse'
import type { JobStage, JobStatusResponse } from '../types/job'
import { ApiError, toApiError } from './errors'

export type { GenerateSuccessResponse }

export interface GenerateArtworkInput {
  photos: readonly File[]
  memoryText?: string
  signal?: AbortSignal
  /** Job の状態が変わるたびに呼ばれる。ローディング表示の切り替えに使う。 */
  onProgress?: (progress: { status: 'pending' | 'processing'; stage?: JobStage }) => void
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export async function generateArtwork(
  input: GenerateArtworkInput,
): Promise<GenerateSuccessResponse> {
  const form = new FormData()
  for (const photo of input.photos) {
    form.append('photos', photo)
  }
  if (input.memoryText) {
    form.append('memoryText', input.memoryText)
  }

  // ① まず生成を「予約」する。返ってくるのは jobId だけ
  const startResponse = await fetch(`${apiBaseUrl}/api/v1/artworks/generate`, {
    method: 'POST',
    body: form,
    signal: input.signal,
  })

  if (!startResponse.ok) {
    throw await toApiError(startResponse)
  }

  const { jobId } = (await startResponse.json()) as { jobId: string }

  // ② 完了か失敗になるまで、2秒おきに様子を見に行く
  while (true) {
    await sleep(2000)

    const jobResponse = await fetch(`${apiBaseUrl}/api/v1/jobs/${jobId}`, {
      signal: input.signal,
    })

    if (!jobResponse.ok) {
      throw await toApiError(jobResponse)
    }

    const data = (await jobResponse.json()) as JobStatusResponse

    if (data.status === 'completed') {
      return data.result
    }

    if (data.status === 'failed') {
      throw new ApiError({
        code: data.error.code,
        message: data.error.message,
        retryable: data.error.retryable,
        status: jobResponse.status,
        details: data.error.details,
      })
    }

    // ここに来たら pending か processing。状態を呼び出し側へ伝えて、もう一度待つ
    input.onProgress?.({
      status: data.status,
      stage: data.status === 'processing' ? data.stage : undefined,
    })
  }
}
