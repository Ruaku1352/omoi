/**
 * Backend の Error形式。正本は AGENTS.md §4。
 * code は UPPER_SNAKE_CASE。message はそのままユーザーへ出せる日本語文言。
 */

export interface ApiErrorBody {
  error: {
    code: string
    message: string
    retryable: boolean
    details: unknown
  }
}

export class ApiError extends Error {
  readonly code: string
  readonly retryable: boolean
  readonly status: number
  readonly details: unknown

  constructor(params: {
    code: string
    message: string
    retryable: boolean
    status: number
    details?: unknown
  }) {
    super(params.message)
    this.name = 'ApiError'
    this.code = params.code
    this.retryable = params.retryable
    this.status = params.status
    this.details = params.details ?? null
  }
}

function isApiErrorBody(value: unknown): value is ApiErrorBody {
  if (typeof value !== 'object' || value === null) return false
  const error = (value as { error?: unknown }).error
  if (typeof error !== 'object' || error === null) return false
  return typeof (error as { code?: unknown }).code === 'string'
}

/** 契約通りのError Bodyならそれを使い、そうでなければ内部情報を出さない形へ寄せる。 */
export async function toApiError(response: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await response.json()
  } catch {
    body = null
  }

  if (isApiErrorBody(body)) {
    return new ApiError({
      code: body.error.code,
      message: body.error.message,
      retryable: Boolean(body.error.retryable),
      status: response.status,
      details: body.error.details,
    })
  }

  return new ApiError({
    code: 'INTERNAL_ERROR',
    message: '作品の生成に失敗しました。もう一度お試しください。',
    retryable: response.status >= 500,
    status: response.status,
  })
}
