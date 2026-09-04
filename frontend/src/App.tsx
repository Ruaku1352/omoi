import { useState } from 'react'
import './App.css'
import { buildAssetIndex } from './artwork/assetIndex'
import { buildMockAssetManifest, mockArtwork } from './mock/mockArtwork'
import { buildDemoSampleZip } from './dev/exportDemoSample'
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
    setManifest({ assets })
    setScreen('preview')
  }}
>
  サンプル作品を見る
</button>
      <p className="sample-load-note">
        ※このボタンはAIによるリアルタイム生成ではなく、事前に生成したサンプル作品を表示します
      </p>
      <button
        type="button"
        className="debug-load-btn"
        onClick={async () => {
          // 今読み込まれている artwork + assets を public/demo/ 用のZIPとして書き出す。
          // サンプル作品(public/demo/artwork.json + public/demo/assets/)を
          // 差し替えたいときに使うローカル運用ツール(2026-09-04、まなみん依頼)。
          try {
            const blob = await buildDemoSampleZip(artwork, assets)
            const url = URL.createObjectURL(blob)
            const a = document.createElement('a')
            a.href = url
            a.download = 'demo-sample.zip'
            document.body.appendChild(a)
            a.click()
            a.remove()
            URL.revokeObjectURL(url)
          } catch (e) {
            setError(e instanceof Error ? e.message : 'サンプル用ZIPの書き出しに失敗しました。')
          }
        }}
      >
        今の作品をサンプル用にエクスポート
      </button>
      <p className="sample-load-note">
        ※今画面に出ている作品を artwork.json + assets/ のZIPでダウンロードします。
        展開して frontend/public/demo/ の中身を置き換えるとサンプル作品を差し替えられます
      </p>
      </div>
      {screen ==='select' &&(
       <PhotoSelect
        onGenerated={(nextArtwork, nextManifest) => {
          setArtwork(nextArtwork)
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
      {/* <section className="meta">
        <dl>
          <dt>Source</dt>
          <dd>
            <code>contracts/mock/artwork.json</code>
          </dd>
          <dt>schemaVersion</dt>
          <dd>
            <code>{artwork.schemaVersion}</code>
          </dd>
          <dt>artworkId</dt>
          <dd>
            <code>{artwork.artworkId}</code>
          </dd>
          <dt>canvas.aspectRatio</dt>
          <dd>
            <code>{artwork.canvas.aspectRatio}</code>
          </dd>
          <dt>sourcePhotos</dt>
          <dd>{artwork.sourcePhotos.length} 枚</dd>
          <dt>VITE_API_BASE_URL</dt>
          <dd>
            <code>{apiBaseUrl === '' ? '(未設定 / 同一Origin相対)' : apiBaseUrl}</code>
          </dd>
        </dl>
      </section> */}

      {/* <section>
        <h2>
          layers <span className="muted">— layerIndex 昇順（0が最背面）／{layers.length} 層</span>
        </h2>

        <ol className="layers">
          {layers.map((layer) => (
            <li key={layer.layerId} className="layer">
              <img
                className="thumb"
                src={resolveAssetUrl(assets, layer.asset.assetId)}
                alt={layer.label}
              />
              <div className="body">
                <p className="title">
                  <span className="badge">layerIndex {layer.layerIndex}</span>
                  <strong>{layer.label}</strong>
                </p>
                <dl className="props">
                  <dt>x / y</dt>
                  <dd>
                    {layer.x} / {layer.y} <span className="muted">（Layer中心・正規化）</span>
                  </dd>
                  <dt>scale</dt>
                  <dd>
                    {layer.scale}{' '}
                    <span className="muted">
                      （幅基準。高さ = {layerHeightRatio(layer).toFixed(4)} を asset から導出）
                    </span>
                  </dd>
                  <dt>asset</dt>
                  <dd>
                    <code>{layer.asset.assetId}</code>{' '}
                    <span className="muted">
                      {layer.asset.mimeType} {layer.asset.widthPx}×{layer.asset.heightPx}
                    </span>
                  </dd>
                  <dt>source</dt>
                  <dd>
                    <code>{layer.sourcePhotoId}</code> / <code>{layer.sourceLayerId}</code>
                  </dd>
                  <dt>差し替え候補</dt>
                  <dd>
                    {layer.replacementCandidates.length === 0
                      ? 'なし'
                      : layer.replacementCandidates.map((c) => c.label).join(' / ')}
                  </dd>
                </dl>
              </div>
            </li>
          ))}
        </ol>
      </section> */}

      {/*<footer className="muted">
        Artwork Data はURLを持たない。画像は Asset Manifest 経由で <code>assetId</code> を解決している。
      </footer>*/}
    </main>
  )
}