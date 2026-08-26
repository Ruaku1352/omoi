# AGENTS.md

このRepositoryで作業するAI Coding Agentが**最初に読む共通入口**。
人間向けの共通技術仕様の正本はDriveの「技術設計」。本ファイルはそのコピーではなく、
実装時に必要な要約・参照先・禁止事項を持つ。齟齬があった場合はDriveの「技術設計」が優先。

Machine Readableな契約の正本は `contracts/` — `artwork.schema.json` /
`asset-manifest.schema.json` / `generate-success-response.schema.json` と `contracts/mock/`。

人間側の入口はRepositoryではなくDrive。全体像は「ドパガキ向け_5分でわかる設計理解」。

---

## 0. 状態ラベルの読み方【最重要】

このファイル中の各項目には状態ラベルが付いている。**Agentはこれを勝手に昇格させてはならない。**

| ラベル | 意味 | Agentの振る舞い |
|---|---|---|
| **【FIX】** | 確定。この前提で実装する | そのまま実装する。変更提案は可、独断変更は不可 |
| **【仮決定】** | 当面のP0開発前提。検証後に最終FIX | 実装してよいが、切り替え可能な形にする |
| **【確認待ち：担当名】** | 初案。関係者が確認してからFIXする | 実装してよいが**FIX扱いにしない**。変える提案が来たら追随する |
| **【PoC後FIX】** | 検証結果を見て決める | **値をハードコードして確定扱いにしない**。環境変数・設定に逃がす |
| **【未決定】** | 現時点で固定しない | **Directory / Service / Endpoint を先回りで作らない** |
| **【担当裁量】** | 担当者が決めてよい | 自由に決めてよい |

Driveの「技術設計」§2 とはラベル名が一部違う。意味は同じなので対応表で読む。

| 本ファイル | Drive「技術設計」 |
|---|---|
| 【未決定】 | 【検討中】 |

「たぶん必要だから」で【未決定】のものを作らないこと。実際に必要になった時点で追加する。

---

## 1. プロダクト

**omoi**（Our Memories, One Image）。複数の写真から、思い出を象徴する要素を抽出して
1つの多層作品を作り、最終的に3Dプリンターで2.5Dの物理作品にする。

### P0 End-to-End Flow【FIX】

```
複数写真 + 任意テキスト
  → AIが写真群の意味理解
  → レイヤー候補の分割・抽出
  → 象徴要素の自動選定
  → x / y / scale / layerIndex の自動構成
  → 3D完成プレビュー（Read Only）
  → 必要時のみ2D編集
  → 作品確定
  → 2.5D物理出力（3Dプリンター）
```

---

## 2. Architecture

### 2.1 Runtime / Deploy【仮決定】

Firebase Hosting（Frontend）+ Cloud Run（Backend + AI）の2 Deploy Unit。

- Frontend: React / Vite の Static SPA → Firebase Hosting
- Backend: FastAPI → Cloud Run。**AI・画像処理は `backend/ai/` の内部Module**
- 別Originのため CORS 許可Originを環境変数で管理する【FIX】
- FrontendはCloud Runの生成APIを**直接HTTPS**で呼ぶ。Firebase Hosting Rewriteを必須経路にしない【FIX】

### 2.2 Repository構成【FIX】

Top Levelは担当者別ではなく、**「一緒にBuild / Deploy / 実行される単位」**と
**「複数Unitから共有されるContract / 開発基盤」**で切る。

```
/
├─ frontend/          # Firebase Hosting Deploy Unit
├─ backend/           # Cloud Run Deploy Unit
│  └─ ai/             #   AI・画像処理Module（独立Serviceにしない）
├─ contracts/         # Deploy Unitを跨ぐ共通Contract
├─ skills/            # AI Coding Agent向け開発基盤
├─ scripts/           # 開発補助スクリプト
├─ AGENTS.md
└─ README.md
```

