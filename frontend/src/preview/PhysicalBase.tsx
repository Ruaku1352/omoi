/**
 * 3D Preview上に、現在のPhysical Output仕様(土台・穴グリッド・横レール)の
 * 見た目を重ねて表示する。印藤さん(Physical Output担当)共有分
 * (#大阪_team-g、2026-09-04 スレッド `p1788464147430659`、および追補のスロット形状図)。
 *
 * ここで使う寸法比はあくまで「3D Preview上の見た目をBackendの物理出力仕様に近づけるための
 * 参照値」であり、Artwork DataやBackendへ送る設定値ではない(AGENTS.md §7 / §8)。
 * Read Onlyの装飾のみで、Artwork Dataは一切変更しない。
 *
 * - 出力サイズは2L判(178mm幅)を前提にする
 * - 土台は横長のベースとして表示する
 * - 土台は4行×3穴、計12穴として表示する(細長いスロット形状。実際に使われるかはLayer数次第)
 * - layerIndex が大きいLayerほど手前に表示する(toLayerPlaneの z 計算と同じ基準)
 * - layerIndex: 0 は背景Layerとして扱う
 * - 行の間隔・土台の奥行きは previewDepthStep から出す。こうしておくと、間隔を変えても
 *   Layer・穴・横レールが必ず同じ位置で揃う(2026-09-04、まなみん要望で間隔を可変にした)
 * - 背景以外の前景Layerは、横レールで支えられている見た目にする
 *   (1つの前景Layerの下に、同じ行の3穴すべてに差し込まれている横長の支えパーツがある見た目。
 *   印藤さん共有分の `supportMode: "rail"` に対応)
 * - layerIndex: 0(背景Layer)には横レールを作らない。2D編集で前後変更した結果、
 *   別のLayerが新たにlayerIndex: 0になった場合も同様
 * - 横レールは2段構成: 行全体を貫く低いレール + Layer中心(x)だけ棒状に高くなる足
 * - レール・足の前後方向の厚みは実寸のスロット幅(1.95mm)基準。previewDepthStep から出すと、
 *   Layer間隔を変えたときに一緒に太ってしまう
 * - 2D編集でLayerの左右位置(x)を変えたら足もそのxに追従し、上下位置(y)を変えたら
 *   Layer本体の下端まで届くように足の高さが変わる
 *
 * 背景Layer用の装飾back panelは、実際のLayer画像と別に額縁のような不要な板が
 * もう1枚あるように見えてしまったため廃止(2026-09-04、まなみん確認済み)。
 */
import { DoubleSide } from 'three'
import { previewDepthStep } from '../config/artworkEditing'
import { toLayerPlane } from '../artwork/geometry'
import type { Artwork } from '../types/artwork'

// 印藤さん共有のmm参照値。2L判(178mm幅)を基準に、Canvas幅=1.0の正規化座標へ換算する。
const REF_CANVAS_WIDTH_MM = 178
const REF_BASE_WIDTH_MM = 170
const REF_BASE_THICKNESS_MM = 5
// スロット(穴)の形状。横幅12mm x 前後幅(スロット幅)1.95mmの細長い長方形
const REF_SLOT_WIDTH_MM = 12
const REF_SLOT_DEPTH_MM = 1.95
// 3列の穴中心(土台左端からのmm) → 0..1の比率(左端基準)
const REF_COLUMN_RATIOS = [18, 85, 152].map((mm) => mm / REF_BASE_WIDTH_MM)
// 穴は4行。手前端から一番手前の行の中心までが8.975mm、奥端から一番奥の行の中心までも同じ
// (実寸: 行中心が 8.975 / 43.325 / 77.675 / 112.025mm、土台奥行き121mm)
const ROW_COUNT = 4
const rowFrontMargin = 8.975 / REF_CANVAS_WIDTH_MM
// 参考: 実寸の土台奥行きは121mm。previewDepthStep = 0.193 のとき
// (ROW_COUNT - 1) * 0.193 + rowFrontMargin * 2 がこれとほぼ一致する

