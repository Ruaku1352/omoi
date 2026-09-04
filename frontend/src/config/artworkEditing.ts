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

/**
 * scale の上限。【PoC後FIX】
 *
 * Canvas幅を超える大きさにしても物理作品の土台へ載らないため、既定値は 1（Canvas幅と同じ）。
 * 2026-09-04、まなみん指摘（2D編集でありえない大きさまで拡大できてしまう）を受けて 2 から変更。
 */
export const maxScale = numberFromEnv(import.meta.env.VITE_MAX_SCALE, 1)

/**
 * Layerの四辺をCanvasの外へどれだけ出してよいか。Canvas幅・高さに対する比率。【PoC後FIX】
 *
 * 0 なら「Layer全体が必ずCanvas内」。0.1 なら上下左右へ10%分まではみ出せる。
 * 土台へ載らない位置までLayerを動かせてしまうのを防ぐための制限
 * （2026-09-04、まなみん指摘）。値はここだけで管理し、Componentへ散らさない。
 */
export const maxOutOfCanvasRatio = numberFromEnv(import.meta.env.VITE_MAX_OUT_OF_CANVAS, 0)

/** 3D Preview の Layer 間隔。表示値であって物理厚みではない。【PoC後FIX】 */
export const previewDepthStep = numberFromEnv(import.meta.env.VITE_PREVIEW_DEPTH_STEP, 0.02)


/** 3D Preview の Layer 1枚の見かけの厚み。表示値であって物理厚みではない。【PoC後FIX】 */
export const previewLayerThickness = numberFromEnv(
  import.meta.env.VITE_PREVIEW_LAYER_THICKNESS,
  0.01,
)

/** 厚みを何枚の板で表現するか。多いほど滑らかだが描画は重くなる。 */
export const previewLayerSheets = 5

export function clampScale(scale: number): number {
  return Math.min(maxScale, Math.max(minScale, scale))
}