/**
 * `heic2any` は型定義を同梱していないため、最小限の型を用意する。
 * HEIC/HEIF の写真をブラウザ標準では表示できないため（AGENTS.md §4のHEIC/HEIF注記）、
 * 選択直後にJPEGへ変換してからプレビュー・アップロードに使う。
 */
declare module 'heic2any' {
  interface Heic2AnyOptions {
    blob: Blob
    toType?: string
    quality?: number
    multiple?: boolean
  }
  export default function heic2any(options: Heic2AnyOptions): Promise<Blob | Blob[]>
}