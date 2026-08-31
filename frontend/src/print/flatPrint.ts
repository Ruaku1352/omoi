import { buildAssetIndex, resolveAssetUrl } from '../artwork/assetIndex'
import { sortByLayerIndex } from '../artwork/layerOrder'
import type { Artwork, Layer } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'
import { createStoredZipBlob, type ZipFileInput } from './simpleZip'

export interface BrowserFlatPrintConfig {
  targetWidthMm: number
  partThicknessMm: number
  cellSizeMm: number
  alphaThreshold: number
  outlineMarginMm: number
  supportBridgeWidthMm: number
  supportBridgeHeightMm: number
  tabWidthMm: number
  tabHeightMm: number
  tabStemWidthMm: number
  baseWidthMm: number
  baseDepthMm: number
  baseHeightMm: number
  baseLayerCapacity: number
  baseSlotsPerLayer: number
  baseCellSizeMm: number
  baseFrontMarginMm: number
  baseBackMarginMm: number
  slotClearanceMm: number
  slotSideClearanceMm: number
}

export const defaultBrowserFlatPrintConfig: BrowserFlatPrintConfig = {
  targetWidthMm: 120,
  partThicknessMm: 1.6,
  cellSizeMm: 0.6,
  alphaThreshold: 16,
  outlineMarginMm: 0.35,
  supportBridgeWidthMm: 1.8,
  supportBridgeHeightMm: 0.8,
  tabWidthMm: 12,
  tabHeightMm: 5,
  tabStemWidthMm: 3.2,
  baseWidthMm: 170,
  baseDepthMm: 121,
  baseHeightMm: 5,
  baseLayerCapacity: 4,
  baseSlotsPerLayer: 3,
  baseCellSizeMm: 1,
  baseFrontMarginMm: 8,
  baseBackMarginMm: 20,
  slotClearanceMm: 0.35,
  slotSideClearanceMm: 0.8,
}

interface Component {
  id: number
  cells: number[]
  minX: number
  maxX: number
  minY: number
  maxY: number
}

interface ComponentResult {
  components: Component[]
  labels: Int32Array
}

interface HeightMapBuild {
  heights: Float32Array
  widthCells: number
  heightCells: number
  cellSizeMm: number
  contentWidthMm: number
  contentHeightMm: number
  supportBridgeCount: number
  floatingComponentCount: number
  originalComponentCount: number
}

export interface BrowserFlatPrintPartReport {
  layerId: string
  layerIndex: number
  label: string
  fileName: string
  widthMm: number
  heightMm: number
  triangleCount: number
  originalComponentCount: number
  floatingComponentCount: number
  supportBridgeCount: number
}

export interface BrowserFlatPrintBaseReport {
  fileName: string
  widthMm: number
  depthMm: number
  heightMm: number
  triangleCount: number
  layerCapacity: number
  slotsPerLayer: number
}

export interface BrowserFlatPrintReport {
  artworkId: string
  config: BrowserFlatPrintConfig
  parts: BrowserFlatPrintPartReport[]
  base: BrowserFlatPrintBaseReport
  warnings: string[]
}

export interface BrowserFlatPrintPackage {
  blob: Blob
  fileName: string
  report: BrowserFlatPrintReport
}

type Triangle = [
  [number, number, number],
  [number, number, number],
  [number, number, number],
]

function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}

function slug(value: string): string {
  const normalized = value.normalize('NFKD').replace(/[\u0300-\u036f]/g, '')
  return normalized.replace(/[^A-Za-z0-9._-]+/g, '-').replace(/^-+|-+$/g, '') || 'part'
}

function indexOf(x: number, y: number, width: number): number {
  return y * width + x
}

function neighbors(index: number, width: number, height: number): number[] {
  const x = index % width
  const y = Math.floor(index / width)
  const result: number[] = []
  if (x > 0) result.push(index - 1)
  if (x < width - 1) result.push(index + 1)
  if (y > 0) result.push(index - width)
  if (y < height - 1) result.push(index + width)
  return result
}

