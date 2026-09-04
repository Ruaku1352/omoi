# frontend — Firebase Hosting Deploy Unit

React 19.2 + TypeScript + Vite 8 の Static SPA。Node.js 24 LTS系（`.nvmrc`）。
3D Preview は three + @react-three/fiber v9系、2D Edit は konva + react-konva。

実装前提は `/AGENTS.md` §6・§7 と `/skills/frontend/SKILL.md`。
Artwork Data の正本は `/contracts/artwork.schema.json`。

## セットアップ

```bash
npm install
npm run dev        # Vite Dev Server
npm run typecheck  # tsc -b
npm run lint       # oxlint
npm run test       # vitest（共通Mockを Fixture にした契約テスト）
npm run build      # tsc -b && vite build → dist/
```

Backendの接続先は `.env` の `VITE_API_BASE_URL` で切り替える。
Key名は Repository Root の `.env.example` を参照（`.env` はCommitしない）。

```bash
cp ../.env.example .env
```

ローカルからCloud Runを直接叩くときは、Backend側の `CORS_ORIGINS` に含まれるOriginで
Viteを起動し、`VITE_API_BASE_URL` にCloud RunのBase URLを入れる。

```bash
VITE_API_BASE_URL=https://omoi-backend-mqq6yxxfoq-an.a.run.app npm run dev -- --host localhost --port 5173
```

2026-09-02時点のCloud Run Mockは `POST /api/v1/artworks/generate` で同期の
生成成功Responseを返す。一方、非同期Backendでは `jobId` を返して
`GET /api/v1/jobs/{jobId}` をPollingする。移行中に画面確認が止まらないよう、
Frontendはこの2種類をどちらも受ける。

Cloud RunのUpload制限に当たらないよう、Frontendは送信直前に
`src/image/resizeImage.ts` で画像を長辺2048px・JPEG品質0.85へ変換する。
プレビュー表示は選択された元画像をそのまま使い、Backendへ送るPayloadだけを軽くする。

## 現在の状態

写真選択、生成中、3D Preview、微調整、完成画面までの画面PoCを持つ。
完成画面のBundle ZIP出力は、確定Artwork Data + Assetsを手渡し検証するための
補助機能であり、STL / PDF / JPEG / G-codeはFrontendでは生成しない。

物理出力の正本はBackend/FastAPI側の `POST /api/v1/physical-output/exports`。
Frontendは確定Artwork Data + Assetsを渡し、Backendが3Dプリンター用STL ZIP、
2L写真紙用PDF、またはコンビニ2L写真プリント用JPEG ZIPを返す。

```
src/
├─ App.tsx              # 写真選択から完成までの画面遷移
├─ api/                 # Backend API境界
│  ├─ generateArtwork.ts  #   POST /api/v1/artworks/generate / Jobs Polling
│  └─ errors.ts           #   AGENTS.md §4 の Error形式
├─ artwork/             # Artwork Data を扱う純粋関数
│  ├─ assetIndex.ts       #   assetId → URL（Asset Manifest経由）
│  ├─ geometry.ts         #   正規化座標 ↔ 3D / Pixel 変換（AGENTS.md §7 の式）
│  └─ layerOrder.ts       #   layerIndex のソートと 0..N-1 再正規化
├─ bundle/              # 検証用Artwork Data + Assets ZIP。STL/PDFは生成しない
├─ components/          # 共通UI
├─ config/
│  ├─ artworkEditing.ts   #   minScale / maxScale / previewDepthStep【PoC後FIX】
│  └─ env.ts              #   VITE_ 環境変数の読み口
├─ edit/                # 2D微調整UI
├─ image/               # Backend送信用の画像リサイズ
├─ mock/                # 開発中の動作確認用。Real失敗時のFallback経路にしない
│  └─ mockArtwork.ts      #   contracts/mock + contracts/assets を読む
├─ preview/             # Three.js Preview
├─ screens/             # 画面単位のUI
└─ types/               # contracts/ Schema の写像
   ├─ artwork.ts
   ├─ assetManifest.ts
   └─ generateResponse.ts  # 生成成功Response（上2つを束ねるだけ・再定義しない）
```

共通Mockは `frontend/` 配下へコピーせず、Repository Root の `contracts/` を直接読む
（`vite.config.ts` の `server.fs.allow`）。正本を二重に持たないため。

## 守ること

- 3D Preview は Read Only。Artwork Data を書き換えない
- Pixel座標は描画時のみ。保存時は正規化 `x` / `y` / `scale` へ戻す（`artwork/geometry.ts`）
- `assetId` → URL は必ず Asset Manifest 経由。Artwork Data 内にURLを期待しない
- 生成成功Responseの形は `/contracts/generate-success-response.schema.json` に従う。
  Frontend側で独自のResponse型を正本にしない。
  外側のKey名は【確認待ち：チーム】なので `src/types/generateResponse.ts` に閉じ込めてある
- `layers[]` / `sourcePhotos[]` を固定長として扱わない。配列位置に意味を持たせない
- 2D Edit 後にAIを呼ばない。更新後の Artwork Data からロジックベースで再描画する
- MockかRealかで Artwork の解釈を分岐させない
- 【PoC後FIX】の数値を各Componentへ書かない。`config/artworkEditing.ts` に集約する
- Frontendから直接 Gemini Developer API を叩かない
- FrontendでSTL / PDF / G-codeを生成しない。必要な場合はBackendのPhysical Output APIを呼ぶ
- 差し込み番号や土台Previewを追加する場合も表示用に閉じ、最終的な出力物はBackendの生成結果を正とする
