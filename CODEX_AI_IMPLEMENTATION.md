# Codex向け: omoi Real AI実装タスク

あなたは `Ruaku1352/omoi` のAI・画像処理実装を担当する。

## 最初に読む順番

1. `/AGENTS.md`
2. `/contracts/artwork.schema.json`
3. `/contracts/asset-manifest.schema.json`
4. `/contracts/generate-success-response.schema.json`
5. `/backend/ai/types.py`
6. `/backend/ai/errors.py`
7. `/backend/ai/gemini.py`
8. `/backend/app/services/generator.py`
9. `/backend/app/api/v1/artworks.py`
10. `/docs/ai/00_INDEX.md`
11. `/skills/ai-image-processing/SKILL.md`

読まずに実装を始めない。

# ゴール

`MOCK_AI=false` のとき、複数写真 + optional `memoryText` から実際に:

1. Geminiで写真群の意味を理解する
2. 思い出を象徴するVisual Element候補を複数選ぶ
3. Geminiから対象位置のbboxを得る
4. EfficientSAM-Ti ONNXで対象をSegmentationする
5. PillowでRGBA PNG Layer Assetを生成する
6. 品質の良いLayerを3〜5個程度採用する
7. Geminiで採用Layerの初期構図を提案する
8. Python側で座標・layerIndex等を正規化する
9. `GenerationResult(artwork, assets)` を返す
10. 既存Backend Validationを通す

代表ケースが「写真5枚・Layer 4枚」であるだけで、固定長にしない。

# 絶対に変更しないもの

明示的なチーム合意がない限り変更しない。

- `contracts/artwork.schema.json`
- `contracts/asset-manifest.schema.json`
- `contracts/generate-success-response.schema.json`
- Product APIの公開形
- `ArtworkGenerator.generate(photos, memory_text) -> GenerationResult` の意味
- `AssetBlob` の役割
- layer asset = RGBA PNG
- asset URLはBackend責務
- MockとRealの明示的切り替え

`worker/`, `queue/`, 独立AI service等を先回りで作らない。

# P0技術選定

## 意味理解

- Gemini
- Model IDは `GEMINI_MODEL` 環境変数
- 初回PoC値: `gemini-3.7-flash`
- Structured Outputを使う
- 自由文をRegex等でparseしない

## Segmentation

- 初回PoC: **EfficientSAM-Ti**
- Runtime: **ONNX Runtime CPU**
- Box Promptを主経路にする
- PyTorchをCloud Run Runtime必須依存にしない
- Model Pathは環境変数化する
- RuntimeでModelをdownloadしない

推奨環境変数:

```text
SEGMENTATION_BACKEND=efficient_sam_onnx
EFFICIENTSAM_MODEL_PATH=/srv/models/efficient_sam_vitt.onnx
SEGMENTATION_MAX_RETRIES=1
CANDIDATE_COUNT=8
TARGET_LAYER_MIN=3
TARGET_LAYER_MAX=5
```

閾値・候補数・Layer数はPoC後FIX。Contract固定値ではない。

# 推奨Module構造

```text
backend/ai/
├─ __init__.py
├─ errors.py               # 既存
├─ types.py                # 既存。Backendとの境界
├─ pipeline.py             # RealArtworkGenerator / orchestration
├─ gemini.py               # Semantic Planner / Composer
├─ internal_models.py      # Pydantic内部型
├─ segmentation.py         # Segmenter Protocol + EfficientSAM ONNX
├─ image_ops.py            # 前処理、mask→RGBA
├─ quality.py              # Mask Quality Gate
└─ assembly.py             # Artwork assembly / layout normalize
```

AI内部なので、責務が明確なら統合してもよい。

# 重要原則

## Artwork Layerは1 Objectとは限らない

例:

```text
Visual Element: 「誕生日の主役」
components:
- child
- party hat
- gift
```

複数Maskのunionを1 Layerにしてよい。

## Candidateを多めに出す