function findHeightComponents(heights: Float32Array, width: number, height: number): ComponentResult {
  const labels = new Int32Array(width * height)
  labels.fill(-1)
  const components: Component[] = []

  for (let start = 0; start < heights.length; start += 1) {
    if (heights[start] <= 0 || labels[start] !== -1) continue

    const id = components.length
    const stack = [start]
    const cells: number[] = []
    labels[start] = id
    let minX = start % width
    let maxX = minX
    let minY = Math.floor(start / width)
    let maxY = minY

    while (stack.length > 0) {
      const current = stack.pop()
      if (current === undefined) break
      cells.push(current)
      const x = current % width
      const y = Math.floor(current / width)
      minX = Math.min(minX, x)
      maxX = Math.max(maxX, x)
      minY = Math.min(minY, y)
      maxY = Math.max(maxY, y)

      for (const next of neighbors(current, width, height)) {
        if (heights[next] <= 0 || labels[next] !== -1) continue
        labels[next] = id
        stack.push(next)
      }
    }

    components.push({ id, cells, minX, maxX, minY, maxY })
  }

  return {
    components: components.sort((a, b) => b.cells.length - a.cells.length),
    labels,
  }
}

function dilateHeights(
  heights: Float32Array,
  width: number,
  height: number,
  radiusCells: number,
  filledHeight: number,
): Float32Array {
  if (radiusCells <= 0) return heights

  const dilated = new Float32Array(heights)
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const source = heights[indexOf(x, y, width)]
      if (source <= 0) continue
      for (let dy = -radiusCells; dy <= radiusCells; dy += 1) {
        for (let dx = -radiusCells; dx <= radiusCells; dx += 1) {
          if (dx * dx + dy * dy > radiusCells * radiusCells) continue
          const nx = x + dx
          const ny = y + dy
          if (nx < 0 || nx >= width || ny < 0 || ny >= height) continue
          const target = indexOf(nx, ny, width)
          dilated[target] = Math.max(dilated[target], filledHeight)
        }
      }
    }
  }
  return dilated
}

function fillDisc(
  heights: Float32Array,
  width: number,
  height: number,
  centerX: number,
  centerY: number,
  radiusCells: number,
  value: number,
): void {
  for (let dy = -radiusCells; dy <= radiusCells; dy += 1) {
    for (let dx = -radiusCells; dx <= radiusCells; dx += 1) {
      if (dx * dx + dy * dy > radiusCells * radiusCells) continue
      const x = centerX + dx
      const y = centerY + dy
      if (x < 0 || x >= width || y < 0 || y >= height) continue
      const target = indexOf(x, y, width)
      heights[target] = Math.max(heights[target], value)
    }
  }
}

function traceBridgePath(
  prev: Int32Array,
  start: number,
  end: number,
): number[] {
  const path = [start]
  let cursor = start
  while (cursor !== end) {
    const next = prev[cursor]
    if (next < 0) break
    cursor = next
    path.push(cursor)
  }
  return path
}

function bridgeComponentToExistingShape(
  heights: Float32Array,
  width: number,
  height: number,
  labels: Int32Array,
  component: Component,
  bridgeWidthCells: number,
  supportHeightMm: number,
): boolean {
  const visited = new Uint8Array(width * height)
  const prev = new Int32Array(width * height)
  prev.fill(-1)
  const queue: number[] = []
  let cursor = 0

  for (const cell of component.cells) {
    visited[cell] = 1
    queue.push(cell)
  }

  while (cursor < queue.length) {
    const current = queue[cursor]
    cursor += 1

    for (const next of neighbors(current, width, height)) {
      if (heights[next] > 0 && labels[next] !== component.id) {
        const path = traceBridgePath(prev, current, component.cells[0])
        for (const cell of path) {
          fillDisc(
            heights,
            width,
            height,
            cell % width,
            Math.floor(cell / width),
            bridgeWidthCells,
            supportHeightMm,
          )
        }
        return true
      }
      if (heights[next] > 0 || visited[next] === 1) continue
      visited[next] = 1
      prev[next] = current
      queue.push(next)
    }
  }

  return false
}