- **Top Levelに独立した `ai/` を作らない**【FIX】。`ai-image-processing` Skillが存在することは `ai/` Directoryを作る理由にならない
- **`physical-output/` を作らない**【未決定】。STL等の生成をBrowser / Backend / 独立Local Toolのどこで実行するかはPhysical Output担当のPoC後に決まる。それまでRoot配置を固定しない
- `worker/` `queue/` 等も作らない【未決定】
- 各Deploy Unit内部のDirectory構成は【担当裁量】

### 2.3 責任境界【FIX】

| 領域 | 責務 | 担当 |
|---|---|---|
| Frontend | 写真選択、進捗表示、3D Preview、2D Edit、Working Copy管理、作品確定 | まなみん |
| Backend | API境界、AI Orchestration、Artwork統合・Validation、Asset Manifest返却 | もりかん |
| AI・画像処理 | 意味理解、Segmentation、象徴要素選定、構成情報生成、Layer Asset生成 | クメ先生 |
| Physical Output | 実寸変換、STL等生成、3Dプリント、物理試作 | ナンちゃん |
| Design / UI | ロゴ、画面構成、UIデザイン | がっぽ |
| 横断支援 | Repository骨組み、AGENTS.md / Skills、Backend支援 | だいちゃん |

- 3D Preview / 2D Edit は**Frontend領域**に含む【FIX】
- MVP段階で担当境界を守るためだけのMicroservices化をしない【FIX】

---

## 3. Artwork Data — Single Source of Truth【FIX】

**Artwork Dataは AI / Backend / Frontend / 3D Preview / 2D Edit / Physical Output を横断する
作品構成の唯一の正本。**担当ごと・画面ごとに別の作品表現を正本として持たない。

- Schema正本: `contracts/artwork.schema.json`
- 共通Mock: `contracts/mock/artwork.json` + `contracts/assets/`
- 検証: `python scripts/validate_contracts.py`（Artwork単体 / 生成成功Response どちらでも可）

### 3.1 座標系【FIX】

実Pixel・実寸から独立した正規化座標系。

- `x` / `y` は**Layer中心点**。ともに 0.0〜1.0。原点はCanvas左上、xは右方向、yは下方向
- `scale` = Layer表示幅 / Canvas幅。**高さは Asset の Aspect Ratio から導出**する
- `canvas.aspectRatio` を Artwork Data が持つ。Schema上で固定値にしない
- **`rotation` は P0 の Artwork Data に持たせない**

### 3.2 layerIndex【FIX】

- 奥行き順を表す整数。**0が最背面**、値が大きいほど手前
- 同一Artwork内で `0..N-1` の**重複なし連番**へ正規化する
- 前後変更は `layers[]` の**配列位置ではなく layerIndex の変更**として扱う

### 3.3 Asset境界【FIX】

- **Binary画像をArtwork JSONへBase64埋め込みしない**
- Artwork Dataは `assetId` / `mimeType` / `widthPx` / `heightPx` のみ持つ
- **Runtime依存のURLをArtwork Data本体へ埋め込まない**
- Frontendへの生成成功結果は **Artwork Data + Asset Manifest**。Manifestは最低限
  `assetId` / `url` / `mimeType` / `widthPx` / `heightPx` を持つ
- **Asset Manifest のSchema正本は `contracts/asset-manifest.schema.json`**【FIX】
  （技術設計 §9.5 / §24.1）。Fieldの意味を変える場合は Artwork Contract と同じ扱いで共有する
- 両者を束ねた生成成功Responseの正本は
  **`contracts/generate-success-response.schema.json`**【FIX】（技術設計 §14.2）。
  Artwork / Manifest の定義を再定義せず `$ref` するだけの層（下記 §4）
- 透過Layer Assetは **RGBA PNG**
- Artwork Bundleでは同じ `assetId` のBinaryを `assets/` 配下へ置く

### 3.4 可変長【FIX】

**`layers[]` と `sourcePhotos[]` を固定長前提で実装しない。**
初期PoCの代表ケースが「写真5枚・4層」であるだけで、5枚固定・4層固定の契約ではない。
`layers[0]` が背景、`layers[2]` が人物、といった**位置による意味の決め打ちも禁止**。

---

## 4. API【FIX】

Prefix: `/api/v1`

### `POST /api/v1/artworks/generate`

