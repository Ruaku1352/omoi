/**
 * layerIndex の扱い。`layers[]` の配列位置を奥行き順と解釈しない（AGENTS.md §3.2）。
 */

import type { Layer } from '../types/artwork'

/** 描画前に layerIndex 昇順（0が最背面）へ並べる。元配列は変更しない。 */
export function sortByLayerIndex<T extends Pick<Layer, 'layerIndex'>>(layers: readonly T[]): T[] {
  return [...layers].sort((a, b) => a.layerIndex - b.layerIndex)
}

/**
 * 前後変更後に layerIndex を 0..N-1 の重複なし連番へ再正規化する。
 * 前後変更は配列位置ではなく layerIndex の変更として扱う。
 */
export function normalizeLayerIndexes<T extends Pick<Layer, 'layerIndex'>>(
  layers: readonly T[],
): T[] {
  const ordered = sortByLayerIndex(layers)
  return ordered.map((layer, i) => (layer.layerIndex === i ? layer : { ...layer, layerIndex: i }))
}
