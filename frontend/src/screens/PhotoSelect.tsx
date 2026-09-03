import { useEffect, useMemo, useState } from 'react'
import { ApiError } from '../api/errors'
import { generateArtwork } from '../api/generateArtwork'
import type { Artwork } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'
import type { JobStage } from '../types/job'
import { resizeImage } from '../image/resizeImage'
import iconUpload from '../assets/icon-upload.svg'
import iconCompose from '../assets/icon-compose.svg'
import iconLayer from '../assets/icon-layer.svg'
import iconRemove from '../assets/icon-remove.svg'
import './PhotoSelect.css'

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

  const previews = useMemo(() => photos.map((file) => URL.createObjectURL(file)), [photos])

  useEffect(() => {
    return () => {
      previews.forEach((url) => URL.revokeObjectURL(url))
    }
  }, [previews])

  const removePhoto = (index: number) => {
    setPhotos(photos.filter((_, i) => i !== index))
  }

  const addPhotos = (files: FileList | File[]) => {
    const added = Array.from(files).filter((f) => f.type.startsWith('image/'))
    setPhotos((prev) => [...prev, ...added].slice(0, 10))
  }

  const handleGenerate = async () => {
    onStart()
    try {
      const uploads = await Promise.all(
        photos.map(async (file) => {
          try {
            return await resizeImage(file)
          } catch {
            return file
          }
        }),
      )
      const result = await generateArtwork({ photos: uploads, memoryText, onProgress })
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
            {hasPhotos ? '写真をドラッグしてアップロード' : '写真をドロップ、または選ぶ'}
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