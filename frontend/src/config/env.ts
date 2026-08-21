/**
 * 公開可能な設定のみ。`VITE_` Prefix の値は Browser から見える（AGENTS.md §10）。
 * Gemini API Key 等の Secret をここへ持ち込まない。Frontendから直接Geminiを叩かない。
 */

function trimTrailingSlash(url: string): string {
  return url.replace(/\/+$/, '')
}

/** Backend の Base URL。未設定なら同一Originの相対Pathで叩く（Local開発用）。 */
export const apiBaseUrl: string = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL ?? '')

/** 開発・デモ用Modeか。Real処理の失敗時に自動でここへ落ちてはならない。 */
export const useMock: boolean = import.meta.env.VITE_USE_MOCK === 'true'