const baseWidth = REF_BASE_WIDTH_MM / REF_CANVAS_WIDTH_MM
const baseThickness = REF_BASE_THICKNESS_MM / REF_CANVAS_WIDTH_MM
const slotWidth = REF_SLOT_WIDTH_MM / REF_CANVAS_WIDTH_MM
// 実寸1.95mmのまま描画すると3D Preview上ではほぼ潰れて見えなくなるため、
// 見た目の視認性のためだけに前後幅を誇張する(表示専用の倍率。実寸換算には使わない)
const SLOT_DEPTH_VISUAL_SCALE = 4
const slotDepth = (REF_SLOT_DEPTH_MM / REF_CANVAS_WIDTH_MM) * SLOT_DEPTH_VISUAL_SCALE
// 横レール・足の前後方向の厚み。スロットへ差し込む板なので、実寸のスロット幅(1.95mm)に合わせる。
// previewDepthStep から出すと、Layer間隔を変えたときに一緒に太ってしまう
// (2026-09-04、まなみん指摘: 土台の上のレイヤーが太すぎる)
const plateDepth = REF_SLOT_DEPTH_MM / REF_CANVAS_WIDTH_MM

const BASE_COLOR = '#a7724c' // --omoi-brown
const SLOT_COLOR = '#3f2717' // 土台の色よりはっきり濃くして視認性を上げる
// 横レール用の色。土台と同じBASE_COLORだと土台に完全に埋もれて見えなくなる
// (2026-09-04、まなみんのスクリーンショットで確認)ため、あえて別の色にして見分けられるようにする
const RAIL_COLOR = '#c99a5b'

