import { Suspense, useEffect, useRef, useState, type ComponentRef } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, useTexture } from '@react-three/drei'
import { DoubleSide } from 'three'
import { resolveAssetUrl, type AssetIndex } from '../artwork/assetIndex'
import { toLayerPlane } from '../artwork/geometry'
import { sortByLayerIndex } from '../artwork/layerOrder'
import {
  previewCameraDistance,
  previewDepthStep,
  previewLayerSheets,
  previewLayerThickness,
} from '../config/artworkEditing'
import type { Artwork, Layer } from '../types/artwork'
import iconRotate from '../assets/icon-rotate.svg'
import PhysicalBase from './PhysicalBase'
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

/**
 * Suspenseの中身（＝全Layerのテクスチャ読み込み）が解決したことを外へ知らせるだけの部品。
 * 読み込み中のオーバーレイを消すタイミングに使う。
 */
function ReadySignal({ onReady }: { onReady: () => void }) {
  useEffect(() => {
    onReady()
  }, [onReady])
  return null
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
  // Layer画像の読み込みが終わったか。終わるまでは土台も含めて何も見せない
  // （2026-09-04、まなみん指摘: 土台だけ先に出て写真が後から乗るのを無くしたい）
  const [ready, setReady] = useState(false)

  // カメラのz。一番手前のLayerから一定距離だけ離して置く。
  // 固定値にすると、Layerが増えたり間隔を広げたときに手前のLayerが目の前へ来てしまう
  // （2026-09-04、まなみん指摘: 最初の表示が近すぎて圧迫感がある）。
  const frontLayerZ =
    layers.length > 0 ? Math.max(...layers.map((l) => l.layerIndex)) * previewDepthStep : 0
  const cameraZ = frontLayerZ + previewCameraDistance

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

      <div className="preview3d-canvas" style={{ position: 'relative' }}>
        <Canvas camera={{ position: [0, 0, cameraZ] }}>
          <OrbitControls ref={controlsRef} makeDefault />
          {/* 土台もSuspenseの内側へ入れる。外に置くとテクスチャ待ちの影響を受けず
              先に描画されてしまい、「土台だけ先に出て写真が後から乗る」状態になる。
              内側へ入れることで、Layer画像が揃ってから土台ごと一度に表示される。 */}
          <Suspense fallback={null}>
            <PhysicalBase artwork={artwork} />
            {layers.map((layer) => (
              <LayerPlane
                key={layer.layerId}
                layer={layer}
                canvas={artwork.canvas}
                url={resolveAssetUrl(assets, layer.asset.assetId)}
              />
            ))}
            <ReadySignal onReady={() => setReady(true)} />
          </Suspense>
        </Canvas>
        {!ready && (
          <div
            style={{
              position: 'absolute',
              inset: 0,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontFamily: '"Zen Kaku Gothic New", sans-serif',
              fontSize: 13,
              color: 'var(--omoi-gray)',
              pointerEvents: 'none',
            }}
          >
            読み込み中…
          </div>
        )}
      </div>
    </div>
  )
}