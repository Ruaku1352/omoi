import { useState } from 'react'
import Breadcrumb from '../components/Breadcrumb'
import ArtworkPreview from '../preview/ArtworkPreview'
import { exportPhysicalOutput } from '../api/exportPhysicalOutput'
import { ApiError } from '../api/errors'
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

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = fileName
  document.body.appendChild(a)
  a.click()
  a.remove()
  URL.revokeObjectURL(url)
}

export default function DoneScreen({ artwork, assets, onSelectScreen }: Props) {
  const [stlStatus, setStlStatus] = useState<ExportStatus>('idle')
  const [stlError, setStlError] = useState<string | null>(null)
  const [pdfStatus, setPdfStatus] = useState<ExportStatus>('idle')
  const [pdfError, setPdfError] = useState<string | null>(null)

  const today = new Date().toLocaleDateString('ja-JP', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })

  // 3Dプリンター用データ出力(STL一式ZIP)
  // Backend(Physical Output)側の POST /api/v1/physical-output/exports を叩く。
  // STL生成ロジック自体はBackend側の責務。Frontendは確定Artwork + 参照Assetを渡し、
  // 返ってきたZIPをダウンロードさせるだけ（印藤さん共有分、#大阪_team-g）。
  const handleExportStl = async () => {
    setStlStatus('building')
    setStlError(null)
    try {
      const { blob, fileName } = await exportPhysicalOutput(artwork, assets, 'stlZip')
      downloadBlob(blob, fileName)
      setStlStatus('done')
    } catch (e) {
      setStlError(
        e instanceof ApiError ? e.message : '3Dデータの出力に失敗しました。もう一度お試しください。',
      )
      setStlStatus('error')
    }
  }

  // 写真貼り付け用PDF出力
  // 同じくBackend側の POST /api/v1/physical-output/exports を叩く（outputFormat: "photoPdf"）。
  const handleExportPdf = async () => {
    setPdfStatus('building')
    setPdfError(null)
    try {
      const { blob, fileName } = await exportPhysicalOutput(artwork, assets, 'photoPdf')
      downloadBlob(blob, fileName)
      setPdfStatus('done')
    } catch (e) {
      setPdfError(
        e instanceof ApiError ? e.message : 'PDFの出力に失敗しました。もう一度お試しください。',
      )
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
                <p className="done-note">
                  {stlError ?? '3Dデータの出力に失敗しました。もう一度お試しください。'}
                </p>
              )}
              {pdfStatus === 'done' && (
                <p className="done-note">印刷用PDFをダウンロードしました！</p>
              )}
              {pdfStatus === 'error' && (
                <p className="done-note">
                  {pdfError ?? 'PDFの出力に失敗しました。もう一度お試しください。'}
                </p>
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