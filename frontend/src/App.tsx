import './App.css'
import { useEffect, useMemo, useState, type ChangeEvent } from 'react'
import { buildAssetIndex, resolveAssetUrl } from './artwork/assetIndex'
import { layerHeightRatio } from './artwork/geometry'
import { sortByLayerIndex } from './artwork/layerOrder'
import { apiBaseUrl } from './config/env'
import { buildMockAssetManifest, mockArtwork } from './mock/mockArtwork'
import { loadLocalPrintDataset } from './print/localBundle'
import { PrintExportPanel } from './print/PrintExportPanel'
import type { Artwork } from './types/artwork'
import type { AssetManifest } from './types/assetManifest'

interface ActiveDataset {
  name: string
  artwork: Artwork
  assetManifest: AssetManifest
  notes: string[]
}

const mockDataset: ActiveDataset = {
  name: 'contracts/mock',
  artwork: mockArtwork,
  assetManifest: buildMockAssetManifest(mockArtwork),
  notes: [],
}

/**
 * 共通Mockの `layers[]` を **layerIndex 昇順（0が最背面）** で並べて確認するページ。
 *
 * Scaffoldの動作確認用であり、3D Preview / 2D Edit の本実装ではない。
 * それらは Frontend担当が `skills/frontend/SKILL.md` の実装順で積む。
 */
export default function App() {
  const [dataset, setDataset] = useState<ActiveDataset>(mockDataset)
  const [objectUrls, setObjectUrls] = useState<string[]>([])
  const [loadError, setLoadError] = useState<string | null>(null)
  const artwork = dataset.artwork
  // `layers[]` の配列位置は奥行き順ではない。必ず layerIndex で並べ替える。
  const layers = useMemo(() => sortByLayerIndex(artwork.layers), [artwork.layers])
  const assets = useMemo(() => buildAssetIndex(dataset.assetManifest), [dataset.assetManifest])

  useEffect(() => {
    return () => {
      for (const url of objectUrls) URL.revokeObjectURL(url)
    }
  }, [objectUrls])

  const handleLocalFiles = async (event: ChangeEvent<HTMLInputElement>) => {
    const input = event.currentTarget
    const files = input.files
    if (!files || files.length === 0) return
    try {
      const loaded = await loadLocalPrintDataset(files)
      setDataset({
        name: loaded.name,
        artwork: loaded.artwork,
        assetManifest: loaded.assetManifest,
        notes: loaded.notes,
      })
      setObjectUrls(loaded.objectUrls)
      setLoadError(null)
    } catch (caught) {
      setLoadError(caught instanceof Error ? caught.message : '読み込みに失敗しました')
    } finally {
      input.value = ''
    }
  }

  const resetToMock = () => {
    setObjectUrls([])
    setDataset(mockDataset)
    setLoadError(null)
  }

  return (
    <main className="app">
      <header>
        <h1>omoi</h1>
        <p className="tagline">Our Memories, One Image — Preview / Print Handoff</p>
      </header>

      <section className="meta">
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
      </section>

      <section className="bundle-loader">
        <div>
          <h2>入力データ</h2>
          <p className="muted">
            Driveで受け取ったResponse JSONとassets画像をまとめて選ぶと、この画面の入力を差し替えられる。
          </p>
        </div>
        <div className="loader-actions">
          <label className="file-button">
            JSONとassetsを選択
            <input type="file" multiple onChange={handleLocalFiles} />
          </label>
          <label className="file-button">
            展開Bundleフォルダ
            <input type="file" multiple {...{ webkitdirectory: '' }} onChange={handleLocalFiles} />
          </label>
          <button className="secondary-button" type="button" onClick={resetToMock}>
            Mockに戻す
          </button>
        </div>
        {loadError && <p className="error-text">{loadError}</p>}
        {dataset.notes.length > 0 && <p className="warning-text">{dataset.notes.join(' / ')}</p>}
      </section>

      <PrintExportPanel
        artwork={artwork}
        assetManifest={dataset.assetManifest}
        datasetName={dataset.name}
      />

      <section>
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
      </section>

      <footer className="muted">
        Artwork Data はURLを持たない。画像は Asset Manifest 経由で <code>assetId</code> を解決している。
      </footer>
    </main>
  )
}
