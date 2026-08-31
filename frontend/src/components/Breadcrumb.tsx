import './Breadcrumb.css'

const STEPS = [
  { key: 'select', label: '写真' },
  { key: 'generating', label: '生成' },
  { key: 'preview', label: 'プレビュー' },
  { key: 'edit', label: '微調整' },
  { key: 'done', label: '完成' },
]

export default function Breadcrumb({ current }: { current: string }) {
  return (
    <nav className="breadcrumb">
      {STEPS.map((step, i) => (
        <span key={step.key} style={{ display: 'flex', gap: 9 }}>
          {i > 0 && <span className="breadcrumb-sep">›</span>}
          <span className={step.key === current ? 'breadcrumb-step is-current' : 'breadcrumb-step'}>
            {step.label}
          </span>
        </span>
      ))}
    </nav>
  )
}