- Request: `multipart/form-data`
  - `photos`: 複数画像（固定5枚ではない）。JPEG / PNG / WebP 基準。HEIC / HEIFは実機確認後【PoC後FIX】
  - `memoryText`: 任意String。未入力可
- 最終成功Result: **Artwork Data + Asset Manifest**

```json
{ "artwork": { ... }, "assetManifest": { "assets": [ ... ] } }
```

- **外側のKeyは `artwork` / `assetManifest`**【FIX】（技術設計 §14.2）。
  **P0では `data` 等の追加Envelopeを設けない**【FIX】
- Schema正本: `contracts/generate-success-response.schema.json`【FIX】。
  既存の `artwork.schema.json` / `asset-manifest.schema.json` を `$ref` するだけで再定義しない
- 共通Mock: `contracts/mock/generate-success-response.json`
- JSONのKeyはArtwork Schemaと同じ **camelCase** を維持する【FIX】
- 同期 / 非同期どちらで返すかは【PoC後FIX】。**どちらでも最終成功Resultの形は同じ**
- 失敗時は下記のError形式であり、この生成成功Response Schemaではない

### 作らないもの【FIX】

以下は「P0で作る前提にしない」。必要性が確定した場合のみ追加する。

- `GET /api/v1/artworks/{artworkId}`
- `PUT /api/v1/artworks/{artworkId}`
- `POST /api/v1/artworks/{artworkId}/finalize`
- `GET /api/v1/artworks/{artworkId}/bundle`
- `GET /api/v1/jobs/{jobId}`（非同期Job方式を採用する場合のみ）
- `GET /api/v1/assets/{assetId}`【検討中】

`GET /health` 等のHealth Checkは【担当裁量】。Product API Contractには含めない。

### Error形式【FIX】

```json
{
  "error": {
    "code": "AI_TIMEOUT",
    "message": "作品の生成に失敗しました。もう一度お試しください。",
    "retryable": true,
    "details": null
  }
}
```

- `code` は UPPER_SNAKE_CASE
- 共通Code: `INVALID_INPUT` / `UNSUPPORTED_MEDIA_TYPE` / `PAYLOAD_TOO_LARGE` /
  `ARTWORK_VALIDATION_FAILED` / `AI_RATE_LIMITED` / `AI_TIMEOUT` / `AI_FAILED` /
  `ASSET_BUILD_FAILED` / `INTERNAL_ERROR` /
  （該当Resourceが実在する場合のみ）`JOB_NOT_FOUND` / `ARTWORK_NOT_FOUND` / `ASSET_NOT_FOUND`
- **Stack Trace / API Key / Providerの生Response / 内部File Path を Frontend へ返さない**

---

## 5. State境界【FIX】

- Backendは**生成完了まで**の初期Artwork + Assetsの生成・統合・Validationに責任を持つ
- **生成後の編集は Frontend の Artwork Working Copy が中心**。P0でServer側Canonical Artworkを継続保持しない
- Userが「この作品で完成」を選んだ時点のWorking Copyが、そのSessionの確定Artwork Data
- P0では Login / 作品一覧 / 長期保存 を実装しない

---

## 6. 技術スタック

### Frontend【FIX】
- TypeScript / React 19.2系 / Vite 8系 / Node.js 24 LTS系
- 3D Preview: `three` + `@react-three/fiber` v9系
- 2D Edit: `konva` + `react-konva`
- Patch Versionは `package-lock.json` を正とする
- 【担当裁量】Router、状態管理、Form、CSS方式、Component分割、`@react-three/drei` 等

### Backend【仮決定】
- Python 3.13系 / FastAPI 0.139系 / Pydantic / ASGI
- `pyproject.toml` + Lock File で再現可能にする。requirements の手書き分散管理をしない【FIX】
- 【担当裁量】Router分割、class設計、DI、ID生成方式、Logging、ASGI Server設定

### AI【FIX / PoC後FIX】
- VLM第一候補: **Gemini Developer API**【FIX】
- 意味理解・象徴要素選定・bbox・構成: Gemini（初回PoCは `gemini-3.7-flash`）【PoC後FIX】
- Segmentation初回PoC: **EfficientSAM-Ti + ONNX Runtime CPU**【PoC後FIX】。
  Geminiは最終Mask境界を決めず、Geminiが返すbboxをPromptとして渡す