function connectFloatingComponents(
  heights: Float32Array,
  width: number,
  height: number,
  config: Pick<BrowserFlatPrintConfig, 'supportBridgeWidthMm' | 'supportBridgeHeightMm' | 'cellSizeMm'>,
): { originalComponentCount: number; floatingComponentCount: number; supportBridgeCount: number } {
  const { components, labels } = findHeightComponents(heights, width, height)
  const bridgeWidthCells = Math.max(0, Math.floor(config.supportBridgeWidthMm / config.cellSizeMm / 2))
  let supportBridgeCount = 0

  for (const component of components.slice(1)) {
    if (
      bridgeComponentToExistingShape(
        heights,
        width,
        height,
        labels,
        component,
        bridgeWidthCells,
        config.supportBridgeHeightMm,
      )
    ) {
      supportBridgeCount += 1
    }
  }

  return {
    originalComponentCount: components.length,
    floatingComponentCount: Math.max(components.length - 1, 0),
    supportBridgeCount,
  }
}

function findFilledBounds(heights: Float32Array, width: number): Component | null {
  let minX = Number.POSITIVE_INFINITY
  let maxX = Number.NEGATIVE_INFINITY
  let minY = Number.POSITIVE_INFINITY
  let maxY = Number.NEGATIVE_INFINITY
  const cells: number[] = []

  for (let i = 0; i < heights.length; i += 1) {
    if (heights[i] <= 0) continue
    const x = i % width
    const y = Math.floor(i / width)
    cells.push(i)
    minX = Math.min(minX, x)
    maxX = Math.max(maxX, x)
    minY = Math.min(minY, y)
    maxY = Math.max(maxY, y)
  }

  if (cells.length === 0) return null
  return { id: 0, cells, minX, maxX, minY, maxY }
}

function drawThickLine(
  heights: Float32Array,
  width: number,
  height: number,
  fromX: number,
  fromY: number,
  toX: number,
  toY: number,
  radiusCells: number,
  value: number,
): void {
  const steps = Math.max(Math.abs(toX - fromX), Math.abs(toY - fromY), 1)
  for (let i = 0; i <= steps; i += 1) {
    const t = i / steps
    fillDisc(
      heights,
      width,
      height,
      Math.round(fromX + (toX - fromX) * t),
      Math.round(fromY + (toY - fromY) * t),
      radiusCells,
      value,
    )
  }
}

function anchorCellForTab(bounds: Component, tabCenterX: number, width: number): number {
  let best = bounds.cells[0]
  let bestScore = Number.POSITIVE_INFINITY
  for (const cell of bounds.cells) {
    const x = cell % width
    const y = Math.floor(cell / width)
    const score = (bounds.maxY - y) * 8 + Math.abs(x - tabCenterX)
    if (score < bestScore) {
      best = cell
      bestScore = score
    }
  }
  return best
}

function addTabAndStem(
  heights: Float32Array,
  width: number,
  height: number,
  config: Pick<
    BrowserFlatPrintConfig,
    'cellSizeMm' | 'partThicknessMm' | 'tabWidthMm' | 'tabHeightMm' | 'tabStemWidthMm'
  >,
): { heights: Float32Array; width: number; height: number } {
  const bounds = findFilledBounds(heights, width)
  if (!bounds) return { heights, width, height }

  const tabRows = Math.max(1, Math.ceil(config.tabHeightMm / config.cellSizeMm))
  const tabCells = Math.max(1, Math.ceil(config.tabWidthMm / config.cellSizeMm))
  const stemRadius = Math.max(1, Math.floor(config.tabStemWidthMm / config.cellSizeMm / 2))
  const nextHeight = height + tabRows
  const result = new Float32Array(width * nextHeight)

  for (let y = 0; y < height; y += 1) {
    result.set(heights.slice(y * width, y * width + width), y * width)
  }

  const tabCenterX = Math.round((bounds.minX + bounds.maxX) / 2)
  const tabLeft = clamp(Math.round(tabCenterX - tabCells / 2), 0, width - tabCells)
  const tabRight = tabLeft + tabCells

  for (let y = height; y < nextHeight; y += 1) {
    for (let x = tabLeft; x < tabRight; x += 1) {
      result[indexOf(x, y, width)] = config.partThicknessMm
    }
  }

  const anchor = anchorCellForTab(bounds, tabCenterX, width)
  drawThickLine(
    result,
    width,
    nextHeight,
    anchor % width,
    Math.floor(anchor / width),
    tabCenterX,
    height,
    stemRadius,
    config.partThicknessMm,
  )

  return { heights: result, width, height: nextHeight }
}

