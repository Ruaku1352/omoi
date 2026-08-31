import { Suspense, useRef, type ComponentRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, useTexture } from '@react-three/drei'
import { DoubleSide } from 'three'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import { toLayerPlane } from '../artwork/geometry'
import { sortByLayerIndex } from '../artwork/layerOrder'
import {
  previewDepthStep,
  previewLayerSheets,
  previewLayerThickness,
} from '../config/artworkEditing'
import type { Artwork, Layer } from '../types/artwork'
import iconRotate from '../assets/icon-rotate.svg'
import './ArtworkPreview.css'

function LayerPlane({
  layer,
  canvas,
  url,
}: {
  layer: Layer
  canvas: Artwork['canvas']
  url: string
}) {
  const texture = useTexture(url)
  const plane = toLayerPlane(layer, canvas, previewDepthStep)
  const gap = previewLayerThickness / Math.max(1, previewLayerSheets - 1)

  return (
    <>
      {Array.from({ length: previewLayerSheets }, (_, i) => (
        <mesh key={i} position={[plane.x3d, plane.y3d, plane.z + i * gap]}>
          <planeGeometry args={[plane.width, plane.height]} />
          <meshBasicMaterial map={texture} alphaTest={0.5} side={DoubleSide} />
        </mesh>
      ))}
    </>
  )
}

export default function ArtworkPreview({
  artwork,
  assets,
}: {
  artwork: Artwork
  assets: AssetIndex
}) {
  const layers = sortByLayerIndex(artwork.layers)
  const controlsRef = useRef<ComponentRef<typeof OrbitControls>>(null)

  return (
    <div className="preview3d">
      <div className="preview3d-head">
        <button
          type="button"
          className="preview3d-reset"
          onClick={() => controlsRef.current?.reset()}
        >
          正面に戻す
        </button>
        <span className="preview3d-hint">
          <img src={iconRotate} alt="" />
          ドラッグで回す・ホイールで寄る
        </span>
      </div>

      <div className="preview3d-canvas">
        <Canvas camera={{ position: [0, 0, 1.0] }}>
          <OrbitControls ref={controlsRef} makeDefault />
          <Suspense fallback={null}>
            {layers.map((layer) => (
              <LayerPlane
                key={layer.layerId}
                layer={layer}
                canvas={artwork.canvas}
                url={resolveAssetUrl(assets, layer.asset.assetId)}
              />
            ))}
          </Suspense>
        </Canvas>
      </div>
    </div>
  )
}