- モデルID・Segmentation Backend・Model Path・候補数・Layer数・品質閾値は環境変数化し、
  他担当のInterfaceを変更せず差し替えられるようにする【FIX / PoC後FIX】
- Gemini の Structured Output / JSON Schema を利用し、自由文ではなく型検証可能な結果を受け取る【FIX】
- Layer Assetの基本形式は RGBA PNG【FIX】
- Runtime起動時にModel WeightをDownloadしない。Cloud Run RuntimeへPyTorchを必須依存として
  持ち込まない【FIX】
- Segment EverythingをP0主経路にしない。Depth EstimationもP0で実装しない【FIX】
- 【担当裁量】Prompt分割、Gemini呼び出し回数、Score計算、Pillow / OpenCV等の内部処理

---

## 7. 3D Preview / 2D Edit【FIX】

### 3D Preview
- **Read Only。Artwork Dataを編集しない**
- P0操作: 回転 / Zoom / 正面Reset
- 各Layerを透過Textureを持つPlaneとして描画
- `z` は `layerIndex` から決定論的に導出する（例: `z = layerIndex * previewDepthStep`）
- **3D上のLayer間隔は表示値であり、物理作品のmm値をArtwork Dataに混ぜない**

正規化座標→3D変換:
```
canvasHeight = 1 / canvas.aspectRatio
x3d          = x - 0.5
y3d          = (0.5 - y) * canvasHeight
layerWidth   = scale
layerHeight  = scale * asset.heightPx / asset.widthPx
```

### 2D Edit
- P0操作: 位置移動 / 拡大縮小 / 差し替え / 前後変更
- Pixel座標は**描画時のみ**生成し、保存時は正規化 `x` / `y` / `scale` へ戻す
  ```
  pixelX     = x * stageWidth
  pixelY     = y * stageHeight
  pixelWidth = scale * stageWidth
  ```
- **rotation操作は提供しない**
- 前後変更後は `layerIndex` を `0..N-1` へ再正規化する
- 差し替え時は `x` / `y` / `scale` / `layerIndex` を維持し、
  `sourcePhotoId` / `sourceLayerId` / `asset` / `label` を置き換える
- `minScale` / `maxScale` / Canvas外許容量は【PoC後FIX】。**Frontend内部へ散在ハードコードしない**

### 編集後【FIX】
- **2D Edit後にAIを呼ばない。** 更新後のArtwork Dataからロジックベースで3Dを再描画する

---

## 8. Physical Output【FIX / PoC後FIX】

- 論理Inputは**確定Artwork Data + Assets**。実行場所がどこでもこの境界を維持する【FIX】
- Frontend内部State / Canvas Pixel / Three.js座標 / AI Prompt へ依存しない【FIX】
- 作品構成のSSOTである Artwork Data と、製造条件である **PhysicalOutputConfig を分離**する【FIX】
- **Artwork Data を物理都合のmm値で上書きしない**【FIX】

実寸変換:
```
targetHeightMm = targetWidthMm / canvas.aspectRatio
xMm            = x * targetWidthMm
yMm            = y * targetHeightMm
layerWidthMm   = scale * targetWidthMm
layerHeightMm  = layerWidthMm * asset.heightPx / asset.widthPx
```

- Web Applicationから3D Printerを直接操作する構成にしない【FIX】
- Portable Artwork Bundle: ZIPまたは展開済みDirectory。最低限 `artwork.json` と
  参照される `assets/` を含む。`artwork.json` は通常のArtwork Dataと同じSchema【FIX】
- **BundleへのSerializeは常に必須ではない**【FIX】（技術設計 §16.1 / §26.1）。
  別Runtime / Toolへ渡す方式を採る場合のみ必要で、同一Runtime内で
  Artwork Data + Assets を直接扱うなら不要。**Mock Bundle も先回りで作らない**
- STL生成方式、板形状、厚み、Layer Gap、Material、実行場所、Repository配置は【PoC後FIX】

