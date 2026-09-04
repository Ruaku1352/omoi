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

/**
 * Physical Output（STL / 写真プリント）へ送るLayer Asset画像の長辺の上限px。【PoC後FIX】
 *
 * AIが返す透過PNGは実寸大（2L判300dpi相当＝2102x1500px級）で、そのまま数枚まとめて
 * multipartで送るとCloud Runのリクエスト上限（32MB）を超えて 413 Content Too Large になる
 * （2026-09-04、まなみん報告）。送信前にこのサイズまで縮小して回避する。
 *
 * 出力物の精細さに影響する値なので、最終的な数値は Physical Output 担当（印藤さん）と
 * 合わせて決める。0 以下にすると縮小しない。
 */
export const exportMaxAssetDimension = numberFromEnv(
  import.meta.env.VITE_EXPORT_MAX_ASSET_DIMENSION,
  1400,
)

/**
 * 3D Preview の Layer 間隔。表示値であって物理厚みではない。【PoC後FIX】
 *
 * 既定値は「実機の土台で隣り合う行の間隔（行中心どうしで約34.35mm）を、
 * 2L判の幅178mmを1.0とした正規化値へ直したときの見た目」に合わせている（34.35 / 178 ≒ 0.193）。
 * 2026-09-04、まなみん指摘（3D Preview上のレイヤー間隔が実物に比べて狭い）を受けて
 * 0.02 から変更した。mm値そのものをここへ持ち込んでいるわけではなく、
 * あくまで見た目を実物へ寄せるための表示値であり、Artwork Dataには一切入らない（AGENTS.md §7）。
 */
export const previewDepthStep = numberFromEnv(import.meta.env.VITE_PREVIEW_DEPTH_STEP, 0.193)


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