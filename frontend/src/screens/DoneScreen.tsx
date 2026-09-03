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

type ExportStatus = 'idle' | 'building' | 'done' | 'error'

export default function DoneScreen({ artwork, assets, onSelectScreen }: Props) {
  const [stlStatus, setStlStatus] = useState<ExportStatus>('idle')
  const [pdfStatus, setPdfStatus] = useState<ExportStatus>('idle')

  const today = new Date().toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })

  // 3Dプリンター用データ出力(STL一式ZIP)
  // 仮実装: 本来はBackend/物理出力側でSTLを生成する想定。
  // 現状は既存のPortable Artwork Bundle(artwork.json + assets/)を流用してダウンロードしている。
  // TODO: ナンちゃんとエンドポイント確定後、実際のSTL生成APIに差し替える
  const handleExportStl = async () => {
    setStlStatus('building')
    try {
      await downloadArtworkBundle(artwork, assets)
      setStlStatus('done')
    } catch (e) {
      setStlStatus('error')
    }
  }

  // 写真貼り付け用PDF出力(100%印刷用PDF)
  // 仮実装: 実際のPDF生成APIが未確定のためダミー処理。
  // TODO: エンドポイント確定後、fetch先を実際のAPIに差し替える
  const handleExportPdf = async () => {
    setPdfStatus('building')
    try {
      // TODO: 仮のエンドポイント。実際のパスが決まり次第差し替え
      const res = await fetch('/api/v1/artworks/export/pdf', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ artwork }),
      })
      if (!res.ok) throw new Error('PDF export failed')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'omoi-print.pdf'
      a.click()
      URL.revokeObjectURL(url)
      setPdfStatus('done')
    } catch (e) {
      setPdfStatus('error')
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
              {stlStatus === 'done' && (
                <p className="done-note">3Dプリンター用データをダウンロードしました！</p>
              )}
              {stlStatus === 'error' && (
                <p className="done-note">3Dデータの出力に失敗しました。もう一度お試しください。</p>
              )}
              {pdfStatus === 'done' && (
                <p className="done-note">印刷用PDFをダウンロードしました！</p>
              )}
              {pdfStatus === 'error' && (
                <p className="done-note">PDFの出力に失敗しました。もう一度お試しください。</p>
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
                onClick={handleExportStl}
                disabled={stlStatus === 'building'}
              >
                {stlStatus === 'building' ? '準備中…' : '3Dプリンター用データ出力'}
              </button>
              <button
                type="button"
                className="done-confirm done-confirm-pdf"
                onClick={handleExportPdf}
                disabled={pdfStatus === 'building'}
              >
                {pdfStatus === 'building' ? '準備中…' : '写真貼り付け用PDF出力'}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}