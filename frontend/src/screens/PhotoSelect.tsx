import { useEffect, useMemo, useState } from 'react'
import heic2any from 'heic2any'
import { ApiError } from '../api/errors'
import { generateArtwork } from '../api/generateArtwork'
import type { Artwork } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'
import type { JobStage } from '../types/job'
import iconUpload from '../assets/icon-upload.svg'
import iconCompose from '../assets/icon-compose.svg'
import iconLayer from '../assets/icon-layer.svg'
import iconRemove from '../assets/icon-remove.svg'
import './PhotoSelect.css'

// iPhone由来のHEIC/HEIFはブラウザによって<img>で表示できない（Android/Windows等）ため、
// 選択直後にJPEGへ変換してから扱う。バックエンドの受け付け基準（JPEG/PNG/WebP）にも合わせる。
const isHeic = (file: File) => {
  const type = file.type.toLowerCase()
  const name = file.name.toLowerCase()
  return type === 'image/heic' || type === 'image/heif' || name.endsWith('.heic') || name.endsWith('.heif')
}

const isImageFile = (file: File) => file.type.startsWith('image/') || isHeic(file)

const convertHeicIfNeeded = async (file: File): Promise<File> => {
  if (!isHeic(file)) return file
  try {
    const converted = await heic2any({ blob: file, toType: 'image/jpeg', quality: 0.9 })
    const blob = Array.isArray(converted) ? converted[0] : converted
    const newName = file.name.replace(/\.(heic|heif)$/i, '.jpg')
    return new File([blob], newName, { type: 'image/jpeg' })
  } catch (e) {
    console.error('HEIC変換に失敗しました:', file.name, e)
    return file
  }
}

// スマホの写真（特にHEICから変換した直後のもの）はそのまま送るとCloud Runの
// リクエストサイズ上限（32MB・固定）に引っかかることがあるため、最長辺を
// MAX_DIMENSION に収まるまで縮小し、JPEGへ再圧縮してからアップロードする。
const MAX_DIMENSION = 2048
const JPEG_QUALITY = 0.85

const resizeIfNeeded = async (file: File): Promise<File> => {
  try {
    const bitmap = await createImageBitmap(file)
    const { width, height } = bitmap
    if (width <= MAX_DIMENSION && height <= MAX_DIMENSION) {
      bitmap.close()
      return file
    }
    const scale = MAX_DIMENSION / Math.max(width, height)
    const targetWidth = Math.round(width * scale)
    const targetHeight = Math.round(height * scale)
    const canvas = document.createElement('canvas')
    canvas.width = targetWidth
    canvas.height = targetHeight
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      bitmap.close()
      return file
    }
    ctx.drawImage(bitmap, 0, 0, targetWidth, targetHeight)
    bitmap.close()
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', JPEG_QUALITY),
    )
    if (!blob) return file
    const newName = file.name.replace(/\.\w+$/, '.jpg')
    return new File([blob], newName, { type: 'image/jpeg' })
  } catch (e) {
    console.error('画像の圧縮に失敗しました:', file.name, e)
    return file
  }
}

const prepareForUpload = async (file: File): Promise<File> => {
  const displayable = await convertHeicIfNeeded(file)
  return resizeIfNeeded(displayable)
}

