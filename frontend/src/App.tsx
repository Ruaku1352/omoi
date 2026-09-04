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
import ErrorBoundary from './components/ErrorBoundary'
import type { JobStage } from './types/job'
import type { AssetRef } from './types/artwork'
import type { AssetManifestEntry } from './types/assetManifest'
export type Screen = 'select' | 'generating' | 'preview' | 'edit' | 'done'

/**
 * 共通Mockの `layers[]` を **layerIndex 昇順（0が最背面）** で並べて確認するページ。
 *
 * Scaffoldの動作確認用であり、3D Preview / 2D Edit の本実装ではない。
 * それらは Frontend担当が `skills/frontend/SKILL.md` の実装順で積む。
 */
export default function App() {
const [artwork, setArtwork] = useState(mockArtwork)
// 生成直後（2D編集する前）のArtwork Data。3D Previewで「最初の状態」を見比べるために保持する
// （2026-09-04、まなみん依頼）。2D編集では更新せず、新しい作品を読み込んだときだけ差し替える。
const [initialArtwork, setInitialArtwork] = useState(mockArtwork)
const [manifest, setManifest] = useState(buildMockAssetManifest(mockArtwork))
const [screen, setScreen] = useState<Screen>('select')
const [error, setError] = useState<string | null>(null)
const [stage, setStage] = useState<JobStage | undefined>(undefined)
  // `layers[]` の配列位置は奥行き順ではない。必ず layerIndex で並べ替える。
  const assets = buildAssetIndex(manifest)

  return (
    <main className="app">
      <Navbar />
      {error && <p className="app-error">{error}</p>}
{(screen === 'select' || screen === 'generating') && <Breadcrumb current={screen} />}
      <div className="sample-load">
      <button
  type="button"
  className="debug-load-btn"
  onClick={async () => {
    // `public/demo/artwork.json` + `public/demo/assets/<assetId>.<ext>` を読む。
    // Vite が public/ 配下を自動配信してくれるので、ローカルサーバー起動は不要。
    const res = await fetch('/demo/artwork.json')
    const demoArtwork = await res.json()
    const extByMime: Record<string, string> = {
      'image/png': 'png',
      'image/jpeg': 'jpg',
      'image/webp': 'webp',
    }
    const assets: AssetManifestEntry[] = []
    const addAsset = (asset: AssetRef) => {
      const ext = extByMime[asset.mimeType] ?? 'png'
      assets.push({ ...asset, url: `/demo/assets/${asset.assetId}.${ext}` })
    }
    for (const layer of demoArtwork.layers) {
      addAsset(layer.asset)
      for (const candidate of layer.replacementCandidates ?? []) addAsset(candidate.asset)
    }
    // 実際の生成フローと同じくローディング画面を経由させる（レイアウト確認・デモ用）。
    setError(null)
    setScreen('generating')
    const demoStages: JobStage[] = ['analyzing', 'extracting', 'composing', 'finalizing']
    for (const s of demoStages) {
      setStage(s)
      await new Promise((resolve) => setTimeout(resolve, 2500)) // 4段階 × 2.5秒 = 合計10秒
    }
    setArtwork(demoArtwork)
        setInitialArtwork(demoArtwork)
    setManifest({ assets })
    setScreen('preview')
  }}
>
  サンプル作品を見る
</button>
      <p className="sample-load-note">
        ※このボタンはAIによるリアルタイム生成ではなく、事前に生成したサンプル作品を表示します
      </p>
      </div>
      {screen ==='select' &&(
       <PhotoSelect
        onGenerated={(nextArtwork, nextManifest) => {
          setArtwork(nextArtwork)
          setInitialArtwork(nextArtwork)
          setManifest(nextManifest)
          setScreen('preview')
        }}
         onStart={() => { setError(null); setStage(undefined); setScreen('generating') }}
         onProgress={(next) => setStage(next.stage)}
  onFailed={(message) => { setError(message); setScreen('select') }}
      />)}
      {screen === 'generating' && <GeneratingScreen stage={stage} />}
<ErrorBoundary
  onReset={() => {
    setError('表示中にエラーが発生したため、最初からやり直してください。')
    setScreen('select')
  }}
>
{screen === 'preview' && (
  <PreviewScreen
    artwork={artwork}
    initialArtwork={initialArtwork}
    assets={assets}
    onSelectScreen={setScreen}
  />
)}
{screen === 'edit' && (
  <EditScreen
    artwork={artwork}
    assets={assets}
    onChange={setArtwork}
    onSelectScreen={setScreen}
  />
)}
{screen === 'done' && (
  <DoneScreen artwork={artwork} assets={assets} onSelectScreen={setScreen} />
)}
</ErrorBoundary>
    </main>
  )
}