async function loadImage(url: string): Promise<HTMLImageElement> {
  const image = new Image()
  image.crossOrigin = 'anonymous'
  image.src = url
  await image.decode()
  return image
}

async function heightMapFromLayer(
  layer: Layer,
  url: string,
  config: BrowserFlatPrintConfig,
): Promise<HeightMapBuild> {
  const layerWidthMm = layer.scale * config.targetWidthMm
  const layerHeightMm = (layerWidthMm * layer.asset.heightPx) / layer.asset.widthPx
  const widthCells = clamp(Math.ceil(layerWidthMm / config.cellSizeMm), 4, 420)
  const heightCells = clamp(Math.ceil(layerHeightMm / config.cellSizeMm), 4, 420)
  const image = await loadImage(url)
  const canvas = document.createElement('canvas')
  canvas.width = widthCells
  canvas.height = heightCells
  const context = canvas.getContext('2d', { willReadFrequently: true })
  if (!context) throw new Error('Canvasの2D contextを取得できませんでした')
  context.clearRect(0, 0, widthCells, heightCells)
  context.drawImage(image, 0, 0, widthCells, heightCells)
  const pixels = context.getImageData(0, 0, widthCells, heightCells).data

  let heights = new Float32Array(widthCells * heightCells)
  for (let i = 0; i < widthCells * heightCells; i += 1) {
    if (pixels[i * 4 + 3] >= config.alphaThreshold) heights[i] = config.partThicknessMm
  }

  const marginCells = Math.max(0, Math.ceil(config.outlineMarginMm / config.cellSizeMm))
  heights = new Float32Array(
    dilateHeights(heights, widthCells, heightCells, marginCells, config.partThicknessMm),
  )
  const supportReport = connectFloatingComponents(heights, widthCells, heightCells, config)
  const withTab = addTabAndStem(heights, widthCells, heightCells, config)

  return {
    heights: withTab.heights,
    widthCells: withTab.width,
    heightCells: withTab.height,
    cellSizeMm: config.cellSizeMm,
    contentWidthMm: withTab.width * config.cellSizeMm,
    contentHeightMm: withTab.height * config.cellSizeMm,
    ...supportReport,
  }
}

function normalFor(triangle: Triangle): [number, number, number] {
  const [a, b, c] = triangle
  const ux = b[0] - a[0]
  const uy = b[1] - a[1]
  const uz = b[2] - a[2]
  const vx = c[0] - a[0]
  const vy = c[1] - a[1]
  const vz = c[2] - a[2]
  const nx = uy * vz - uz * vy
  const ny = uz * vx - ux * vz
  const nz = ux * vy - uy * vx
  const length = Math.hypot(nx, ny, nz) || 1
  return [nx / length, ny / length, nz / length]
}

function triangleToFacet(triangle: Triangle): string {
  const normal = normalFor(triangle)
  return [
    `  facet normal ${normal[0].toFixed(6)} ${normal[1].toFixed(6)} ${normal[2].toFixed(6)}`,
    '    outer loop',
    ...triangle.map(
      (vertex) =>
        `      vertex ${vertex[0].toFixed(4)} ${vertex[1].toFixed(4)} ${vertex[2].toFixed(4)}`,
    ),
    '    endloop',
    '  endfacet',
  ].join('\n')
}

