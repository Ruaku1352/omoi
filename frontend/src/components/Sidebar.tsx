import iconCube from '../assets/icon-cube.svg'
import iconSwap from '../assets/icon-swap.svg'
import iconLayer from '../assets/icon-layer.svg'
import './Sidebar.css'

export default function Sidebar({
  onSelect,
}: {
  onSelect: (next: 'preview' | 'edit') => void
}) {
  return (
    <aside className="sidebar">
      <button type="button" className="sidebar-btn" onClick={() => onSelect('preview')}>
        <img src={iconCube} alt="プレビュー" />
      </button>
      <img className="sidebar-swap" src={iconSwap} alt="" />
      <button type="button" className="sidebar-btn" onClick={() => onSelect('edit')}>
        <img src={iconLayer} alt="レイヤー" />
      </button>
    </aside>
  )
}