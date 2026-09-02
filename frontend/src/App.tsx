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
  // `layers[]` の配列位置は奥行き順ではない。必ず layerIndex で並べ替える。
  const assets = buildAssetIndex(manifest)

  return (
    <main className="app">
      <Navbar />
      {error && <p className="app-error">{error}</p>}
{(screen === 'select' || screen === 'generating') && <Breadcrumb current={screen} />}
      <button
  type="button"
  onClick={async () => {
    const base = 'http://localhost:8000'
    const res = await fetch(`${base}/generate-success-response.bundle.json`)
    const data = await res.json()
    const manifest = {
      assets: data.assetManifest.assets.map((a: { url: string }) => ({
        ...a,
        url: `${base}/${a.url}`,
      })),
    }
    setArtwork(data.artwork)
    setManifest(manifest)
    setScreen('preview')
  }}
>
  実データを読む（デバッグ用）
</button>
      {screen ==='select' &&(
       <PhotoSelect
        onGenerated={(nextArtwork, nextManifest) => {
          setArtwork(nextArtwork)
          setManifest(nextManifest)
          setScreen('preview') 
        }}
         onStart={() => { setError(null); setScreen('generating') }}
  onFailed={(message) => setError(message)}
      />)}
      {screen === 'generating' && <GeneratingScreen />}
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