---

## 9. Mock / 並行開発

- `contracts/mock/` + `contracts/assets/` が全担当の共通Fixture【FIX】
  - `mock/artwork.json` — Artwork Data を読む側すべて
  - `mock/asset-manifest.json` — `assetId` → URL の解決を組む側
  - `mock/generate-success-response.json` — Frontend ↔ Backend の生成成功境界
  - Mock Manifest の `url` はPlaceholder。実URLはRuntime依存なので固定値を前提にしない
- 各担当は他領域の完成を待たず、このMockとの契約を前提に開発する【FIX】
- Backendは `MOCK_AI=true` で実Geminiを呼ばず、Real生成と**同じ形式**を返せるModeを持つ【FIX】
- FrontendはMockかReal AIかで**Artwork Schemaの解釈を切り替えない**【FIX】
- Frontend / Physical Output側で独自にField名を読み替えない【FIX】

### Fallback禁止【FIX】

- **Real AI処理の失敗時に、ユーザーへ知らせず自動でMock Artworkへ差し替えることは禁止**
- `MOCK_AI=true` は明示的に有効化する開発・デモ用Modeであり、本番の隠れFallbackではない
- Schemaを満たさないArtworkや必須Assetが欠けたArtworkを成功扱いしない

---

## 10. Secret【FIX】

- `.env` を **Commitしない**
- `.env.example` は **Key名だけ**を共有し、Secret値を入れない
- Gemini API Key等はDeploy先のSecret / Environment Variablesへ設定する
- **Raw Gemini API Key を Frontend / Browser へ公開しない**
- API Key を Slack / Docs / AGENTS.md / Screenshot へ平文記載しない
- Frontendの公開可能な設定のみ `VITE_` Prefix で持つ

---

## 11. Agentへの禁止事項（まとめ）

以下は**Agentの判断だけで実行してはならない**。必要と判断した場合は実装せず、
理由と影響範囲を提示して人間の確認を求めること。

1. `contracts/` 配下のSchema変更（Field追加・削除・意味の変更・型変更）。
   `artwork.schema.json` / `asset-manifest.schema.json` /
   `generate-success-response.schema.json` はいずれも同じ扱い
2. `layers[]` / `sourcePhotos[]` を固定長前提で実装すること
3. Layerの配列位置に固定の意味（背景 / 中景 / 前景）を持たせること
4. `rotation` をArtwork Dataや2D Edit操作へ追加すること
5. Artwork DataへBinaryをBase64埋め込みすること、Runtime依存URLを埋め込むこと
6. §4「作らないもの」のEndpointを実装すること
7. `physical-output/` `worker/` `ai/` 等、【未決定】のTop Level Directoryを作ること
8. 【PoC後FIX】の値を確定値としてハードコードすること
9. 一枚絵を生成してから再Segmentationする方式を採ること
10. 2D Edit後にAIを再実行すること / 3D Previewに編集機能を持たせること
11. MVP外機能（Undo/Redo、複数構成案、Exploded View、注文・決済等）を勝手に追加すること
12. AI失敗時に黙ってMockへFallbackすること
13. Frontendから直接 Gemini Developer API を叩くこと

共通Contract・API・Repository Top Level・共通Stack・P0 Scope・費用に影響する変更は、
担当内で確定させず**公開チャンネルで共有してから**進める。

---

## 12. 参照

- 領域別の詳細: `skills/` 配下（`project-context` / `artwork-data` / `frontend` /
  `backend` / `ai-image-processing` / `physical-output` / `integration`）
- Machine Readable Contract正本: `contracts/`
  - `artwork.schema.json` / `asset-manifest.schema.json` / `generate-success-response.schema.json`
  - 共通Mock: `contracts/mock/`
- 人間向け仕様正本: Drive「技術設計」。全体像は Drive「ドパガキ向け_5分でわかる設計理解」、
  作るものは Drive「要件定義」

Skillsは本ファイルと `contracts/` を**参照する**構造にする。同じ契約本文を各Skillへコピーしない。
共通仕様が変わったら、技術設計だけでなく AGENTS.md と関連Skills も同期する。
