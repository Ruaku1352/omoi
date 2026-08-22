import { Suspense, useRef, type ComponentRef } from 'react'   // ← 変更
import { Canvas } from '@react-three/fiber'
import { OrbitControls, useTexture } from '@react-three/drei'
import { buildAssetIndex, resolveAssetUrl } from '../artwork/assetIndex'
import { toLayerPlane } from '../artwork/geometry'
import { sortByLayerIndex } from '../artwork/layerOrder'
import { previewDepthStep } from '../config/artworkEditing'
import { buildMockAssetManifest, mockArtwork } from '../mock/mockArtwork'
import type { Artwork, Layer } from '../types/artwork'

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

  return (
    <mesh position={[plane.x3d, plane.y3d, plane.z]}>
      <planeGeometry args={[plane.width, plane.height]} />
      <meshBasicMaterial map={texture} transparent depthWrite={false} />
    </mesh>
  )
}

export default function ArtworkPreview() {
  const artwork = mockArtwork
  const layers = sortByLayerIndex(artwork.layers)
  const assets = buildAssetIndex(buildMockAssetManifest(artwork))

  // ← 追加：OrbitControls を掴んでおくための入れ物
  const controlsRef = useRef<ComponentRef<typeof OrbitControls>>(null)

  return (
    <div style={{ position: 'relative', height: 400, background: '#111' }}>
      {/* ← 追加：3Dの上に重ねるボタン */}
      <button
        type="button"
        onClick={() => controlsRef.current?.reset()}
        style={{ position: 'absolute', top: 12, left: 12, zIndex: 1 }}
      >
        正面に戻す
      </button>

      <Canvas camera={{ position: [0, 0, 2] }}>
        <OrbitControls ref={controlsRef} makeDefault />   {/* ← 変更 */}
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
  )
}