```text
Gemini: 6〜8候補
→ Segmentation
→ Quality Gate
→ 良質な3〜5 Layer採用
```

1候補のSegmentation失敗でArtwork全体を即失敗させない。

## Segment Everythingを主経路にしない

主経路:

```text
Gemini → sourcePhoto + bbox → EfficientSAM → mask
```

## Depthを実装しない

P0ではDepth Map / Depth Anything / MoGe等を追加しない。
`layerIndex` はScene ReconstructionではなくArtwork Composition。

## Model Runtime Download禁止

Modelが無い場合は `AiNotConfiguredError` でfail fast。
Cloud Run cold start中にGitHub/Hugging Faceからdownloadしない。

# 実装順

## Phase A: Internal Types
- SemanticPlan
- VisualElementCandidate
- SegmentationComponent
- AcceptedLayer
- CompositionPlan

## Phase B: EfficientSAM Adapter
- `Segmenter` Protocol
- ONNX Sessionはprocess内で1回だけload
- bbox入力
- mask出力
- scoreが取得できる場合は返す
- Unit Test用Fake Segmenterを用意

## Phase C: Image Ops
- EXIF transpose
- Gemini解析用resize
- bbox変換
- mask union
- mask→alpha
- crop
- RGBA PNG Encode

## Phase D: Gemini Semantic Planner
- photos + memoryTextを同一Contextで解析
- Structured Output
- 6〜8候補
- sourcePhoto index
- label / importance / reason
- components[]
- component bbox

## Phase E: Quality Gate
Hard Fail:
- empty mask
- 全面foreground
- prompt bboxと完全に乖離
- decode不能

Soft Metric:
- foreground area ratio
- bbox coverage
- score
- border touch

Soft Metricはまずlog。PoC前に強い閾値を決めすぎない。

## Phase F: Candidate Selection
importance順に処理し、良質なLayerが目標数集まったら終了。
min未達時のみGeneration failure。

## Phase G: Composition
実際に採用できたLayer thumbnail/metadataをGeminiへ渡す。
返却:
- x
- y
- scale
- front-to-back order

Pythonで:
- x/y clamp
- scale sanity
- layerIndex `0..N-1` unique contiguous

## Phase H: Assembly
- source photo assetも `AssetBlob`
- Layer Assetも `AssetBlob`
- Artwork JSONにBinary無し
- Artwork JSONにruntime URL無し
- replacementCandidatesは初回E2Eでは空配列可

## Phase I: Integration
- Real generatorを既存`build_generator()`へ接続
- Mockを壊さない
- Backend既存Validationを必ず通す
- API Response Contractを変えない

## Phase J: Tests
Unit:
- Internal Model
- bbox conversion
- mask→RGBA
- mask union
- layout normalize
- Artwork assembly
- Fake Segmenter
- Fake Gemini

Integration:
- Real Gemini
- Real EfficientSAM ONNX
- representative photos

Unit TestをAPI Key / Model Weight必須にしない。

# Completion Definition

- [ ] `MOCK_AI=true` 既存動作が壊れていない
- [ ] Real Pipelineが `GenerationResult` を返す
- [ ] Contractを変更していない
- [ ] sourcePhotos/layers可変長
- [ ] Layer PNGに実透明領域がある
- [ ] Runtime URLをArtworkへ埋め込んでいない
- [ ] Backend Validationを通る
- [ ] Real失敗でMockへfallbackしない
- [ ] ONNX model missing時に明確な設定Error
- [ ] Unit TestがModel Weight無しで走る
- [ ] Real PoCを別scriptで実行可能
- [ ] Semantic / Segmentation / CompositionのTimingを記録

# 迷ったときの優先順位

1. omoiの課題解決に必要か
2. Shared Contractを壊さないか
3. Cloud Run CPUで成立するか
4. P0に本当に必要か
5. 後から差し替え可能か

「将来必要そう」だけで複雑化しない。
