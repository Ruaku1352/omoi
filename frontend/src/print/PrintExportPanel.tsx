import { useState } from 'react'
import type { Artwork } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'
import {
  downloadBlob,
  generateBrowserFlatPrintPackage,
  type BrowserFlatPrintReport,
} from './flatPrint'

interface PrintExportPanelProps {
  artwork: Artwork
  assetManifest: AssetManifest
  datasetName: string
}

export function PrintExportPanel({
  artwork,
  assetManifest,
  datasetName,
}: PrintExportPanelProps) {
  const [isGenerating, setIsGenerating] = useState(false)
  const [report, setReport] = useState<BrowserFlatPrintReport | null>(null)
  const [error, setError] = useState<string | null>(null)

  const handleGenerate = async () => {
    setIsGenerating(true)
    setError(null)
    try {
      const generated = await generateBrowserFlatPrintPackage(artwork, assetManifest)
      downloadBlob(generated.blob, generated.fileName)
      setReport(generated.report)
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : '印刷データ生成に失敗しました')
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <section className="print-panel">
      <div className="section-heading">
        <div>
          <h2>印刷データ</h2>
          <p className="muted">
            {datasetName} から、平面パーツSTLと4層3穴土台STLをZIPで出力する。
          </p>
        </div>
        <button className="primary-button" type="button" onClick={handleGenerate} disabled={isGenerating}>
          {isGenerating ? '生成中' : 'STL ZIPを生成'}
        </button>
      </div>

      <div className="print-rules">
        <span>layerIndex 0も出力</span>
        <span>浮いた塊は低い支えで接続</span>
        <span>G-codeはBambu Studioで作成</span>
      </div>

      {error && <p className="error-text">{error}</p>}

      {report && (
        <div className="print-report">
          <dl>
            <dt>パーツ</dt>
            <dd>{report.parts.length} 個</dd>
            <dt>土台</dt>
            <dd>
              {report.base.widthMm} x {report.base.depthMm} x {report.base.heightMm}mm
            </dd>
            <dt>自動支え</dt>
            <dd>{report.parts.reduce((sum, part) => sum + part.supportBridgeCount, 0)} 本</dd>
          </dl>

          <ul>
            {report.parts.map((part) => (
              <li key={part.layerId}>
                <strong>{part.label}</strong>
                <span>
                  layerIndex {part.layerIndex} / {part.widthMm} x {part.heightMm}mm / 浮き{' '}
                  {part.floatingComponentCount} / 支え {part.supportBridgeCount}
                </span>
              </li>
            ))}
          </ul>

          {report.warnings.length > 0 && (
            <p className="warning-text">{report.warnings.join(' / ')}</p>
          )}
        </div>
      )}
    </section>
  )
}
