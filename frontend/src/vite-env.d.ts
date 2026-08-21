/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Backend(Cloud Run) の Base URL。末尾スラッシュ有無どちらでもよい。 */
  readonly VITE_API_BASE_URL?: string
  /** 開発専用Flag。Real AI失敗時の隠れFallbackには使わない（AGENTS.md §9）。 */
  readonly VITE_USE_MOCK?: string
  /** 【PoC後FIX】暫定値の上書き用。確定値をコードへ散在させないための逃がし先。 */
  readonly VITE_MIN_SCALE?: string
  readonly VITE_MAX_SCALE?: string
  readonly VITE_PREVIEW_DEPTH_STEP?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
