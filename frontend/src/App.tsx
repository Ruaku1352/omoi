import { useState } from 'react'
import './App.css'
import { buildAssetIndex } from './artwork/assetIndex'
import { buildMockAssetManifest, mockArtwork } from './mock/mockArtwork'
import PhotoSelect from './screens/PhotoSelect'
import Navbar from './components/Navbar'
import Breadcrumb from './components/Breadcrumb'
import PreviewScreen from './screens/PreviewScreen'
import EditScreen from './screens/EditScreen'
import GeneratingScreen from './screens/GeneratingScreen'
import DoneScreen from './screens/DoneScreen'
import type { Artwork, AssetMimeType, AssetRef } from './types/artwork'
import type { AssetManifestEntry } from './types/assetManifest'
import type { JobStage } from './types/job'
export type Screen = 'select' | 'generating' | 'preview' | 'edit' | 'done'

const DEMO_LOADING_MS = 10000
const DEMO_BASE = '/demo'
const DEMO_EXT: Record<AssetMimeType, string> = {
  'image/png': 'png',
  'image/jpeg': 'jpg',
  'image/webp': 'webp',
}

export default function App() {
  const [artwork, setArtwork] = useState(mockArtwork)
  const [manifest, setManifest] = useState(buildMockAssetManifest(mockArtwork))
  const [screen, setScreen] = useState<Screen>('select')
  const [error, setError] = useState<string | null>(null)
  const [stage, setStage] = useState<JobStage | undefined>(undefined)
  const assets = buildAssetIndex(manifest)

  const runDemo = async () => {
    setError(null)
    setScreen('generating')
    try {
      const res = await fetch(`${DEMO_BASE}/artwork.json`)
      if (!res.ok) throw new Error('demo artwork.json not found')
      const demoArtwork = (await res.json()) as Artwork
      const entries = new Map<string, AssetManifestEntry>()
      const add = (asset: AssetRef) => {
        entries.set(asset.assetId, {
          assetId: asset.assetId,
          mimeType: asset.mimeType,
          widthPx: asset.widthPx,
          heightPx: asset.heightPx,
          url: `${DEMO_BASE}/assets/${asset.assetId}.${DEMO_EXT[asset.mimeType]}`,
        })
      }
      for (const photo of demoArtwork.sourcePhotos) add(photo.asset)
      for (const layer of demoArtwork.layers) {
        add(layer.asset)
        for (const candidate of layer.replacementCandidates) add(candidate.asset)
      }
      await new Promise((resolve) => setTimeout(resolve, DEMO_LOADING_MS))
      setArtwork(demoArtwork)
      setManifest({ assets: Array.from(entries.values()) })
      setScreen('preview')
    } catch {
      setError('デモデータを読み込めませんでした。')
      setScreen('select')
    }
  }

  return (
    <main className="app">
      <Navbar />
      {error && <p className="app-error">{error}</p>}
      {(screen === 'select' || screen === 'generating') && <Breadcrumb current={screen} />}
      {screen === 'select' && (
        <button type="button" className="app-demo" onClick={runDemo}>
          生成済みサンプルでデモを見る（その場でのAI生成は行いません）
        </button>
      )}
      {screen === 'select' && (
        <PhotoSelect
          onGenerated={(nextArtwork, nextManifest) => {
            setArtwork(nextArtwork)
            setManifest(nextManifest)
            setScreen('preview')
          }}
          onStart={() => { setError(null); setStage(undefined); setScreen('generating') }}
          onProgress={(next) => setStage(next.stage)}
          onFailed={(message) => { setError(message); setScreen('select') }}
        />
      )}
      {screen === 'generating' && <GeneratingScreen stage={stage} />}
      {screen === 'preview' && (
        <PreviewScreen artwork={artwork} assets={assets} onSelectScreen={setScreen} />
      )}
      {screen === 'edit' && (
        <EditScreen artwork={artwork} assets={assets} onChange={setArtwork} onSelectScreen={setScreen} />
      )}
      {screen === 'done' && (
        <DoneScreen artwork={artwork} assets={assets} onSelectScreen={setScreen} />
      )}
    </main>
  )
}