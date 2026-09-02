import { useState } from 'react'
import Breadcrumb from '../components/Breadcrumb'
import ArtworkPreview from '../preview/ArtworkPreview'
import { downloadArtworkBundle } from '../bundle/artworkBundle'
import type { AssetIndex } from '../artwork/assetIndex'
import type { Artwork } from '../types/artwork'
import type { Screen } from '../App'
import './DoneScreen.css'

type Props = {
  artwork: Artwork
  assets: AssetIndex
  onSelectScreen: (screen: Screen) => void
}

export default function DoneScreen({ artwork, assets, onSelectScreen }: Props) {
  const [status, setStatus] = useState<'idle' | 'building' | 'done' | 'error'>('idle')

  const today = new Date().toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })

  const handleConfirm = async () => {
    setStatus('building')
    try {
      await downloadArtworkBundle(artwork, assets)
      setStatus('done')
    } catch (e) {
      setStatus('error')
    }
  }

  return (
    <div className="done">
      <div className="done-flow">
        <Breadcrumb current="done" />
      </div>

      <div className="done-stage">
        <div className="done-card done-left">
          <ArtworkPreview artwork={artwork} assets={assets} />
          <div className="done-caption">
            <span className="done-caption-title">思い出のレイヤーアート</span>
            <span className="done-caption-date">{today}</span>
          </div>
        </div>

        <div className="done-card done-right">
          <div className="done-panel">
            <div className="done-panel-top">
              <h2 className="done-title">完成しました！</h2>
              <p className="done-lead">
                確定すると、このデータをもとに<br />
                レイヤーアートを制作します。
              </p>
              <p className="done-note">
                ※「最初から作る」を選ぶと<br />
                　作ったデータは消えてしまいます。
              </p>
              {status === 'done' && (
                <p className="done-note">ダウンロードしました！ナンちゃんに渡してね。</p>
              )}
              {status === 'error' && (
                <p className="done-note">ダウンロードに失敗しました。もう一度お試しください。</p>
              )}
            </div>

            <div className="done-panel-actions">
              <button type="button" className="done-restart" onClick={() => onSelectScreen('select')}>
                ※最初から作る
              </button>
              <button type="button" className="done-again" onClick={() => onSelectScreen('edit')}>
                もう一度調整する
              </button>
              <button
                type="button"
                className="done-confirm"
                onClick={handleConfirm}
                disabled={status === 'building'}
              >
                {status === 'building' ? '準備中…' : 'この作品で確定する'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}