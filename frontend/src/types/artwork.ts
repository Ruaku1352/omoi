/**
 * Artwork Data の型。正本は `/contracts/artwork.schema.json`。
 *
 * ここはSchemaの写像であって別の正本ではない。Schemaが変わったら同一PRで追随する。
 * Field名の読み替え・独自Fieldの追加をFrontend側で行わないこと（AGENTS.md §3, §9）。
 */

/** Asset の MIME Type。Layer Asset は image/png（RGBA）固定。 */
export type AssetMimeType = 'image/png' | 'image/jpeg' | 'image/webp'

/**
 * Binary本体は持たず識別子とMetadataのみを持つ。
 * URLはここに無い。解決は Asset Manifest 経由（AGENTS.md §3.3）。
 */
export interface AssetRef {
  assetId: string
  mimeType: AssetMimeType
  widthPx: number
  heightPx: number
}

/** 透過Layer Asset。RGBA PNG固定。 */
export interface LayerAssetRef extends AssetRef {
  mimeType: 'image/png'
}

export interface SourcePhoto {
  sourcePhotoId: string
  asset: AssetRef
}

/**
 * 差し替え候補。差し替え時は x / y / scale / layerIndex を維持し、
 * sourcePhotoId / sourceLayerId / asset / label を置き換える（AGENTS.md §7）。
 */
export interface ReplacementCandidate {
  candidateId: string
  sourcePhotoId: string
  sourceLayerId: string
  asset: LayerAssetRef
  label: string
}

export interface Layer {
  layerId: string
  sourcePhotoId: string
  sourceLayerId: string
  asset: LayerAssetRef
  /** 人間が確認できる短い意味Label。 */
  label: string
  /** Layer中心のX。0.0〜1.0。原点はCanvas左上、右方向が正。 */
  x: number
  /** Layer中心のY。0.0〜1.0。原点はCanvas左上、下方向が正。 */
  y: number
  /** Layer表示幅 / Canvas幅。高さは asset の Aspect Ratio から導出する。 */
  scale: number
  /** 奥行き順。0が最背面。配列位置とは無関係。 */
  layerIndex: number
  replacementCandidates: ReplacementCandidate[]
}

export interface ArtworkCanvas {
  /** Canvas幅 / Canvas高さ。固定値にしない。 */
  aspectRatio: number
}

/** 物理出力のmode表明のみ。mm値等の製造条件はここに持たない。 */
export interface PhysicalOutput {
  mode: string
}

export interface Artwork {
  schemaVersion: string
  artworkId: string
  canvas: ArtworkCanvas
  /** 可変長。固定5枚と仮定しない。 */
  sourcePhotos: SourcePhoto[]
  /** 可変長。配列位置に前景/中景/背景の意味を持たせない。 */
  layers: Layer[]
  physicalOutput?: PhysicalOutput
}