export default function PhotoSelect({
  onGenerated,
  onStart,
  onFailed,
  onProgress,
}: {
  onGenerated: (artwork: Artwork, assetManifest: AssetManifest) => void
  onStart: () => void
  onFailed: (message: string) => void
  onProgress?: (progress: { status: 'pending' | 'processing'; stage?: JobStage }) => void
}) {
  const [photos, setPhotos] = useState<File[]>([])
  const [memoryText, setMemoryText] = useState('')
  const [isDragOver, setIsDragOver] = useState(false)
  const [isConverting, setIsConverting] = useState(false)

  const previews = useMemo(() => photos.map((file) => URL.createObjectURL(file)), [photos])

  useEffect(() => {
    return () => {
      previews.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [previews])

  const removePhoto = (index: number) => {
    setPhotos(photos.filter((_, i) => i !== index))
  }

  const addPhotos = async (files: FileList | File[]) => {
    const incoming = Array.from(files).filter(isImageFile)
    if (incoming.length === 0) return
    setIsConverting(true)
    try {
      const prepared = await Promise.all(incoming.map(prepareForUpload))
      setPhotos((prev) => [...prev, ...prepared].slice(0, 10))
    } finally {
      setIsConverting(false)
    }
  }

  const handleGenerate = async () => {
    onStart()
    try {
      const result = await generateArtwork({ photos, memoryText, onProgress })
      onGenerated(result.artwork, result.assetManifest)
    } catch (e) {
      onFailed(e instanceof ApiError ? e.message : '通信に失敗しました。')
    }
  }

  const hasPhotos = photos.length > 0

  return (
    <>
      <section className="s01">
        <div
          className={`s01-drop${isDragOver ? ' s01-drop-over' : ''}`}
          onDragOver={(e) => {
            e.preventDefault()
            setIsDragOver(true)
          }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={(e) => {
            e.preventDefault()
            setIsDragOver(false)
            addPhotos(e.dataTransfer.files)
          }}
        >
          {hasPhotos ? (
            <div className="s01-grid">
              {photos.map((file, i) => (
                <div className="s01-cell" key={`${file.name}-${i}`}>
                  <div className="s01-thumb">
                    <img src={previews[i]} alt="" />
                    <button
                      type="button"
                      className="s01-remove"
                      onClick={() => removePhoto(i)}
                      aria-label={`${file.name} を取り消す`}
                    >
                      <img src={iconRemove} alt="" />
                    </button>
                  </div>
                  <span className="s01-name">{file.name}</span>
                </div>
              ))}
            </div>
          ) : (
            <>
              <h1 className="s01-title">思い出の写真をレイヤーアートに変換</h1>
              <p className="s01-lead">思い出が写った写真を数枚を選んでアップロードしてください</p>
            </>
          )}

          <input
            id="photo-input"
            type="file"
            accept="image/*"
            multiple
            hidden
            onChange={(e) => {
              addPhotos(e.target.files ?? [])
              e.target.value = ''
            }}
          />
          <label htmlFor="photo-input" className={hasPhotos ? 's01-btn s01-btn-more' : 's01-btn'}>
            <img src={iconUpload} alt="" />
            {isConverting
              ? '変換中…'
              : hasPhotos
                ? '写真をドラッグしてアップロード'
                : '写真をドロップ、または選ぶ'}
          </label>
        </div>

        <div className="s01-bottom">
          <input
            className="s01-memo"
            type="text"
            placeholder="こんな思い出：海に行った夏の日、犬とはじめての散歩（任意）"
            value={memoryText}
            onChange={(e) => setMemoryText(e.target.value)}
          />
          <button
            type="button"
            className="s01-btn s01-btn-primary"
            onClick={handleGenerate}
            disabled={!hasPhotos}
          >
            <img src={iconCompose} alt="" />
            作品を作る
          </button>
        </div>
      </section>

      <section className="s01-howto">
        <h2 className="s01-howto-title">レイヤーアートの作り方</h2>
        <div className="s01-cards">
          <div className="s01-card">
            <div className="s01-card-head">
              <img src={iconUpload} alt="" />
              <span>えらぶ</span>
            </div>
            <p>ページ上部のドロップゾーンに、思い出の写真を数枚（最大10枚）アップロード</p>
          </div>

          <div className="s01-card">
            <div className="s01-card-head">
              <img src={iconCompose} alt="" />
              <span>ととのえる</span>
            </div>
            <p>AIが自動構成した3Dプレビューを見て、気になる所だけ微調整</p>
          </div>

          <div className="s01-card">
            <div className="s01-card-head">
              <img src={iconLayer} alt="" />
              <span>かたちにする</span>
            </div>
            <p>確定すると、2.5Dのレイヤーアートになって届く</p>
          </div>
        </div>
      </section>
    </>
  )
}