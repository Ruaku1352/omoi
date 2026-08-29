import { describe, expect, it } from 'vitest'
import { defaultBrowserFlatPrintConfig, testOnly } from './flatPrint'

describe('browser flat print support bridges', () => {
  it('離れた塊を低い支えで接続する', () => {
    const width = 9
    const height = 5
    const heights = new Float32Array(width * height)
    heights[2 * width + 1] = 1.6
    heights[2 * width + 7] = 1.6

    const before = testOnly.findHeightComponents(heights, width, height)
    expect(before.components).toHaveLength(2)

    const report = testOnly.connectFloatingComponents(heights, width, height, {
      cellSizeMm: 1,
      supportBridgeWidthMm: 1,
      supportBridgeHeightMm: 0.8,
    })

    const after = testOnly.findHeightComponents(heights, width, height)
    expect(report.supportBridgeCount).toBe(1)
    expect(after.components).toHaveLength(1)
    expect(Array.from(heights).some((heightMm) => heightMm > 0 && heightMm < 1.6)).toBe(true)
  })
})

describe('browser flat print STL helpers', () => {
  it('4層3穴の土台STLを作れる', () => {
    const config = defaultBrowserFlatPrintConfig
    const base = testOnly.createBaseHeightMap(config, 4)
    const stl = testOnly.heightMapToStl(
      'flat-parts-grid-base',
      base.heights,
      base.widthCells,
      base.heightCells,
      config.baseCellSizeMm,
    )

    expect(base.report.layerCapacity).toBe(4)
    expect(base.report.slotsPerLayer).toBe(3)
    expect(stl.triangleCount).toBeGreaterThan(0)
    expect(stl.stl).toContain('solid flat-parts-grid-base')
  })
})
