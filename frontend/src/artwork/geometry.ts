/**
 * 正規化座標（x / y / scale）と描画座標の変換。式の正本は AGENTS.md §7。
 *
 * - `x` / `y` は Layer中心。左上基準の描画APIへ渡すときは幅・高さの半分を引く
 * - `scale` は幅基準。高さは asset の Aspect Ratio から導出する。独立値として持たせない
 * - rotation は扱わない（P0では持たせない）
 */

import type { Artwork, Layer } from '../types/artwork'

/** Layer表示高さ / Canvas幅。scale と同じ「Canvas幅基準」の正規化値。 */
export function layerHeightRatio(layer: Pick<Layer, 'scale' | 'asset'>): number {
  return (layer.scale * layer.asset.heightPx) / layer.asset.widthPx
}

/** 3D Preview 用。Canvas幅を1.0とした座標系へ写す。 */
export interface LayerPlane {
  x3d: number
  y3d: number
  z: number
  width: number
  height: number
}

/**
 * `z` は layerIndex から決定論的に導出する表示値。
 * 物理作品のmm値をここへ混ぜない（AGENTS.md §7）。
 */
export function toLayerPlane(
  layer: Pick<Layer, 'x' | 'y' | 'scale' | 'layerIndex' | 'asset'>,
  canvas: Artwork['canvas'],
  previewDepthStep: number,
): LayerPlane {
  const canvasHeight = 1 / canvas.aspectRatio
  return {
    x3d: layer.x - 0.5,
    y3d: (0.5 - layer.y) * canvasHeight,
    z: layer.layerIndex * previewDepthStep,
    width: layer.scale,
    height: layerHeightRatio(layer),
  }
}

/**
 * Layer全体がCanvas（2L判の出力範囲）に収まる scale の上限。
 *
 * `scale` は幅基準なので、幅は 1.0（Canvas幅）が上限。
 * 高さは asset の Aspect Ratio から導出されるため、縦長のAssetでは
 * 幅が1.0以下でも高さがCanvasからはみ出す。そのぶんも考慮して小さい方を返す。
 * 上限そのもの（`maxScale`）は【PoC後FIX】なので呼び出し側から渡す
 * （AGENTS.md §7: 数値をComponentへ散在させない）。
 */
export function maxScaleWithinCanvas(
  layer: Pick<Layer, 'asset'>,
  canvas: Artwork['canvas'],
  maxScale: number,
): number {
  const canvasHeight = 1 / canvas.aspectRatio
  const heightPerScale = layer.asset.heightPx / layer.asset.widthPx
  const limitByHeight = heightPerScale > 0 ? canvasHeight / heightPerScale : maxScale
  return Math.min(maxScale, 1, limitByHeight)
}
/**
 * Layer全体（中心ではなく四辺）がCanvasの中へ収まるように、中心座標 x / y を丸める。
 *
 * 中心だけをCanvas内に制限すると、Layerの半分までは外へ出せてしまう
 * （2026-09-04、まなみん指摘: 土台からはみ出して見える）。ここでは
 * 「左端 >= 0 かつ 右端 <= 1」「上端 >= 0 かつ 下端 <= 1」を満たす範囲へ収める。
 *
 * `outOfCanvasRatio` は Canvas の外へどれだけはみ出してよいかの許容量（【PoC後FIX】）。
 * 0 なら完全に内側。値は呼び出し側（config/artworkEditing.ts）から渡す。
 */
export function clampLayerCenterWithinCanvas(
  layer: Pick<Layer, 'x' | 'y' | 'scale' | 'asset'>,
  canvas: Artwork['canvas'],
  outOfCanvasRatio: number,
): Pick<Layer, 'x' | 'y'> {
  // x は Canvas幅基準、y は Canvas高さ基準なので、高さ側は aspectRatio をかけて揃える
  const halfWidth = layer.scale / 2
  const halfHeight = (layerHeightRatio(layer) * canvas.aspectRatio) / 2

  const clamp = (value: number, half: number) => {
    const min = half - outOfCanvasRatio
    const max = 1 - half + outOfCanvasRatio
    // Layerが枠より大きい場合に min > max となって破綻しないよう、その時は中央へ寄せる
    if (min > max) return 0.5
    return Math.min(max, Math.max(min, value))
  }

  return {
    x: clamp(layer.x, halfWidth),
    y: clamp(layer.y, halfHeight),
  }
}

/** 2D Edit 用。Pixel座標は描画時のみ生成し、保存時は正規化値へ戻す。 */
export interface LayerRectPx {
  /** 左上基準X。Konva等の描画APIへそのまま渡せる。 */
  leftPx: number
  /** 左上基準Y。 */
  topPx: number
  widthPx: number
  heightPx: number
}

export function toLayerRectPx(
  layer: Pick<Layer, 'x' | 'y' | 'scale' | 'asset'>,
  stageWidth: number,
  stageHeight: number,
): LayerRectPx {
  const widthPx = layer.scale * stageWidth
  const heightPx = layerHeightRatio(layer) * stageWidth
  return {
    leftPx: layer.x * stageWidth - widthPx / 2,
    topPx: layer.y * stageHeight - heightPx / 2,
    widthPx,
    heightPx,
  }
}

/** 描画結果（左上基準Pixel）を保存用の正規化 x / y / scale へ戻す。 */
export function fromLayerRectPx(
  rect: Pick<LayerRectPx, 'leftPx' | 'topPx' | 'widthPx'>,
  stageWidth: number,
  stageHeight: number,
  heightRatioSource: Pick<Layer, 'asset'>,
): Pick<Layer, 'x' | 'y' | 'scale'> {
  const scale = rect.widthPx / stageWidth
  const heightPx =
    (rect.widthPx * heightRatioSource.asset.heightPx) / heightRatioSource.asset.widthPx
  return {
    x: (rect.leftPx + rect.widthPx / 2) / stageWidth,
    y: (rect.topPx + heightPx / 2) / stageHeight,
    scale,
  }
}