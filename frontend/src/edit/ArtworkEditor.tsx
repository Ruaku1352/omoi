import { useEffect, useRef, useState } from 'react'
import type Konva from 'konva'
import { Stage, Layer, Image as KonvaImage, Transformer } from 'react-konva'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import { fromLayerRectPx, toLayerRectPx } from '../artwork/geometry'
import { sortByLayerIndex } from '../artwork/layerOrder'
import { clampScale, minScale, maxScale } from '../config/artworkEditing'
import type { Artwork, Layer as ArtworkLayer } from '../types/artwork'

const DEFAULT_STAGE_WIDTH = 600

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
    boundBoxFunc={(oldBox, newBox) => {
      const minWidthPx = minScale * stageWidth
      const maxWidthPx = maxScale * stageWidth
      if (newBox.width < minWidthPx || newBox.width > maxWidthPx) {
        return oldBox
      }
      return newBox
    }}
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
const containerRef = useRef<HTMLDivElement>(null)
const [stageWidth, setStageWidth] = useState(DEFAULT_STAGE_WIDTH)
const stageHeight = stageWidth / artwork.canvas.aspectRatio
const [selectedId, setSelectedId] = useState<string | null>(null)

useEffect(() => {
  const el = containerRef.current
  if (!el) return

  const observer = new ResizeObserver((entries) => {
    setStageWidth(entries[0].contentRect.width)
  })
  observer.observe(el)
  return () => observer.disconnect()
}, [])
  const updateLayer = (layerId: string, next: Partial<ArtworkLayer>) => {
    onChange({
      ...artwork,
      layers: artwork.layers.map((l) => (l.layerId === layerId ? { ...l, ...next } : l)),
    })
  }

  

    

  return (
<div ref={containerRef} style={{ background: 'var(--editor-bg)', width: '100%', maxWidth: DEFAULT_STAGE_WIDTH }}>
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

      
    </div>
  )
}