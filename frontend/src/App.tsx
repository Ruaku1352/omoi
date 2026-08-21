import './App.css'
import { apiBaseUrl, useMock } from './config/env'

/**
 * Scaffold時点のPlaceholder。
 *
 * 画面（写真選択 / 進捗表示 / 3D Preview / 2D Edit）は Frontend担当が
 * `skills/frontend/SKILL.md` の実装順に沿って積む。ここで先回りしない。
 */
export default function App() {
  return (
    <main className="app">
      <h1>omoi</h1>
      <p className="tagline">Our Memories, One Image</p>

      <p>Frontend Scaffold のみ。画面はこれから実装する。</p>

      <dl>
        <dt>API Base URL</dt>
        <dd>
          <code>{apiBaseUrl === '' ? '(未設定 / 同一Origin相対)' : apiBaseUrl}</code>
        </dd>
        <dt>VITE_USE_MOCK</dt>
        <dd>
          <code>{String(useMock)}</code>
        </dd>
      </dl>
    </main>
  )
}
