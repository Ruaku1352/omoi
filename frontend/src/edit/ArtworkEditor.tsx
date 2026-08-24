import { useEffect, useRef, useState } from 'react'
import type Konva from 'konva'
import { Stage, Layer, Image as KonvaImage, Transformer } from 'react-konva'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import { fromLayerRectPx, toLayerRectPx } from '../artwork/geometry'
import { normalizeLayerIndexes, sortByLayerIndex } from '../artwork/layerOrder'
import { clampScale } from '../config/artworkEditing'
import type { Artwork, Layer as ArtworkLayer } from '../types/artwork'

const STAGE_WIDTH = 600

/** URLから画像を読み込む。読み込みが終わるまでは null を返す。 */
function useImage(url: string) {
  const [image, setImage] = useState<HTMLImageElement | null>(null)

  useEffect(() => {
    const img = new window.Image()
    img.crossOrigin = 'anonymous'
    img.src = url
    img.onload = () => setImage(img)
    return () => {
      img.onload = null
    }
  }, [url])

  return image
}

function LayerImage({
  layer,
  url,
  stageWidth,
  stageHeight,
  isSelected,
  onSelect,
  onChangeRect,
}: {
  layer: ArtworkLayer
  url: string
  stageWidth: number
  stageHeight: number
  isSelected: boolean
  onSelect: () => void
  onChangeRect: (next: Pick<ArtworkLayer, 'x' | 'y' | 'scale'>) => void
}) {
  const image = useImage(url)
  const rect = toLayerRectPx(layer, stageWidth, stageHeight)
  const shapeRef = useRef<Konva.Image>(null)
  const trRef = useRef<Konva.Transformer>(null)

  useEffect(() => {
    if (isSelected && shapeRef.current && trRef.current) {
      trRef.current.nodes([shapeRef.current])
    }
  }, [isSelected, image])

  if (!image) return null

  return (
    <>
      <KonvaImage
        ref={shapeRef}
        image={image}
        x={rect.leftPx}
        y={rect.topPx}
        width={rect.widthPx}
        height={rect.heightPx}
        draggable
        onMouseDown={onSelect}
        onTap={onSelect}
        onDragEnd={(e) => {
          onChangeRect(
            fromLayerRectPx(
              { leftPx: e.target.x(), topPx: e.target.y(), widthPx: rect.widthPx },
              stageWidth,
              stageHeight,
              layer,
            ),
          )
        }}
        onTransformEnd={() => {
          const node = shapeRef.current
          if (!node) return
          const widthPx = node.width() * node.scaleX()
          node.scaleX(1)
          node.scaleY(1)
          const next = fromLayerRectPx(
            { leftPx: node.x(), topPx: node.y(), widthPx },
            stageWidth,
            stageHeight,
            layer,
          )
          onChangeRect({ ...next, scale: clampScale(next.scale) })
        }}
      />

      {isSelected && (
        <Transformer
          ref={trRef}
          rotateEnabled={false}
          keepRatio
          enabledAnchors={['top-left', 'top-right', 'bottom-left', 'bottom-right']}
        />
      )}
    </>
  )
}

export default function ArtworkEditor({
  artwork,
  onChange,
  assets,
}: {
  artwork: Artwork
  onChange: (next: Artwork) => void
  assets: AssetIndex
}) {
  const layers = sortByLayerIndex(artwork.layers)
  const stageWidth = STAGE_WIDTH
  const stageHeight = STAGE_WIDTH / artwork.canvas.aspectRatio
  const [selectedId, setSelectedId] = useState<string | null>(null)

  const updateLayer = (layerId: string, next: Partial<ArtworkLayer>) => {
    onChange({
      ...artwork,
      layers: artwork.layers.map((l) => (l.layerId === layerId ? { ...l, ...next } : l)),
    })
  }

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
    <div style={{ background: 'var(--editor-bg)', display: 'inline-block' }}>
      <Stage
        width={stageWidth}
        height={stageHeight}
        onMouseDown={(e) => {
          if (e.target === e.target.getStage()) setSelectedId(null)
        }}
      >
        <Layer>
          {layers.map((layer) => (
            <LayerImage
              key={layer.layerId}
              layer={layer}
              url={resolveAssetUrl(assets, layer.asset.assetId)}
              stageWidth={stageWidth}
              stageHeight={stageHeight}
              isSelected={layer.layerId === selectedId}
              onSelect={() => setSelectedId(layer.layerId)}
              onChangeRect={(next) => updateLayer(layer.layerId, next)}
            />
          ))}
        </Layer>
      </Stage>

      <ol style={{ color: '#eee', fontSize: 14, padding: '12px 24px' }}>
        {layers.map((layer) => (
          <li key={layer.layerId} style={{ marginBottom: 6 }}>
            {layer.label}（{layer.layerIndex}）
            <button type="button" onClick={() => swapOrder(layer.layerId, 1)} style={{ marginLeft: 8 }}>
              手前へ
            </button>
            <button type="button" onClick={() => swapOrder(layer.layerId, -1)} style={{ marginLeft: 4 }}>
              奥へ
            </button>
            {layer.replacementCandidates.map((c) => (
              <button
                key={c.candidateId}
                type="button"
                onClick={() => replaceLayer(layer.layerId, c.candidateId)}
                style={{ marginLeft: 4 }}
              >
                → {c.label}
              </button>
            ))}
          </li>
        ))}
      </ol>
    </div>
  )
}