function addQuad(
  triangles: Triangle[],
  a: [number, number, number],
  b: [number, number, number],
  c: [number, number, number],
  d: [number, number, number],
): void {
  triangles.push([a, b, c], [a, c, d])
}

function heightAt(heights: Float32Array, width: number, height: number, x: number, y: number): number {
  if (x < 0 || x >= width || y < 0 || y >= height) return 0
  return heights[indexOf(x, y, width)]
}

function heightMapToStl(
  name: string,
  heights: Float32Array,
  width: number,
  height: number,
  cellSizeMm: number,
): { stl: string; triangleCount: number } {
  const triangles: Triangle[] = []
  const widthMm = width * cellSizeMm
  const heightMm = height * cellSizeMm

  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const top = heightAt(heights, width, height, x, y)
      if (top <= 0) continue

      const x0 = x * cellSizeMm - widthMm / 2
      const x1 = x0 + cellSizeMm
      const y0 = y * cellSizeMm - heightMm / 2
      const y1 = y0 + cellSizeMm

      addQuad(triangles, [x0, y0, top], [x1, y0, top], [x1, y1, top], [x0, y1, top])
      addQuad(triangles, [x0, y1, 0], [x1, y1, 0], [x1, y0, 0], [x0, y0, 0])

      const left = heightAt(heights, width, height, x - 1, y)
      const right = heightAt(heights, width, height, x + 1, y)
      const up = heightAt(heights, width, height, x, y - 1)
      const down = heightAt(heights, width, height, x, y + 1)

      if (left < top) addQuad(triangles, [x0, y1, left], [x0, y0, left], [x0, y0, top], [x0, y1, top])
      if (right < top) addQuad(triangles, [x1, y0, right], [x1, y1, right], [x1, y1, top], [x1, y0, top])
      if (up < top) addQuad(triangles, [x0, y0, up], [x1, y0, up], [x1, y0, top], [x0, y0, top])
      if (down < top) addQuad(triangles, [x1, y1, down], [x0, y1, down], [x0, y1, top], [x1, y1, top])
    }
  }

  const facets = triangles.map(triangleToFacet).join('\n')
  return {
    stl: `solid ${name}\n${facets}\nendsolid ${name}\n`,
    triangleCount: triangles.length,
  }
}

function createBaseHeightMap(
  config: BrowserFlatPrintConfig,
  layerCount: number,
): { heights: Float32Array; widthCells: number; heightCells: number; report: BrowserFlatPrintBaseReport } {
  const widthCells = Math.ceil(config.baseWidthMm / config.baseCellSizeMm)
  const heightCells = Math.ceil(config.baseDepthMm / config.baseCellSizeMm)
  const heights = new Float32Array(widthCells * heightCells)
  heights.fill(config.baseHeightMm)

  const slotLengthMm = config.tabWidthMm + config.slotSideClearanceMm
  const slotWidthMm = config.partThicknessMm + config.slotClearanceMm
  const layerCapacity = Math.max(config.baseLayerCapacity, layerCount)
  const xGap = config.baseWidthMm / (config.baseSlotsPerLayer + 1)
  const usableDepthMm =
    config.baseDepthMm -
    config.baseFrontMarginMm -
    config.baseBackMarginMm -
    slotWidthMm * layerCapacity
  const yGap = layerCapacity > 1 ? Math.max(usableDepthMm / (layerCapacity - 1), 2) : 0

  for (let layer = 0; layer < layerCapacity; layer += 1) {
    const slotCenterY =
      config.baseFrontMarginMm + layer * (slotWidthMm + yGap) + slotWidthMm / 2
    for (let slot = 0; slot < config.baseSlotsPerLayer; slot += 1) {
      const slotCenterX = xGap * (slot + 1)
      const x0 = Math.floor((slotCenterX - slotLengthMm / 2) / config.baseCellSizeMm)
      const x1 = Math.ceil((slotCenterX + slotLengthMm / 2) / config.baseCellSizeMm)
      const y0 = Math.floor((slotCenterY - slotWidthMm / 2) / config.baseCellSizeMm)
      const y1 = Math.ceil((slotCenterY + slotWidthMm / 2) / config.baseCellSizeMm)
      for (let y = clamp(y0, 0, heightCells - 1); y <= clamp(y1, 0, heightCells - 1); y += 1) {
        for (let x = clamp(x0, 0, widthCells - 1); x <= clamp(x1, 0, widthCells - 1); x += 1) {
          heights[indexOf(x, y, widthCells)] = 0
        }
      }
    }
  }

  return {
    heights,
    widthCells,
    heightCells,
    report: {
      fileName: 'base/flat-parts-grid-base.stl',
      widthMm: widthCells * config.baseCellSizeMm,
      depthMm: heightCells * config.baseCellSizeMm,
      heightMm: config.baseHeightMm,
      triangleCount: 0,
      layerCapacity,
      slotsPerLayer: config.baseSlotsPerLayer,
    },
  }
}

