import { useEffect, useRef, useState } from 'react'
import type Konva from 'konva'
import { Stage, Layer, Image as KonvaImage, Transformer } from 'react-konva'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import {
  clampLayerCenterWithinCanvas,
  fromLayerRectPx,
  maxScaleWithinCanvas,
  toLayerRectPx,
} from '../artwork/geometry'
import { sortByLayerIndex } from '../artwork/layerOrder'
import { clampScale, minScale, maxScale, maxOutOfCanvasRatio } from '../config/artworkEditing'
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
  canvas,
  url,
  stageWidth,
  stageHeight,
  maxScaleForLayer,
  isSelected,
  onSelect,
  onChangeRect,
}: {
  layer: ArtworkLayer
  canvas: Artwork['canvas']
  url: string
  stageWidth: number
  stageHeight: number
  /** このLayerが2L判(Canvas)に収まる scale の上限。Assetの縦横比ごとに変わる */
  maxScaleForLayer: number
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
        // ドラッグ中のリアルタイム制限。Layerの四辺が許容範囲（既定ではCanvas内）から
        // 出ないところで止める。土台へ載らない位置まで動かせてしまうのを防ぐ
        // （2026-09-04、まなみん指摘）。許容量は config/artworkEditing.ts 側で管理する。
        dragBoundFunc={(pos) => {
          // Layerの四辺がCanvasの外へ出ないところで止める（中心ではなく全体で判定）
          const minLeft = -maxOutOfCanvasRatio * stageWidth
          const maxLeft = (1 + maxOutOfCanvasRatio) * stageWidth - rect.widthPx
          const minTop = -maxOutOfCanvasRatio * stageHeight
          const maxTop = (1 + maxOutOfCanvasRatio) * stageHeight - rect.heightPx
          return {
            x: maxLeft < minLeft ? pos.x : Math.min(maxLeft, Math.max(minLeft, pos.x)),
            y: maxTop < minTop ? pos.y : Math.min(maxTop, Math.max(minTop, pos.y)),
          }
        }}
        onDragEnd={(e) => {
          const next = fromLayerRectPx(
            { leftPx: e.target.x(), topPx: e.target.y(), widthPx: rect.widthPx },
            stageWidth,
            stageHeight,
            layer,
          )
          // 保存する正規化値の側でも念のため丸める（dragBoundFuncを通らない経路への保険）
          onChangeRect({
            ...next,
            ...clampLayerCenterWithinCanvas(
              { ...layer, ...next },
              canvas,
              maxOutOfCanvasRatio,
            ),
          })
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
          // 拡大縮小の結果、Layerが枠の外へ出ることがあるので位置もあわせて丸める
          const scale = Math.min(maxScaleForLayer, clampScale(next.scale))
          onChangeRect({
            scale,
            ...clampLayerCenterWithinCanvas(
              { ...layer, ...next, scale },
              canvas,
              maxOutOfCanvasRatio,
            ),
          })
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
      // 幅・高さの両方が2L判(Canvas)に収まる上限。縦長のAssetでは幅の上限より小さくなる
      const maxWidthPx = maxScaleForLayer * stageWidth
      if (newBox.width < minWidthPx || newBox.width > maxWidthPx) {
        return oldBox
      }
      // 拡大の結果、四辺がCanvasの外へ出る操作は受け付けない
      const outX = maxOutOfCanvasRatio * stageWidth
      const outY = maxOutOfCanvasRatio * stageHeight
      if (
        newBox.x < -outX ||
        newBox.y < -outY ||
        newBox.x + newBox.width > stageWidth + outX ||
        newBox.y + newBox.height > stageHeight + outY
      ) {
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
  selectedId: selectedIdProp,
  onSelectId,
}: {
  artwork: Artwork
  onChange: (next: Artwork) => void
  assets: AssetIndex
  selectedId?: string | null
  onSelectId?: (layerId: string | null) => void
}) {
const layers = sortByLayerIndex(artwork.layers)
const containerRef = useRef<HTMLDivElement>(null)
const [stageWidth, setStageWidth] = useState(DEFAULT_STAGE_WIDTH)
const stageHeight = stageWidth / artwork.canvas.aspectRatio
const [selectedIdInternal, setSelectedIdInternal] = useState<string | null>(null)
const selectedId = selectedIdProp !== undefined ? selectedIdProp : selectedIdInternal
const setSelectedId = onSelectId ?? setSelectedIdInternal

useEffect(() => {
  const el = containerRef.current
  if (!el) return

  const observer = new ResizeObserver((entries) => {
    setStageWidth(entries[0].contentRect.width)
  })
  observer.observe(el)
  return () => observer.disconnect()
}, [])
  // Artwork Dataへ書き戻す唯一の入口。どの操作経路から来ても、ここで
  // scale と 位置(x / y) を許容範囲へ丸めてから保存する
  // （2026-09-04、まなみん指摘: 際限なく拡大できる／土台外へ動かせるのを防ぐ）。
  const updateLayer = (layerId: string, next: Partial<ArtworkLayer>) => {
    onChange({
      ...artwork,
      layers: artwork.layers.map((l) => {
        if (l.layerId !== layerId) return l
        const merged = { ...l, ...next }
        const scale = Math.min(
          maxScaleWithinCanvas(merged, artwork.canvas, maxScale),
          clampScale(merged.scale),
        )
        return {
          ...merged,
          scale,
          ...clampLayerCenterWithinCanvas(
            { ...merged, scale },
            artwork.canvas,
            maxOutOfCanvasRatio,
          ),
        }
      }),
    })
  }

  return (
<div ref={containerRef} className="ae-stage" style={{ background: 'var(--editor-bg)', width: '100%', maxWidth: DEFAULT_STAGE_WIDTH }}>
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
              canvas={artwork.canvas}
              url={resolveAssetUrl(assets, layer.asset.assetId)}
              stageWidth={stageWidth}
              stageHeight={stageHeight}
              maxScaleForLayer={maxScaleWithinCanvas(layer, artwork.canvas, maxScale)}
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