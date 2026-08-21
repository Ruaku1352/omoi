/**
 * 共通Mock（`/contracts/mock/artwork.json`）を Fixture にした契約側の回帰テスト。
 * Real生成結果も同じSchemaを満たすことが接続条件なので、ここはMock専用の分岐を持たない。
 */

import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import type { Artwork } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'
import type { GenerateSuccessResponse } from '../types/generateResponse'
import { buildAssetIndex, resolveAssetUrl } from './assetIndex'
import { fromLayerRectPx, layerHeightRatio, toLayerPlane, toLayerRectPx } from './geometry'
import { normalizeLayerIndexes, sortByLayerIndex } from './layerOrder'

function readMock<T>(name: string): T {
  return JSON.parse(
    readFileSync(fileURLToPath(new URL(`../../../contracts/mock/${name}`, import.meta.url)), 'utf-8'),
  ) as T
}

const mockPath = fileURLToPath(new URL('../../../contracts/mock/artwork.json', import.meta.url))
const artwork = readMock<Artwork>('artwork.json')

describe('共通Mockの前提', () => {
  it('可変長として読む（長さを決め打ちしない）', () => {
    expect(artwork.sourcePhotos.length).toBeGreaterThan(0)
    expect(artwork.layers.length).toBeGreaterThan(0)
  })

  it('layerIndex は 0..N-1 の重複なし連番', () => {
    const indexes = sortByLayerIndex(artwork.layers).map((l) => l.layerIndex)
    expect(indexes).toEqual(artwork.layers.map((_, i) => i))
  })

  it('Artwork Data に URL も rotation も持たない', () => {
    const raw = readFileSync(mockPath, 'utf-8')
    expect(raw).not.toContain('"url"')
    expect(raw).not.toContain('"rotation"')
  })
})

describe('layerOrder', () => {
  it('配列位置ではなく layerIndex で並べる', () => {
    const shuffled = [...artwork.layers].reverse()
    expect(sortByLayerIndex(shuffled).map((l) => l.layerId)).toEqual(
      sortByLayerIndex(artwork.layers).map((l) => l.layerId),
    )
  })

  it('前後変更後に 0..N-1 へ再正規化する', () => {
    const moved = artwork.layers.map((l) =>
      l.layerIndex === 0 ? { ...l, layerIndex: 99 } : l,
    )
    const normalized = normalizeLayerIndexes(moved)
    expect(normalized.map((l) => l.layerIndex)).toEqual(normalized.map((_, i) => i))
    expect(normalized.at(-1)?.layerId).toBe(artwork.layers[0].layerId)
  })
})

describe('geometry', () => {
  const layer = artwork.layers[1]

  it('高さは asset の Aspect Ratio から導出する', () => {
    expect(layerHeightRatio(layer)).toBeCloseTo(
      (layer.scale * layer.asset.heightPx) / layer.asset.widthPx,
    )
  })

  it('3D変換は AGENTS.md §7 の式どおり', () => {
    const plane = toLayerPlane(layer, artwork.canvas, 0.02)
    expect(plane.x3d).toBeCloseTo(layer.x - 0.5)
    expect(plane.y3d).toBeCloseTo((0.5 - layer.y) * (1 / artwork.canvas.aspectRatio))
    expect(plane.z).toBeCloseTo(layer.layerIndex * 0.02)
  })

  it('Pixel変換は往復して正規化値へ戻る', () => {
    const stageWidth = 800
    const stageHeight = stageWidth / artwork.canvas.aspectRatio
    const rect = toLayerRectPx(layer, stageWidth, stageHeight)
    const back = fromLayerRectPx(rect, stageWidth, stageHeight, layer)
    expect(back.x).toBeCloseTo(layer.x)
    expect(back.y).toBeCloseTo(layer.y)
    expect(back.scale).toBeCloseTo(layer.scale)
  })
})

describe('生成成功Response（contracts/generate-success-response.schema.json）', () => {
  const response = readMock<GenerateSuccessResponse>('generate-success-response.json')
  const manifest = readMock<AssetManifest>('asset-manifest.json')

  it('artwork / assetManifest を束ねただけの形', () => {
    expect(Object.keys(response).sort()).toEqual(['artwork', 'assetManifest'])
    expect(response.artwork).toEqual(artwork)
    expect(response.assetManifest).toEqual(manifest)
  })

  it('Artworkが参照する全AssetをManifestが解決できる', () => {
    const index = buildAssetIndex(response.assetManifest)
    for (const layer of response.artwork.layers) {
      expect(() => resolveAssetUrl(index, layer.asset.assetId)).not.toThrow()
      for (const candidate of layer.replacementCandidates) {
        expect(() => resolveAssetUrl(index, candidate.asset.assetId)).not.toThrow()
      }
    }
    for (const photo of response.artwork.sourcePhotos) {
      expect(() => resolveAssetUrl(index, photo.asset.assetId)).not.toThrow()
    }
  })
})

describe('assetIndex', () => {
  it('assetId は Manifest 経由でURLへ解決する', () => {
    const index = buildAssetIndex({
      assets: [
        {
          assetId: artwork.layers[0].asset.assetId,
          url: 'https://example.test/layer-1.png',
          mimeType: 'image/png',
          widthPx: artwork.layers[0].asset.widthPx,
          heightPx: artwork.layers[0].asset.heightPx,
        },
      ],
    })
    expect(resolveAssetUrl(index, artwork.layers[0].asset.assetId)).toBe(
      'https://example.test/layer-1.png',
    )
    expect(() => resolveAssetUrl(index, 'missing-asset')).toThrow()
  })
})
