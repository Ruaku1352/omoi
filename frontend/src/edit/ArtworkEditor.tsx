import { useEffect, useState } from 'react'
import { Stage, Layer, Image as KonvaImage } from 'react-konva'
import { buildAssetIndex, resolveAssetUrl } from '../artwork/assetIndex'
import { fromLayerRectPx, toLayerRectPx } from '../artwork/geometry'
import { sortByLayerIndex } from '../artwork/layerOrder'
import { buildMockAssetManifest } from '../mock/mockArtwork'
import type { Artwork, Layer as ArtworkLayer } from '../types/artwork'

const STAGE_WIDTH = 600

/** URLから画像を読み込む。読み込みが終わるまでは null を返す。 */
function useImage(url: string) {
  const [image, setImage] = useState<HTMLImageElement | null>(null)

  useEffect(() => {
    const img = new window.Image()
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
  onMove,
}: {
  layer: ArtworkLayer
  url: string
  stageWidth: number
  stageHeight: number
  onMove: (next: Pick<ArtworkLayer, 'x' | 'y' | 'scale'>) => void
}) {
  const image = useImage(url)
  const rect = toLayerRectPx(layer, stageWidth, stageHeight)

  if (!image) return null

  return (
    <KonvaImage
      image={image}
      x={rect.leftPx}
      y={rect.topPx}
      width={rect.widthPx}
      height={rect.heightPx}
      draggable
      onDragEnd={(e) => {
        onMove(
          fromLayerRectPx(
            { leftPx: e.target.x(), topPx: e.target.y(), widthPx: rect.widthPx },
            stageWidth,
            stageHeight,
            layer,
          ),
        )
      }}
    />
  )
}

export default function ArtworkEditor({
  artwork,
  onChange,
}: {
  artwork: Artwork
  onChange: (next: Artwork) => void
}) {
  const layers = sortByLayerIndex(artwork.layers)
  const assets = buildAssetIndex(buildMockAssetManifest(artwork))
  const stageWidth = STAGE_WIDTH
  const stageHeight = STAGE_WIDTH / artwork.canvas.aspectRatio

  const moveLayer = (layerId: string, next: Pick<ArtworkLayer, 'x' | 'y' | 'scale'>) => {
    onChange({
      ...artwork,
      layers: artwork.layers.map((l) => (l.layerId === layerId ? { ...l, ...next } : l)),
    })
  }

  return (
    <div style={{ background: 'var(--editor-bg)', display: 'inline-block' }}>
      <Stage width={stageWidth} height={stageHeight}>
        <Layer>
          {layers.map((layer) => (
            <LayerImage
              key={layer.layerId}
              layer={layer}
              url={resolveAssetUrl(assets, layer.asset.assetId)}
              stageWidth={stageWidth}
              stageHeight={stageHeight}
              onMove={(next) => moveLayer(layer.layerId, next)}
            />
          ))}
        </Layer>
      </Stage>
    </div>
  )
}