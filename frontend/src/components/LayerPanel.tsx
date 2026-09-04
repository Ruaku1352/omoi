import { useState } from 'react'
import { normalizeLayerIndexes, sortByLayerIndex } from '../artwork/layerOrder'
import type { Artwork } from '../types/artwork'
import lineDotted from '../assets/line-dotted.svg'
import iconUpdown from '../assets/icon-updown.svg'
import './LayerPanel.css'

type Props = {
  artwork: Artwork
  onChange: (next: Artwork) => void
  selectedLayerId?: string | null
  onSelectLayer?: (layerId: string) => void
}

export default function LayerPanel({ artwork, onChange, selectedLayerId, onSelectLayer }: Props) {
  const layers = [...sortByLayerIndex(artwork.layers)].reverse()

  const [dragIndex, setDragIndex] = useState<number | null>(null)
  // ドラッグの落とし先は「レイヤーの行の上」ではなく「レイヤーとレイヤーの間のすき間」。
  // gapIndex は 0〜layers.length。gapIndex=0 は一番上、gapIndex=layers.length は一番下。
  const [overGap, setOverGap] = useState<number | null>(null)

  // layers は「手前(上)→奥(下)」の表示順。
  // ドラッグで並び替えたあと、逆順(奥→手前)にしてlayerIndexを振り直す
  const reorderLayers = (fromIndex: number, toIndex: number) => {
    if (fromIndex === toIndex) return

    const displayed = [...layers]
    const [moved] = displayed.splice(fromIndex, 1)
    displayed.splice(toIndex, 0, moved)

    const ascending = [...displayed].reverse()
    const layerIndexById = new Map(ascending.map((l, idx) => [l.layerId, idx]))

    onChange({
      ...artwork,
      layers: normalizeLayerIndexes(
        artwork.layers.map((l) => ({
          ...l,
          layerIndex: layerIndexById.get(l.layerId) ?? l.layerIndex,
        })),
      ),
    })
  }

  const handleDragStart = (index: number) => (e: React.DragEvent) => {
    setDragIndex(index)
    e.dataTransfer.effectAllowed = 'move'

    // ドラッグ中にカーソルへ追従するプレビュー画像から番号を除外する。
    // 何もしないと行全体（番号バッジ込み）のスナップショットがそのまま
    // プレビューになり、番号がドラッグ対象と一緒に動いているように見えてしまう。
    // 番号は常に「上から何番目か」という位置を表す値であって、
    // ドラッグ中のレイヤーに付随するものではないため。
    const row = e.currentTarget as HTMLElement
    const clone = row.cloneNode(true) as HTMLElement
    clone.querySelector('.lp-order')?.remove()
    clone.style.position = 'absolute'
    clone.style.top = '-9999px'
    clone.style.left = '-9999px'
    clone.style.width = `${row.offsetWidth}px`
    clone.style.pointerEvents = 'none'
    document.body.appendChild(clone)
    e.dataTransfer.setDragImage(clone, 20, row.offsetHeight / 2)
    window.setTimeout(() => {
      if (clone.parentNode) document.body.removeChild(clone)
    }, 0)
  }

  // 行(レイヤー)自体をドロップ先にする。カーソルがその行の上半分にあれば
  // 「この行の上」、下半分にあれば「この行の下」に挿入する gapIndex を決める。
  const gapIndexForRowEvent = (rowIndex: number, e: React.DragEvent) => {
    const rect = e.currentTarget.getBoundingClientRect()
    const isUpperHalf = e.clientY < rect.top + rect.height / 2
    return isUpperHalf ? rowIndex : rowIndex + 1
  }

  const handleRowDragOver = (rowIndex: number) => (e: React.DragEvent) => {
    e.preventDefault()
    const gapIndex = gapIndexForRowEvent(rowIndex, e)
    if (overGap !== gapIndex) setOverGap(gapIndex)
  }

  const handleRowDrop = (rowIndex: number) => (e: React.DragEvent) => {
    e.preventDefault()
    const gapIndex = gapIndexForRowEvent(rowIndex, e)
    if (dragIndex !== null) {
      // 自分自身を取り除いたあとに挿入するので、元の位置より後ろのすき間に
      // 落とした場合はひとつ前にずれる
      const toIndex = dragIndex < gapIndex ? gapIndex - 1 : gapIndex
      reorderLayers(dragIndex, toIndex)
    }
    setDragIndex(null)
    setOverGap(null)
  }

  const handleDragEnd = () => {
    setDragIndex(null)
    setOverGap(null)
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
            <div
              className={`lp-gap${overGap === i && dragIndex !== null && dragIndex !== i && dragIndex !== i - 1 ? ' is-over' : ''}`}
            >
              {i > 0 && <img className="lp-sep" src={lineDotted} alt="" />}
            </div>
            <div
              className={`lp-row${dragIndex === i ? ' is-dragging' : ''}${selectedLayerId === layer.layerId ? ' is-selected' : ''}`}
              draggable
              onClick={() => onSelectLayer?.(layer.layerId)}
              onDragStart={handleDragStart(i)}
              onDragOver={handleRowDragOver(i)}
              onDrop={handleRowDrop(i)}
              onDragEnd={handleDragEnd}
            >
              <span className="lp-handle" aria-label="ドラッグで並び替え">≡</span>
              <span className="lp-order">{i + 1}</span>
              <span className="lp-label">
                {layer.label}
                {i === 0 && <span className="lp-depth-tag">手前</span>}
                {i === layers.length - 1 && <span className="lp-depth-tag">奥</span>}
              </span>
              {/* 前後の入れ替えボタン。HTML5のドラッグ&ドロップはスマホのタッチでは
                  反応しないため、狭い画面のときだけこのボタンで前後を変えられるようにする
                  （2026-09-04、まなみん指示: 画面幅で操作方法を切り替える）。
                  表示/非表示の切り替えは LayerPanel.css の `.lp-move` 側で行う。
                  PC幅ではこのボタンを隠し、今まで通りドラッグで並び替える。 */}
              <button
                type="button"
                className="lp-pill lp-move"
                aria-label="ひとつ手前へ"
                disabled={i === 0}
                onClick={(e) => {
                  e.stopPropagation()
                  reorderLayers(i, i - 1)
                }}
              >
                ↑
              </button>
              <button
                type="button"
                className="lp-pill lp-move"
                aria-label="ひとつ奥へ"
                disabled={i === layers.length - 1}
                onClick={(e) => {
                  e.stopPropagation()
                  reorderLayers(i, i + 1)
                }}
              >
                ↓
              </button>
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
        <div
          className={`lp-gap${overGap === layers.length && dragIndex !== null && dragIndex !== layers.length - 1 ? ' is-over' : ''}`}
        />
      </div>

      <div className="lp-hint">
        <div className="lp-hint-card">
          <img src={iconUpdown} alt="" />
          {/* 操作方法の説明も画面幅に合わせて出し分ける（表示切り替えはCSS側） */}
          <p className="lp-hint-pc">
            ドラッグで前後が入れ替わります。<br />
            上が手前です。
          </p>
          <p className="lp-hint-sp">
            ↑↓ボタンで前後が<br />
            入れ替わります。上が手前です。
          </p>
        </div>
      </div>
    </aside>
  )
}