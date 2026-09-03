/**
 * POST /api/v1/artworks/generate → GET /api/v1/jobs/{jobId}
 *
 * 生成は非同期。POST は 202 + jobId を返すだけで、結果は Job Endpoint から取る。
 * Schema正本は `/contracts/generate-accepted-response.schema.json` と
 * `/contracts/job-status-response.schema.json`（技術設計 §14.2）。
 * 呼び出し側は最終的な生成成功Resultだけを受け取る。
 */
import { apiBaseUrl } from '../config/env'
import type { GenerateSuccessResponse } from '../types/generateResponse'
import type { JobStage, JobStatusResponse } from '../types/job'
import { ApiError, toApiError } from './errors'

export type { GenerateSuccessResponse }

/** Polling間隔。Frontend / Backend で合わせている。 */
const POLL_INTERVAL_MS = 2000

/**
 * Polling を打ち切るまでの上限。
 * Cloud Run の Request Timeout（600秒）に合わせている。
 * これを超えるのは Backend 側が応答しなくなった場合なので、
 * 画面を待たせ続けずエラーにする。
 */
const POLL_TIMEOUT_MS = 600_000

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
  const deadline = Date.now() + POLL_TIMEOUT_MS
  while (true) {
    if (Date.now() > deadline) {
      throw new ApiError({
        code: 'POLL_TIMEOUT',
        message: '生成に時間がかかりすぎています。もう一度お試しください。',
        retryable: true,
        status: 504,
        details: { jobId },
      })
    }

    await sleep(POLL_INTERVAL_MS)

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
