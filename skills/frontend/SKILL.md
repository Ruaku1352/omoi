---
name: frontend
description: React / Vite の Frontend、3D Preview、2D Edit、Artwork Working Copy、Backend API接続を実装するときに使う。Component構成、Three.js / R3F、Konva、進捗表示、Asset Manifest によるURL解決を扱う場合に参照する。
---

# frontend

前提は `/AGENTS.md` §6, §7。Schemaは `/contracts/artwork.schema.json`。

## Stack
TypeScript / React 19.2系 / Vite 8系 / Node 24 LTS。
3Dは `three` + `@react-three/fiber` v9系、2Dは `konva` + `react-konva`。
Router / 状態管理 / CSS方式 / Component分割は担当裁量。

## 実装順（Real API を待たない）
1. `contracts/mock/artwork.json` を読み込んで型を起こす
2. `layerIndex` 昇順でPlaneを並べて3D Previewを描画する
3. Konvaで2D Editを作り、編集結果をWorking Copyへ反映する
4. 3Dへ戻って再描画できることを確認する（**AIは呼ばない**）
5. 最後に `POST /api/v1/artworks/generate` へ差し替える。
   成功Responseの形は `contracts/generate-success-response.schema.json`（`{artwork, assetManifest}`）。
   `VITE_API_BASE_URL` で接続先を切り替える

## 守ること
- 3D Preview は Read Only。Artwork Data を書き換えない
- Pixel座標は描画時のみ。保存時は正規化 `x` / `y` / `scale` へ戻す
- `assetId` → URL の解決は **Asset Manifest** 経由。Artwork Data 内にURLを期待しない
- MockかRealかで Artwork の解釈を分岐させない
- 進捗はユーザー向け文言へMappingする。内部処理名をそのまま出さない
- 実処理時間と一致しない疑似progress %を共通契約にしない
- `minScale` / `maxScale` は【PoC後FIX】。定数を一箇所に集約し、各Componentへ散在させない
