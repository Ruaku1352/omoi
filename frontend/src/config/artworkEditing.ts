/**
 * 2D Edit / 3D Preview の表示・操作パラメータ。
 *
 * ここにある値は【PoC後FIX】。確定値ではないので、各Componentへ数値を散在させず
 * 必ずこのModuleを参照する（AGENTS.md §7, §11-8）。上書きは環境変数で行う。
 *
 * いずれも Artwork Data には保存しない表示側の都合であり、
 * 物理作品のmm値とも無関係（mm値は PhysicalOutputConfig 側の責務）。
 */

function numberFromEnv(raw: string | undefined, fallback: number): number {
  if (raw === undefined || raw === '') return fallback
  const parsed = Number(raw)
  return Number.isFinite(parsed) ? parsed : fallback
}

/** scale の下限。【PoC後FIX】 */
export const minScale = numberFromEnv(import.meta.env.VITE_MIN_SCALE, 0.05)

/** scale の上限。【PoC後FIX】 */
export const maxScale = numberFromEnv(import.meta.env.VITE_MAX_SCALE, 2)

/** 3D Preview の Layer 間隔。表示値であって物理厚みではない。【PoC後FIX】 */
export const previewDepthStep = numberFromEnv(import.meta.env.VITE_PREVIEW_DEPTH_STEP, 0.02)

export function clampScale(scale: number): number {
  return Math.min(maxScale, Math.max(minScale, scale))
}