export async function generateBrowserFlatPrintPackage(
  artwork: Artwork,
  assetManifest: AssetManifest,
  config: BrowserFlatPrintConfig = defaultBrowserFlatPrintConfig,
): Promise<BrowserFlatPrintPackage> {
  const assetIndex = buildAssetIndex(assetManifest)
  const files: ZipFileInput[] = []
  const parts: BrowserFlatPrintPartReport[] = []
  const warnings: string[] = []

  for (const layer of sortByLayerIndex(artwork.layers)) {
    const url = resolveAssetUrl(assetIndex, layer.asset.assetId)
    const heightMap = await heightMapFromLayer(layer, url, config)
    const name = `flat-part-layer-${layer.layerIndex}-${slug(layer.layerId)}`
    const fileName = `parts/${name}.stl`
    const { stl, triangleCount } = heightMapToStl(
      name,
      heightMap.heights,
      heightMap.widthCells,
      heightMap.heightCells,
      heightMap.cellSizeMm,
    )
    files.push({ path: fileName, data: stl })
    parts.push({
      layerId: layer.layerId,
      layerIndex: layer.layerIndex,
      label: layer.label,
      fileName,
      widthMm: Number(heightMap.contentWidthMm.toFixed(2)),
      heightMm: Number(heightMap.contentHeightMm.toFixed(2)),
      triangleCount,
      originalComponentCount: heightMap.originalComponentCount,
      floatingComponentCount: heightMap.floatingComponentCount,
      supportBridgeCount: heightMap.supportBridgeCount,
    })
    if (heightMap.floatingComponentCount > 0 && heightMap.supportBridgeCount === 0) {
      warnings.push(`${layer.label}: 離れた塊を検出したが自動支えを作れなかった`)
    }
    if (heightMap.originalComponentCount >= 4) {
      warnings.push(
        `${layer.label}: 切り抜き済みレイヤーが${heightMap.originalComponentCount}個に分離しているため、AI側のレイヤー生成を再確認する`,
      )
    }
  }

  const baseMap = createBaseHeightMap(config, parts.length)
  const base = heightMapToStl(
    'flat-parts-grid-base',
    baseMap.heights,
    baseMap.widthCells,
    baseMap.heightCells,
    config.baseCellSizeMm,
  )
  const baseReport = { ...baseMap.report, triangleCount: base.triangleCount }
  files.push({ path: baseReport.fileName, data: base.stl })

  const report: BrowserFlatPrintReport = {
    artworkId: artwork.artworkId,
    config,
    parts,
    base: baseReport,
    warnings,
  }
  files.push({ path: 'print-report.json', data: JSON.stringify(report, null, 2) + '\n' })

  return {
    blob: createStoredZipBlob(files),
    fileName: `flat-print-${slug(artwork.artworkId)}.zip`,
    report,
  }
}

export function downloadBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = fileName
  anchor.click()
  URL.revokeObjectURL(url)
}

export const testOnly = {
  connectFloatingComponents,
  createBaseHeightMap,
  findHeightComponents,
  heightMapToStl,
}
