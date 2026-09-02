import './GeneratingScreen.css'

export default function GeneratingScreen({ photoCount }: { photoCount?: number }) {
  return (
    <div className="gen">
      <div className="gen-stage">
        <div className="gen-card">
          <div className="gen-text">
            <h2 className="gen-title">思い出を重ねています。</h2>
            <p className="gen-lead">
              {photoCount ? `${photoCount}枚の写真` : '選んだ写真'}
              から象徴的な要素を選び、前後の奥行きを組み立てています。
            </p>
            <p className="gen-lead">高品質なデータを生成しています。30秒ほどお待ちください。</p>
          </div>
          <div className="gen-spinner" />
        </div>
      </div>
    </div>
  )
}