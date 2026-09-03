import { useState } from 'react'
import Sidebar from '../components/Sidebar'
import Breadcrumb from '../components/Breadcrumb'
import LayerPanel from '../components/LayerPanel'
import ArtworkEditor from '../edit/ArtworkEditor'
import type { AssetIndex } from '../artwork/assetIndex'
import type { Artwork } from '../types/artwork'
import type { Screen } from '../App'
import './screen.css'

type Props = {
  artwork: Artwork
  assets: AssetIndex
  onChange: (artwork: Artwork) => void
  onSelectScreen: (screen: Screen) => void
}

export default function EditScreen({ artwork, assets, onChange, onSelectScreen }: Props) {
  const [selectedLayerId, setSelectedLayerId] = useState<string | null>(null)

  return (
    <div className="screen">
      <Sidebar onSelect={onSelectScreen} />
      <div className="screen-main">
        <div className="screen-top">
          <Breadcrumb current="edit" />
          <div className="screen-actions">
            <button type="button" className="btn-fill" onClick={() => onSelectScreen('preview')}>
              編集を終わる
            </button>
          </div>
        </div>
        <ArtworkEditor
          artwork={artwork}
          assets={assets}
          onChange={onChange}
          selectedId={selectedLayerId}
          onSelectId={setSelectedLayerId}
        />
      </div>
      <LayerPanel
        artwork={artwork}
        onChange={onChange}
        selectedLayerId={selectedLayerId}
        onSelectLayer={setSelectedLayerId}
      />
    </div>
  )
}