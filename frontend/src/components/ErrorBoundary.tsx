import { Component, type ReactNode } from 'react'
import './ErrorBoundary.css'

type Props = {
  children: ReactNode
  onReset: () => void
}

type State = {
  error: Error | null
}

/**
 * 描画中(render中)に起きた例外を捕まえて、画面が真っ白になるのを防ぐ。
 *
 * 例: Asset Manifest に該当 assetId が無い場合、resolveAssetUrl() が
 * render中に例外を投げる（artwork/assetIndex.ts）。これを補足せずにいると
 * Reactがツリーごとアンマウントし、真っ白な画面になってしまう。
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: { componentStack: string }) {
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  handleReset = () => {
    this.setState({ error: null })
    this.props.onReset()
  }

  render() {
    if (this.state.error) {
      return (
        <div className="eb">
          <div className="eb-card">
            <h2 className="eb-title">表示中にエラーが発生しました</h2>
            <p className="eb-lead">
              作品データの読み込み中に問題が起きたため、この画面を表示できませんでした。
              <br />
              お手数ですが、最初からやり直してください。
            </p>
            <p className="eb-detail">{this.state.error.message}</p>
            <button type="button" className="eb-btn" onClick={this.handleReset}>
              写真選択に戻る
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}