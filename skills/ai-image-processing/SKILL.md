---
name: ai-image-processing
description: Gemini による意味理解、象徴要素選定、Segmentation、透過Layer Asset生成を実装するときに使う。Prompt設計、Structured Output、モデル選定のPoC、Backendから呼ぶFunction境界を扱う場合に参照する。
---

# ai-image-processing

前提は `/AGENTS.md` §6。実装場所は `backend/ai/`。
**Top Levelに `ai/` Directoryを作らないこと。**本Skillが存在することは理由にならない。

## モデル【FIX / PoC後FIX】
- 意味理解・選定・構成: Gemini Developer API。具体的な `GEMINI_MODEL` は環境変数で
  差し替え、最終Model IDはFIXしない【PoC後FIX】
- SegmentationのP0主経路: **EfficientSAM-Ti + ONNX Runtime CPU**【FIX】。Geminiが返すbboxを
  PromptとしてMaskを得る。EfficientSAMの公式出典は `yformer/EfficientSAM`
- Geminiは意味理解・象徴要素選定・sourcePhoto/bbox・採用LayerのCompositionを担当し、
  最終Mask境界は担当しない
- **モデルID、`SEGMENTATION_BACKEND`、`EFFICIENTSAM_MODEL_PATH` は環境変数化**する。
  モデルWeightはRuntimeでDownloadしない。Cloud Run RuntimeへPyTorchを必須追加しない
- SAM 2.1 / YOLOE / Mattingは品質不足時の比較・Escalation候補であり、P0主経路の
  自動Fallbackにはしない

## 守ること
- Structured Output / JSON Schema を使う。自由文をパースしない
- **一枚絵を生成してから再Segmentationする方式を採らない。**
  元写真の要素を抽出Layerとして保持したまま構成する
- 元写真に存在しない面を生成して斜めの被写体を正面化しない
- 出力Layer Assetは **RGBA PNG**（実際に透過領域を持つこと）
- Backendからは Python Function / Module として呼べる境界にする
- 外部API失敗時の自動Retryは少回数・上限付き。無限Retryしない（P0は1回程度）
- 失敗時に黙ってMockへFallbackしない
- Segment EverythingをP0主経路にしない。Depth Modelを先回り追加しない

## PoCで出すべき材料
GeminiによるSemantic Planningと、EfficientSAMによるbbox→Maskの品質・Latencyを
代表写真ケースで計測し、次モデル比較が必要かを判断できる状態にする。GPU必須構成をP0の
Deploy必須条件にしない。

## 担当裁量
Prompt分割、Gemini呼び出し回数、中間型、Score計算、Pillow / OpenCV等の内部処理。
ただし最終的なOutputの形は Artwork Schema に統合可能であること。
