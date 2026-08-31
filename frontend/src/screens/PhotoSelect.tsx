import { useState } from 'react'
import { ApiError } from '../api/errors'
import { generateArtwork } from '../api/generateArtwork'
import type { Artwork } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'
import iconUpload from '../assets/icon-upload.svg'
import iconCompose from '../assets/icon-compose.svg'
import './PhotoSelect.css'
import iconLayer from '../assets/icon-layer.svg'

export default function PhotoSelect({
  onGenerated,
  onStart,
  onFailed,
}: {
  onGenerated: (artwork: Artwork, assetManifest: AssetManifest) => void
  onStart: () => void
  onFailed: (message: string) => void
}) {
  const [photos, setPhotos] = useState<File[]>([])
  const [memoryText, setMemoryText] = useState('')

  const handleGenerate = async () => {
    onStart()
    try {
      const result = await generateArtwork({ photos, memoryText })
      onGenerated(result.artwork, result.assetManifest)
    } catch (e) {
      onFailed(e instanceof ApiError ? e.message : '通信に失敗しました。')
    }
  }

  return (
    <>
    <section className="s01">
      <div className="s01-drop">
        <h1 className="s01-title">思い出の写真をレイヤーアートに変換</h1>
        <p className="s01-lead">思い出が写った写真を数枚を選んでアップロードしてください</p>

        <input
          id="photo-input"
          type="file"
          accept="image/*"
          multiple
          hidden
          onChange={(e) => setPhotos(Array.from(e.target.files ?? []))}
        />
        <label htmlFor="photo-input" className="s01-btn">
          <img src={iconUpload} alt="" />
          写真をドロップ、または選ぶ
        </label>

        {photos.length > 0 && <p className="s01-lead">{photos.length} 枚選択中</p>}
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
          className="s01-btn"
          onClick={handleGenerate}
          disabled={photos.length === 0}
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