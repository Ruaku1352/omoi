import { useState } from 'react'
import './App.css'
import { buildAssetIndex, resolveAssetUrl } from './artwork/assetIndex'
import { layerHeightRatio } from './artwork/geometry'
import { sortByLayerIndex } from './artwork/layerOrder'
import { apiBaseUrl } from './config/env'
import { buildMockAssetManifest, mockArtwork } from './mock/mockArtwork'
import PhotoSelect from './screens/PhotoSelect'
import ArtworkPreview from './preview/ArtworkPreview'
import ArtworkEditor from './edit/ArtworkEditor'
type Screen = 'select' | 'generating' | 'preview' | 'edit' | 'done'

/**
 * 共通Mockの `layers[]` を **layerIndex 昇順（0が最背面）** で並べて確認するページ。
 *
 * Scaffoldの動作確認用であり、3D Preview / 2D Edit の本実装ではない。
 * それらは Frontend担当が `skills/frontend/SKILL.md` の実装順で積む。
 */
export default function App() {
const [artwork, setArtwork] = useState(mockArtwork)
const [manifest, setManifest] = useState(buildMockAssetManifest(mockArtwork))
const [screen, setScreen] = useState<Screen>('preview')
const [error, setError] = useState<string | null>(null) 
  // `layers[]` の配列位置は奥行き順ではない。必ず layerIndex で並べ替える。
  const layers = sortByLayerIndex(artwork.layers)
  const assets = buildAssetIndex(manifest)

  return (
    <main className="app">
      <header>
        <h1>omoi</h1>
        <p className="tagline">Our Memories, One Image — Frontend Scaffold</p>
      </header>
      {screen ==='select' &&(
       <PhotoSelect
        onGenerated={(nextArtwork, nextManifest) => {
          setArtwork(nextArtwork)
          setManifest(nextManifest)
          setScreen('preview') 
        }}
         onStart={() => {
    setError(null)
    setScreen('generating')
  }}
  onFailed={(message) => setError(message)}
      />)}
      {screen === 'generating' && (
  <section style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
    {error === null ? (
      <p>作品を作っています…</p>
    ) : (
      <>
        <p style={{ color: 'salmon' }}>{error}</p>
        <button type="button" onClick={() => setScreen('select')}>
          写真を選び直す
        </button>
      </>
    )}
  </section>
)}
{screen === 'preview' && (
  <>
    <ArtworkPreview artwork={artwork} assets={assets} />
    <button type="button" onClick={() => setScreen('done')}>
      この作品で完成
    </button>
    <button type="button" onClick={() => setScreen('edit')}>
      少し調整する
    </button>
  </>
)}
{screen === 'edit' && (
  <><ArtworkEditor artwork={artwork} onChange={setArtwork} assets={assets} />
  <button type="button" onClick={() => setScreen('preview')}>
      編集を終える
    </button>
  </>
)}
{screen === 'done' && (
  <>
    <ArtworkPreview artwork={artwork} assets={assets} />

    <section style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h2>作品が完成しました</h2>
      <p>このデータから、実物のレイヤーアートを作ります。</p>

      <div style={{ display: 'flex', gap: 12 }}>
        <button type="button" onClick={() => setScreen('edit')}>
          もう一度調整する
        </button>
        <button type="button" onClick={() => setScreen('select')}>
          最初から作る
        </button>
      </div>
    </section>
  </>
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

      <footer className="muted">
        Artwork Data はURLを持たない。画像は Asset Manifest 経由で <code>assetId</code> を解決している。
      </footer>
    </main>
  )
}