export default function PhysicalBase({ artwork }: { artwork: Artwork }) {
  const canvasHeight = 1 / artwork.canvas.aspectRatio
  const layerIndexes = artwork.layers.map((l) => l.layerIndex)
  const maxLayerIndex = layerIndexes.length > 0 ? Math.max(...layerIndexes) : 0

  // 行の間隔は previewDepthStep に合わせる。こうしておくと、間隔を変えても
  // 「Layer・穴・横レール」が必ず同じ位置で揃う
  // (2026-09-04、まなみん要望: レイヤー同士の間隔を微調整したい)。
  // 土台の奥行きも「行の並び + 手前奥の余白」から出すので、間隔を変えると土台ごと自然に詰まる。
  // previewDepthStep = 0.193 のとき、実物の土台奥行き121mm(=0.6798)とほぼ一致する。
  const rowPitch = previewDepthStep
  const baseDepth = (ROW_COUNT - 1) * rowPitch + rowFrontMargin * 2

  // 土台の手前端。「一番手前のLayerが手前1行目の穴に載る」ように置く。
  // Layerが4枚を超える場合は、はみ出したLayerも土台に載るよう手前側へ広げる。
  const frontRowLayerZ = Math.max(maxLayerIndex, ROW_COUNT - 1) * rowPitch
  const zFront = frontRowLayerZ + rowFrontMargin
  const zBack = zFront - baseDepth
  const baseCenterZ = (zFront + zBack) / 2

  // 手前から rowI 番目(0 = 手前1行目)の行のz
  const rowZ = (rowI: number) => zFront - rowFrontMargin - rowI * rowPitch

  // 土台上面。Canvas下端のすぐ下に置く。ここも previewDepthStep 基準にすると
  // Layer間隔を変えたときに土台が離れていってしまうので、土台の厚み基準にする
  const baseTopY = -canvasHeight / 2 - baseThickness * 0.3
  const baseCenterY = baseTopY - baseThickness / 2

  // layerIndex: 0(背景Layer)以外の前景Layerは、行ごとの横レールで支えられている見た目にする
  const foregroundLayers = artwork.layers.filter((l) => l.layerIndex !== 0)

  // layerIndexが大きい(=手前の)Layerほど、手前の行に割り当てる。
  // 穴は4行までしかないので、Layer数がそれより多い場合は一番奥の行にまとめる
  const rowZForLayerIndex = (layerIndex: number) =>
    rowZ(Math.min(Math.max(maxLayerIndex - layerIndex, 0), ROW_COUNT - 1))

  const railWidth = baseWidth * 0.85
  const railDepth = plateDepth
  // 行全体を貫く低いレール部分の高さ。土台からわずかに立ち上がる程度の低いプロファイルにする
  const railLowThickness = baseThickness * 0.4
  // Layerの中心だけ高くする「足」部分。Layer本体の幅には合わせず、棒くらいの太さで固定する
  const pegSize = baseWidth * 0.05
  // Layerが低いレールのすぐ近くにあっても、見た目の太さが潰れないための最低の高さ
  const pegMinHeight = baseThickness * 1.6

  return (
    <group>
      {/* 土台本体 */}
      <mesh position={[0, baseCenterY, baseCenterZ]}>
        <boxGeometry args={[baseWidth, baseThickness, baseDepth]} />
        <meshBasicMaterial color={BASE_COLOR} />
      </mesh>

      {/* 穴グリッド(4行 x 3列、計12穴の装飾)。細長いスロット形状。土台自体の見た目であり、実Layer数とは独立 */}
      {Array.from({ length: ROW_COUNT }, (_, rowI) =>
        REF_COLUMN_RATIOS.map((colRatio, colI) => {
          const holeX = (colRatio - 0.5) * baseWidth
          const holeZ = rowZ(rowI)
          return (
            <mesh
              key={`hole-${rowI}-${colI}`}
              position={[holeX, baseTopY + 0.0006, holeZ]}
              rotation={[-Math.PI / 2, 0, 0]}
            >
              <planeGeometry args={[slotWidth, slotDepth]} />
              <meshBasicMaterial color={SLOT_COLOR} side={DoubleSide} />
            </mesh>
          )
        }),
      )}

      {/* 前景Layerを支える横レール。行全体を貫く低いレール + Layer中心だけ高くなる棒状の足、の2段構成 */}
      {foregroundLayers.map((layer) => {
        const plane = toLayerPlane(layer, artwork.canvas, previewDepthStep)
        // 穴グリッドと同じ式で行のzを出す(入れ替え時もlayerIndexから毎回計算し直すので、
        // 自動的に正しい行のzへ移動する)
        const railZ = rowZForLayerIndex(layer.layerIndex)

        // 行全体を貫く低いレール
        const lowRailCenterY = baseTopY + railLowThickness / 2

        // Layer中心の位置だけ高くする棒状の足。太さはLayerに依らず固定、xだけLayerに追従する。
        // yを変えたときは、Layer本体の下端まで届くように足の高さも変わる(繋がって見えるようにする)
        const lowRailTopY = baseTopY + railLowThickness
        const layerBottomY = plane.y3d - plane.height / 2
        const pegTopY = Math.max(layerBottomY, lowRailTopY + pegMinHeight)
        const pegHeight = pegTopY - lowRailTopY
        const pegCenterY = (lowRailTopY + pegTopY) / 2
        const pegX = Math.max(
          Math.min(plane.x3d, railWidth / 2 - pegSize / 2),
          -railWidth / 2 + pegSize / 2,
        )

        return (
          <group key={`rail-${layer.layerId}`}>
            <mesh position={[0, lowRailCenterY, railZ]}>
              <boxGeometry args={[railWidth, railLowThickness, railDepth]} />
              <meshBasicMaterial color={RAIL_COLOR} />
            </mesh>
            <mesh position={[pegX, pegCenterY, railZ]}>
              <boxGeometry args={[pegSize, pegHeight, plateDepth]} />
              <meshBasicMaterial color={RAIL_COLOR} />
            </mesh>
          </group>
        )
      })}
    </group>
  )
}