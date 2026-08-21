---
name: ai-image-processing
description: Gemini による意味理解、象徴要素選定、Segmentation、透過Layer Asset生成を実装するときに使う。Prompt設計、Structured Output、モデル選定のPoC、Backendから呼ぶFunction境界を扱う場合に参照する。
---

# ai-image-processing

前提は `/AGENTS.md` §6。実装場所は `backend/ai/`。
**Top Levelに `ai/` Directoryを作らないこと。**本Skillが存在することは理由にならない。

## モデル【PoC後FIX】
- 意味理解・選定・構成: `gemini-3.7-flash` から検証開始
- Segmentation: **FIXしない**。初期候補 `gemini-2.5-flash`。
  Gemini 3.x のImage Segmentation対応は公式資料間で記述が割れているため、
  安全側で 2.5 を起点に実APIでPolygon Mask取得を確認する
- 意味理解用とSegmentation用が同一モデルである必要はない
- **モデルIDは `GEMINI_MODEL` / `GEMINI_SEGMENTATION_MODEL` で環境変数化**する。
  ハードコードしない

## 守ること
- Structured Output / JSON Schema を使う。自由文をパースしない
- **一枚絵を生成してから再Segmentationする方式を採らない。**
  元写真の要素を抽出Layerとして保持したまま構成する
- 元写真に存在しない面を生成して斜めの被写体を正面化しない
- 出力Layer Assetは **RGBA PNG**（実際に透過領域を持つこと）
- Backendからは Python Function / Module として呼べる境界にする
- 外部API失敗時の自動Retryは少回数・上限付き。無限Retryしない（P0は1回程度）
- 失敗時に黙ってMockへFallbackしない

## PoCで出すべき材料
Gemini単体のSegmentation品質、Latency、Rate Limit を代表写真5枚ケースで計測し、
SAM系の追加が必要かを判断できる状態にする。GPU必須構成をP0のDeploy必須条件にしない。

## 担当裁量
Prompt分割、Gemini呼び出し回数、中間型、Score計算、Pillow / OpenCV等の内部処理。
ただし最終的なOutputの形は Artwork Schema に統合可能であること。
