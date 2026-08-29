import type { Artwork, AssetRef } from '../types/artwork'
import type { AssetManifest, AssetManifestEntry } from '../types/assetManifest'
import type { GenerateSuccessResponse } from '../types/generateResponse'

export interface LoadedLocalPrintDataset {
  name: string
  artwork: Artwork
  assetManifest: AssetManifest
  objectUrls: string[]
  notes: string[]
}

interface NamedJson {
  name: string
  value: unknown
}

type FileWithRelativePath = File & { webkitRelativePath?: string }

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

function isArtwork(value: unknown): value is Artwork {
  return isRecord(value) && Array.isArray(value.layers) && isRecord(value.canvas)
}

function isAssetManifest(value: unknown): value is AssetManifest {
  return isRecord(value) && Array.isArray(value.assets)
}

function isGenerateSuccessResponse(value: unknown): value is GenerateSuccessResponse {
  return isRecord(value) && isArtwork(value.artwork) && isAssetManifest(value.assetManifest)
}

function fileRelativePath(file: File): string {
  return (file as FileWithRelativePath).webkitRelativePath || file.name
}

function basename(path: string): string {
  return path.replace(/\\/g, '/').split('/').pop() ?? path
}

function stripExtension(path: string): string {
  const name = basename(path)
  const dot = name.lastIndexOf('.')
  return dot === -1 ? name : name.slice(0, dot)
}

function extForMime(mimeType: AssetManifestEntry['mimeType']): string {
  if (mimeType === 'image/jpeg') return 'jpg'
  if (mimeType === 'image/webp') return 'webp'
  return 'png'
}

function collectAssets(artwork: Artwork): AssetRef[] {
  const assets: AssetRef[] = []
  for (const photo of artwork.sourcePhotos) assets.push(photo.asset)
  for (const layer of artwork.layers) {
    assets.push(layer.asset)
    for (const candidate of layer.replacementCandidates) assets.push(candidate.asset)
  }
  return assets
}

async function readJsonFiles(files: readonly File[]): Promise<NamedJson[]> {
  const jsonFiles = files.filter((file) => file.name.toLowerCase().endsWith('.json'))
  return Promise.all(
    jsonFiles.map(async (file) => ({
      name: file.name,
      value: JSON.parse(await file.text()) as unknown,
    })),
  )
}

function findArtworkAndManifest(jsons: readonly NamedJson[]): {
  name: string
  artwork: Artwork | null
  assetManifest: AssetManifest | null
} {
  for (const json of jsons) {
    if (isGenerateSuccessResponse(json.value)) {
      return {
        name: json.name,
        artwork: json.value.artwork,
        assetManifest: json.value.assetManifest,
      }
    }
  }

  return {
    name: jsons[0]?.name ?? 'local-files',
    artwork: jsons.find((json) => isArtwork(json.value))?.value as Artwork | null,
    assetManifest: jsons.find((json) => isAssetManifest(json.value))?.value as AssetManifest | null,
  }
}

function buildManifestFromArtwork(artwork: Artwork): AssetManifest {
  return {
    assets: collectAssets(artwork).map((asset) => ({
      assetId: asset.assetId,
      mimeType: asset.mimeType,
      widthPx: asset.widthPx,
      heightPx: asset.heightPx,
      url: `${asset.assetId}.${extForMime(asset.mimeType)}`,
    })),
  }
}

function findMatchingFile(entry: AssetManifestEntry, imageFiles: readonly File[]): File | null {
  const expectedName = basename(entry.url).toLowerCase()
  const expectedAssetName = `${entry.assetId}.${extForMime(entry.mimeType)}`.toLowerCase()

  for (const file of imageFiles) {
    const name = file.name.toLowerCase()
    const relative = fileRelativePath(file).replace(/\\/g, '/').toLowerCase()
    if (name === expectedName || name === expectedAssetName) return file
    if (stripExtension(name) === entry.assetId.toLowerCase()) return file
    if (relative.endsWith(`/assets/${expectedName}`)) return file
    if (relative.endsWith(`/assets/${expectedAssetName}`)) return file
  }

  return null
}

export async function loadLocalPrintDataset(filesInput: FileList | readonly File[]): Promise<LoadedLocalPrintDataset> {
  const files = Array.from(filesInput)
  const jsons = await readJsonFiles(files)
  const { name, artwork, assetManifest } = findArtworkAndManifest(jsons)
  if (!artwork) throw new Error('artwork.json か generate-success-response.json が見つかりません')

  const manifest = assetManifest ?? buildManifestFromArtwork(artwork)
  const imageFiles = files.filter((file) => file.type.startsWith('image/'))
  const objectUrls: string[] = []
  const notes: string[] = []

  const assets = manifest.assets.map((entry) => {
    const file = findMatchingFile(entry, imageFiles)
    if (!file) {
      notes.push(`${entry.assetId}: 選択ファイル内に画像が見つからなかったため、元URLを使います`)
      return entry
    }
    const url = URL.createObjectURL(file)
    objectUrls.push(url)
    return { ...entry, url }
  })

  return {
    name,
    artwork,
    assetManifest: { assets },
    objectUrls,
    notes,
  }
}
