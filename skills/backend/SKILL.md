---
name: backend
description: Cloud Run 上の FastAPI Backend を実装するときに使う。POST /api/v1/artworks/generate、GET /api/v1/jobs/{jobId}、Physical Output PoC、AI Module 呼び出し境界、Artwork統合とValidation、Asset Manifest 返却、CORS、MOCK_AI Mode、Error形式を扱う場合に参照する。
---

# backend

前提は `/AGENTS.md` §4, §5, §6。

## Stack【仮決定】
Python 3.13系 / FastAPI 0.139系 / Pydantic / ASGI。
`pyproject.toml` + Lock File。requirements の手書き分散管理をしない。

## 責務の範囲
API境界 → AI呼び出し・Orchestration → Layer Asset生成結果の受領 →
初期Artwork統合 → Schema / Asset参照 Validation → Asset Manifest返却。

生成後のCanonical Artwork維持はFrontend Working Copyへ移す。
Job管理は2026-09-02時点で、`POST /api/v1/artworks/generate` が `202 + jobId` を返し、
`GET /api/v1/jobs/{jobId}` で完了結果を取得する形にFIX済み。Asset Binary Storage方式は
まだ未決定で、Manifestの境界を変えずに差し替えられるようにする。

Physical OutputはまだRuntime/配置がFIXではない。ただしPoC候補として
`POST /api/v1/physical-output/exports` をFastAPIに追加し、確定Artwork Data + Assetsを受けて
3Dプリンター用STL ZIPまたは2L Landscape（178 x 127mm）写真紙用PDFを生成する。

## 実装順
1. `POST /api/v1/artworks/generate` の受け口（multipart）と Pydantic モデル
2. `202 + jobId` を返し、`GET /api/v1/jobs/{jobId}` で結果をPollingできるJob境界
3. `MOCK_AI=true` で `contracts/mock/generate-success-response.json` 相当を返すMode
4. Artwork Schema Validation と Asset参照整合性チェック
5. Asset Manifest の組み立て。Manifest Schemaの正本は
   `contracts/asset-manifest.schema.json`【FIX】。返す形の正本は
   `contracts/generate-success-response.schema.json`【FIX】（`{artwork, assetManifest}`）。
   **P0では `data` 等の追加Envelopeを設けない**【FIX】
6. AI Module を **Python Function / Module 境界**で呼ぶ（内部HTTP Microserviceにしない）
7. Physical Output PoCは `artwork` JSON + `assets[]` を入力にし、製造条件は
   `physicalOutputConfig` に分離する。未指定時はBackend側のPoC既定値
   （rail / 2L Landscape / 4行 x 3穴）を使う。`outputFormat` で
   `stlZip` / `photoPdf` を分け、入力をPortable Bundle ZIPへ固定しない。
   生成入力写真とPhysical Output用Layer PNGのUpload制限は分ける
8. CORS を `CORS_ORIGINS` から設定して Cloud Run へDeploy

## 単独でFIXしないこと
Asset Binary Storage方式、Physical Output Runtime配置、Bundle生成主体。
いずれも共通決定に影響する。

追加Endpointは基本的に先回りしない。ただし `POST /api/v1/physical-output/exports` は
2026-09-02時点のPhysical Output PoC候補として扱う。正式FIXではないので、
Cloud Runへ載せる前に公開チャンネルで共有する。

## Error
`/AGENTS.md` §4 の形式に従う。実在しないResourceのError Codeを先回りで定義しない。
Stack Trace / API Key / Providerの生Response / 内部File Path を返さない。
