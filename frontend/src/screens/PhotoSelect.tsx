import { useState } from 'react'
import { ApiError } from '../api/errors'
import { generateArtwork } from '../api/generateArtwork'
import type { Artwork } from '../types/artwork'
import type { AssetManifest } from '../types/assetManifest'

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
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

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
    <section style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>
      <h2>S01 写真選択（仮）</h2>

      <input
        type="file"
        accept="image/*"
        multiple
        onChange={(e) => setPhotos(Array.from(e.target.files ?? []))}
      />
      <p>{photos.length} 枚選択中</p>

      <input
        type="text"
        placeholder="こんな思い出（任意）"
        value={memoryText}
        onChange={(e) => setMemoryText(e.target.value)}
      />

      <button
        type="button"
        onClick={handleGenerate}
        disabled={photos.length === 0 || loading}
      >
        {loading ? '作品を作っています…' : '作品を作る'}
      </button>

      {error && <p style={{ color: 'salmon' }}>{error}</p>}
    </section>
  )
}