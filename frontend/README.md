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

## 現在の状態

Scaffold + 共通Contractの型・変換 + **動作確認ページ**まで。
`npm run dev` で共通Mockの `layers[]` が `layerIndex` 昇順（0が最背面）で一覧表示される。

3D Preview / 2D Edit は未実装。`skills/frontend/SKILL.md` の実装順で積んでいく。

```
src/
├─ App.tsx              # 動作確認ページ（Mockのlayer一覧。3D / 2D の本実装ではない）
├─ api/                 # Backend API境界
│  ├─ generateArtwork.ts  #   POST /api/v1/artworks/generate（唯一FIXのEndpoint）
│  └─ errors.ts           #   AGENTS.md §4 の Error形式
├─ artwork/             # Artwork Data を扱う純粋関数
│  ├─ assetIndex.ts       #   assetId → URL（Asset Manifest経由）
│  ├─ geometry.ts         #   正規化座標 ↔ 3D / Pixel 変換（AGENTS.md §7 の式）
│  └─ layerOrder.ts       #   layerIndex のソートと 0..N-1 再正規化
├─ config/
│  ├─ artworkEditing.ts   #   minScale / maxScale / previewDepthStep【PoC後FIX】
│  └─ env.ts              #   VITE_ 環境変数の読み口
├─ mock/                # 開発中の動作確認用。Real失敗時のFallback経路にしない
│  └─ mockArtwork.ts      #   contracts/mock + contracts/assets を読む
└─ types/               # contracts/ Schema の写像
   ├─ artwork.ts
   └─ assetManifest.ts
```

共通Mockは `frontend/` 配下へコピーせず、Repository Root の `contracts/` を直接読む
（`vite.config.ts` の `server.fs.allow`）。正本を二重に持たないため。

## 守ること

- 3D Preview は Read Only。Artwork Data を書き換えない
- Pixel座標は描画時のみ。保存時は正規化 `x` / `y` / `scale` へ戻す（`artwork/geometry.ts`）
- `assetId` → URL は必ず Asset Manifest 経由。Artwork Data 内にURLを期待しない
- `layers[]` / `sourcePhotos[]` を固定長として扱わない。配列位置に意味を持たせない
- 2D Edit 後にAIを呼ばない。更新後の Artwork Data からロジックベースで再描画する
- MockかRealかで Artwork の解釈を分岐させない
- 【PoC後FIX】の数値を各Componentへ書かない。`config/artworkEditing.ts` に集約する
- Frontendから直接 Gemini Developer API を叩かない
