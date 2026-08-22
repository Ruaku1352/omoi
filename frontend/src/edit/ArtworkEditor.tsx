import { useEffect, useState } from 'react'
import { Stage, Layer, Image as KonvaImage } from 'react-konva'
import { buildAssetIndex, resolveAssetUrl } from '../artwork/assetIndex'
import { toLayerRectPx } from '../artwork/geometry'
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
}: {
  layer: ArtworkLayer
  url: string
  stageWidth: number
  stageHeight: number
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
    />
  )
}

export default function ArtworkEditor({ artwork }: { artwork: Artwork }) {
  const layers = sortByLayerIndex(artwork.layers)
  const assets = buildAssetIndex(buildMockAssetManifest(artwork))
  const stageWidth = STAGE_WIDTH
  const stageHeight = STAGE_WIDTH / artwork.canvas.aspectRatio

  return (
    <div style={{ background: '#111', display: 'inline-block' }}>
      <Stage width={stageWidth} height={stageHeight}>
        <Layer>
          {layers.map((layer) => (
            <LayerImage
              key={layer.layerId}
              layer={layer}
              url={resolveAssetUrl(assets, layer.asset.assetId)}
              stageWidth={stageWidth}
              stageHeight={stageHeight}
            />
          ))}
        </Layer>
      </Stage>
    </div>
  )
}