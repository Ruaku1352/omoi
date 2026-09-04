import { useState } from 'react'
import Breadcrumb from '../components/Breadcrumb'
import Sidebar from '../components/Sidebar'
import ArtworkPreview from '../preview/ArtworkPreview'
import type { AssetIndex } from '../artwork/assetIndex'
import type { Artwork } from '../types/artwork'
import iconCompose from '../assets/icon-compose.svg'
import './screen.css'

/**
 * 2D編集で変わりうる値（位置・大きさ・重なり順・差し替え）だけを取り出して比べる。
 * 生成直後のArtworkと今のArtworkが同じなら、見比べるボタンを出す意味がないので隠す。
 */
function layoutSignature(artwork: Artwork): string {
  return JSON.stringify(
    [...artwork.layers]
      .sort((a, b) => a.layerId.localeCompare(b.layerId))
      .map((l) => [l.layerId, l.x, l.y, l.scale, l.layerIndex, l.asset.assetId]),
  )
}

export default function PreviewScreen({
  artwork,
  initialArtwork,
  assets,
  onSelectScreen,
}: {
  artwork: Artwork
  /** 生成直後（2D編集する前）のArtwork Data。見比べ表示にのみ使う */
  initialArtwork: Artwork
  assets: AssetIndex
  onSelectScreen: (next: 'preview' | 'edit' | 'done') => void
}) {
  // 「最初の状態」を表示中かどうか。表示を切り替えるだけで、Artwork Dataは書き換えない
  // （3D PreviewはRead Only。AGENTS.md §7）。
  const [showingInitial, setShowingInitial] = useState(false)

  const edited = layoutSignature(artwork) !== layoutSignature(initialArtwork)
  const shown = showingInitial ? initialArtwork : artwork

  return (
    <div className="screen">
      <Sidebar onSelect={onSelectScreen} />

      <div className="screen-main">
        <div className="screen-top">
          <Breadcrumb current="preview" />
          <div className="screen-actions">
            {edited && (
              <button
                type="button"
                className="btn-outline"
                onClick={() => setShowingInitial((v) => !v)}
              >
                {showingInitial ? '編集後を見る' : '最初の状態を見る'}
              </button>
            )}
            <button type="button" className="btn-outline" onClick={() => onSelectScreen('edit')}>
              微調整する
            </button>
            <button type="button" className="btn-fill" onClick={() => onSelectScreen('done')}>
              <img src={iconCompose} alt="" />
              この作品で完成
            </button>
          </div>
        </div>

        {showingInitial && (
          <p
            style={{
              margin: 0,
              fontFamily: '"Zen Kaku Gothic New", sans-serif',
              fontSize: 13,
              color: 'var(--omoi-accent)',
              fontWeight: 700,
            }}
          >
            最初に作られた状態を表示しています（編集内容は保持されています）
          </p>
        )}

        {/* key を変えて、表示を切り替えたときにテクスチャ読み込みからやり直させる */}
        <ArtworkPreview
          key={showingInitial ? 'initial' : 'current'}
          artwork={shown}
          assets={assets}
        />
      </div>
    </div>
  )
}