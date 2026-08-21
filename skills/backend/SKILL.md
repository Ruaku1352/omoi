---
name: backend
description: Cloud Run 上の FastAPI Backend を実装するときに使う。POST /api/v1/artworks/generate、AI Module 呼び出し境界、Artwork統合とValidation、Asset Manifest 返却、CORS、MOCK_AI Mode、Error形式を扱う場合に参照する。
---

# backend

前提は `/AGENTS.md` §4, §5, §6。

## Stack【仮決定】
Python 3.13系 / FastAPI 0.139系 / Pydantic / ASGI。
`pyproject.toml` + Lock File。requirements の手書き分散管理をしない。

## 責務の範囲
API境界 → AI呼び出し・Orchestration → Layer Asset生成結果の受領 →
初期Artwork統合 → Schema / Asset参照 Validation → Asset Manifest返却。**ここまで。**

生成後のCanonical Artwork維持はFrontend Working Copyへ移す。
Job管理・Asset Binary Storageは必要性が確定した場合のみ追加する。

## 実装順
1. `POST /api/v1/artworks/generate` の受け口（multipart）と Pydantic モデル
2. `MOCK_AI=true` で `contracts/mock/generate-success-response.json` 相当を返すMode
3. Artwork Schema Validation と Asset参照整合性チェック
4. Asset Manifest の組み立て。返す形の正本は
   `contracts/generate-success-response.schema.json`（`{artwork, assetManifest}`）
5. AI Module を **Python Function / Module 境界**で呼ぶ（内部HTTP Microserviceにしない）
6. CORS を `CORS_ORIGINS` から設定して Cloud Run へDeploy

## 単独でFIXしないこと
同期 / 非同期方式、Asset Binary Storage方式、Queue / Job Runner の導入、
追加Endpoint、Bundle生成主体。いずれも共通決定に影響する。

代表写真5枚ケースの**実測時間を計測して共有する**のがまず優先。
同期で足りるなら Job Store も Polling も作らない。

## Error
`/AGENTS.md` §4 の形式に従う。実在しないResourceのError Codeを先回りで定義しない。
Stack Trace / API Key / Providerの生Response / 内部File Path を返さない。
