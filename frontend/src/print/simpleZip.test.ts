import { describe, expect, it } from 'vitest'
import { createStoredZipBlob } from './simpleZip'

describe('createStoredZipBlob', () => {
  it('複数ファイルをZIP Blobにまとめる', async () => {
    const zip = createStoredZipBlob([
      { path: 'parts/sample.stl', data: 'solid sample\nendsolid sample\n' },
      { path: 'print-report.json', data: '{"ok":true}\n' },
    ])

    const bytes = new Uint8Array(await zip.arrayBuffer())
    expect(zip.type).toBe('application/zip')
    expect(bytes[0]).toBe(0x50)
    expect(bytes[1]).toBe(0x4b)
    expect(zip.size).toBeGreaterThan(100)
  })
})
