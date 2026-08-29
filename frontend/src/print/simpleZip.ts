export interface ZipFileInput {
  path: string
  data: string | Uint8Array
  modifiedAt?: Date
}

const textEncoder = new TextEncoder()

const crcTable = new Uint32Array(256)
for (let i = 0; i < crcTable.length; i += 1) {
  let value = i
  for (let bit = 0; bit < 8; bit += 1) {
    value = value & 1 ? 0xedb88320 ^ (value >>> 1) : value >>> 1
  }
  crcTable[i] = value >>> 0
}

function crc32(bytes: Uint8Array): number {
  let crc = 0xffffffff
  for (const byte of bytes) {
    crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8)
  }
  return (crc ^ 0xffffffff) >>> 0
}

function asBytes(data: string | Uint8Array): Uint8Array {
  return typeof data === 'string' ? textEncoder.encode(data) : data
}

function normalizedPath(path: string): string {
  return path.replace(/\\/g, '/').replace(/^\/+/, '')
}

function dosDateTime(date: Date): { dosDate: number; dosTime: number } {
  const year = Math.max(1980, date.getFullYear())
  return {
    dosTime:
      (date.getHours() << 11) |
      (date.getMinutes() << 5) |
      Math.floor(date.getSeconds() / 2),
    dosDate:
      ((year - 1980) << 9) |
      ((date.getMonth() + 1) << 5) |
      date.getDate(),
  }
}

function writeUint16(view: DataView, offset: number, value: number): void {
  view.setUint16(offset, value, true)
}

function writeUint32(view: DataView, offset: number, value: number): void {
  view.setUint32(offset, value >>> 0, true)
}

function concat(chunks: readonly Uint8Array[]): Uint8Array {
  const size = chunks.reduce((sum, chunk) => sum + chunk.byteLength, 0)
  const result = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) {
    result.set(chunk, offset)
    offset += chunk.byteLength
  }
  return result
}

function asArrayBuffer(bytes: Uint8Array): ArrayBuffer {
  const copy = new Uint8Array(bytes.byteLength)
  copy.set(bytes)
  return copy.buffer
}

export function createStoredZipBlob(files: readonly ZipFileInput[]): Blob {
  const fileChunks: Uint8Array[] = []
  const centralDirectory: Uint8Array[] = []
  let offset = 0

  for (const file of files) {
    const nameBytes = textEncoder.encode(normalizedPath(file.path))
    const dataBytes = asBytes(file.data)
    const checksum = crc32(dataBytes)
    const { dosDate, dosTime } = dosDateTime(file.modifiedAt ?? new Date())

    const localHeader = new Uint8Array(30 + nameBytes.byteLength)
    const localView = new DataView(localHeader.buffer)
    writeUint32(localView, 0, 0x04034b50)
    writeUint16(localView, 4, 20)
    writeUint16(localView, 6, 0)
    writeUint16(localView, 8, 0)
    writeUint16(localView, 10, dosTime)
    writeUint16(localView, 12, dosDate)
    writeUint32(localView, 14, checksum)
    writeUint32(localView, 18, dataBytes.byteLength)
    writeUint32(localView, 22, dataBytes.byteLength)
    writeUint16(localView, 26, nameBytes.byteLength)
    writeUint16(localView, 28, 0)
    localHeader.set(nameBytes, 30)

    fileChunks.push(localHeader, dataBytes)

    const centralHeader = new Uint8Array(46 + nameBytes.byteLength)
    const centralView = new DataView(centralHeader.buffer)
    writeUint32(centralView, 0, 0x02014b50)
    writeUint16(centralView, 4, 20)
    writeUint16(centralView, 6, 20)
    writeUint16(centralView, 8, 0)
    writeUint16(centralView, 10, 0)
    writeUint16(centralView, 12, dosTime)
    writeUint16(centralView, 14, dosDate)
    writeUint32(centralView, 16, checksum)
    writeUint32(centralView, 20, dataBytes.byteLength)
    writeUint32(centralView, 24, dataBytes.byteLength)
    writeUint16(centralView, 28, nameBytes.byteLength)
    writeUint16(centralView, 30, 0)
    writeUint16(centralView, 32, 0)
    writeUint16(centralView, 34, 0)
    writeUint16(centralView, 36, 0)
    writeUint32(centralView, 38, 0)
    writeUint32(centralView, 42, offset)
    centralHeader.set(nameBytes, 46)
    centralDirectory.push(centralHeader)

    offset += localHeader.byteLength + dataBytes.byteLength
  }

  const centralStart = offset
  const centralBytes = concat(centralDirectory)
  const endRecord = new Uint8Array(22)
  const endView = new DataView(endRecord.buffer)
  writeUint32(endView, 0, 0x06054b50)
  writeUint16(endView, 4, 0)
  writeUint16(endView, 6, 0)
  writeUint16(endView, 8, files.length)
  writeUint16(endView, 10, files.length)
  writeUint32(endView, 12, centralBytes.byteLength)
  writeUint32(endView, 16, centralStart)
  writeUint16(endView, 20, 0)

  const blobParts = [...fileChunks, centralBytes, endRecord].map(asArrayBuffer)
  return new Blob(blobParts, { type: 'application/zip' })
}
