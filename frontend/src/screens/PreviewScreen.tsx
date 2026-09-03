import Breadcrumb from '../components/Breadcrumb'
import Sidebar from '../components/Sidebar'
import ArtworkPreview from '../preview/ArtworkPreview'
import type { AssetIndex } from '../artwork/assetIndex'
import type { Artwork } from '../types/artwork'
import iconCompose from '../assets/icon-compose.svg'
import './screen.css'

export default function PreviewScreen({
  artwork,
  assets,
  onSelectScreen,
}: {
  artwork: Artwork
  assets: AssetIndex
  onSelectScreen: (next: 'preview' | 'edit' | 'done') => void
}) {
  return (
    <div className="screen">
      <Sidebar onSelect={onSelectScreen} />

      <div className="screen-main">
        <div className="screen-top">
          <Breadcrumb current="preview" />
          <div className="screen-actions">
            <button type="button" className="btn-outline" onClick={() => onSelectScreen('edit')}>
              微調整する
            </button>
            <button type="button" className="btn-fill" onClick={() => onSelectScreen('done')}>
              <img src={iconCompose} alt="" />
              この作品で完成
            </button>
          </div>
        </div>

        <ArtworkPreview artwork={artwork} assets={assets} />
      </div>
    </div>
  )
}