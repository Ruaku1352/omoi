import { normalizeLayerIndexes, sortByLayerIndex } from '../artwork/layerOrder'
import type { Artwork } from '../types/artwork'
import lineDotted from '../assets/line-dotted.svg'
import iconUpdown from '../assets/icon-updown.svg'
import './LayerPanel.css'

const chipColors = ['#5b75a2', '#d1ac6f', '#df96b0', '#91b8d5']

type Props = {
  artwork: Artwork
  onChange: (next: Artwork) => void
}

export default function LayerPanel({ artwork, onChange }: Props) {
  const layers = [...sortByLayerIndex(artwork.layers)].reverse()

  const swapOrder = (layerId: string, direction: -1 | 1) => {
    const ordered = sortByLayerIndex(artwork.layers)
    const i = ordered.findIndex((l) => l.layerId === layerId)
    const j = i + direction
    if (i < 0 || j < 0 || j >= ordered.length) return

    const a = ordered[i]
    const b = ordered[j]

    onChange({
      ...artwork,
      layers: normalizeLayerIndexes(
        artwork.layers.map((l) => {
          if (l.layerId === a.layerId) return { ...l, layerIndex: b.layerIndex }
          if (l.layerId === b.layerId) return { ...l, layerIndex: a.layerIndex }
          return l
        }),
      ),
    })
  }

  const replaceLayer = (layerId: string, candidateId: string) => {
    onChange({
      ...artwork,
      layers: artwork.layers.map((l) => {
        if (l.layerId !== layerId) return l
        const c = l.replacementCandidates.find((x) => x.candidateId === candidateId)
        if (!c) return l
        return {
          ...l,
          sourcePhotoId: c.sourcePhotoId,
          sourceLayerId: c.sourceLayerId,
          asset: c.asset,
          label: c.label,
          replacementCandidates: l.replacementCandidates.map((x) =>
            x.candidateId === candidateId
              ? {
                  candidateId: x.candidateId,
                  sourcePhotoId: l.sourcePhotoId,
                  sourceLayerId: l.sourceLayerId,
                  asset: l.asset,
                  label: l.label,
                }
              : x,
          ),
        }
      }),
    })
  }

  return (
    <aside className="lp">
      <div className="lp-head">
        <h2 className="lp-title">2Dで微調整</h2>
        <p className="lp-lead">
          レイヤー（重なり）と<br />
          写真のカット変更できます。
        </p>
      </div>

      <div className="lp-list">
        {layers.map((layer, i) => (
          <div key={layer.layerId}>
            {i > 0 && <img className="lp-sep" src={lineDotted} alt="" />}
            <div className="lp-row">
              <div className="lp-arrows">
                <button type="button" onClick={() => swapOrder(layer.layerId, 1)} disabled={i === 0}>▲</button>
                <button type="button" onClick={() => swapOrder(layer.layerId, -1)} disabled={i === layers.length - 1}>▼</button>
              </div>
              <span className="lp-chip" style={{ background: chipColors[i % chipColors.length] }} />
              <span className="lp-label">{layer.label}</span>
              {layer.replacementCandidates.length > 0 && (
                <button
                  type="button"
                  className="lp-pill"
                  onClick={() => replaceLayer(layer.layerId, layer.replacementCandidates[0].candidateId)}
                >
                  別カットに
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <div className="lp-hint">
        <div className="lp-hint-card">
          <img src={iconUpdown} alt="" />
          <p>
            ▲▼ で前後が入れ替わります。<br />
            上が手前です。
          </p>
        </div>
      </div>
    </aside>
  )
}