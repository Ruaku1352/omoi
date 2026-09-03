import './GeneratingScreen.css'
import MomoMascot from '../components/MomoMascot'
import type { JobStage } from '../types/job'

/**
 * 生成中の待ち画面。
 *
 * `stage` は `GET /api/v1/jobs/{jobId}` が返す処理段階
 * （contracts/job-status-response.schema.json）。
 * 内部処理名をそのまま出さず、ここでユーザー向け文言へ変換する。
 * Backend が stage を返さないこともあるので、未指定でも成立させる。
 */
const STAGE_TEXT: Record<JobStage, string> = {
  analyzing: '写真を読み取っています。',
  extracting: '思い出を表すものを探しています。',
  composing: '作品を組み立てています。',
  finalizing: '仕上げをしています。',
}

export default function GeneratingScreen({
  photoCount,
  stage,
}: {
  photoCount?: number
  stage?: JobStage
}) {
  const title = stage ? STAGE_TEXT[stage] : '思い出を重ねています。'

  return (
    <div className="gen">
      <div className="gen-stage">
        <div className="gen-card">
          <div className="gen-text">
            <h2 className="gen-title">{title}</h2>
            <p className="gen-lead">
              {photoCount ? `${photoCount}枚の写真` : '選んだ写真'}
              から象徴的な要素を選び、前後の奥行きを組み立てています。
            </p>
            <p className="gen-lead">
              作品ができるまで数分かかります。そのままお待ちください。
            </p>
          </div>
          <MomoMascot />
        </div>
      </div>
    </div>
  )
}
