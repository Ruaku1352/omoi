# Implementation Plan

## 0. Baseline保護

最初に既存Tests / Contract Validationを実行しBaselineを確認する。
Mock経路を壊さない。

## 1. Runtime Dependency

基本:

```text
google-genai
pillow
numpy
onnxruntime
```

Cloud Run RuntimeへPyTorchを必須追加しない。

## 2. Configuration

P0設定:

```text
SEGMENTATION_BACKEND=efficient_sam_onnx
EFFICIENTSAM_MODEL_PATH
SEGMENTATION_MAX_RETRIES
CANDIDATE_COUNT
TARGET_LAYER_MIN
TARGET_LAYER_MAX
ARTWORK_CANVAS_ASPECT_RATIO
```

初回MVPの既定値は `TARGET_LAYER_MIN=4` / `TARGET_LAYER_MAX=4` /
`ARTWORK_CANVAS_ASPECT_RATIO=178/127`。これらはMVP生成Profileであり、Shared Contractの
可変長性を変更しない。

※先頭の `a` は実装時に除去し、正しいenv名 `EFFICIENTSAM_MODEL_PATH` とする。

`GEMINI_MODEL` はSemantic Planning / Composition用であり、最終採用Model IDは
環境変数で差し替える。Segmentationには `EFFICIENTSAM_MODEL_PATH` を使い、
`GEMINI_SEGMENTATION_MODEL` は設けない。

## 3. Segmenter Protocol

```python
class Segmenter(Protocol):
    def segment(
        self,
        image: Image.Image,
        box_px: tuple[int, int, int, int],
        *,
        point_px: tuple[int, int] | None = None,
    ) -> SegmentationResult: ...
```

ONNX Sessionはrequestごとにloadしない。
Service process lifetimeで再利用する。

## 4. Model Weight

- Runtime Downloadしない
- URLを推測してコードに書かない
- `EFFICIENTSAM_MODEL_PATH` が無ければclear error
- Artifact供給方式はDeploy前に明示

最初のPoCはLocal Model Pathでよい。

## 5. Gemini Semantic Planner

Structured OutputをPydanticで定義。
Promptで明示:
- 最終作品は多層Layer作品
- 思い出を象徴する対象を選ぶ
- 切り抜きやすさだけで選ばない
- 同じ意味の候補を重複しすぎない
- Visual Elementが複数componentなら分ける
- bboxは対象全体を含める
- candidateはimportance順

## 6. Preprocessing

元画像:
- Layer生成用に保持

Gemini用:
- EXIF補正
- resizeして通信量削減

Segmentation用:
- ONNX Model仕様に合わせてresize/normalize
- 出力Maskを元画像座標へ戻す

## 7. Quality Gate

Hard Fail:
- empty mask
- 全面foreground
- bboxから完全に外れる
- decode不能

Soft Metric:
- foreground area ratio
- bbox coverage
- model score
- border touch
- union size

Soft MetricはlogしてPoCで閾値決定。

## 8. RGBA Asset

- original resolution基準
- maskをalphaへ
- tight crop + 必要なら少量padding
- PNG encode
- `image/png`
- width/heightはcrop後
- 透明領域が存在

## 9. Composition

採用LayerだけをGeminiへ渡す。
可能ならlayer thumbnail + label + importanceを渡す。

返却:
- x
- y
- scale
- order

PythonでContract constraintsへ変換。
`scale * canvasAspectRatio * assetHeight / assetWidth` で表示高さを求め、x/y/scaleの
単純clampではなくLayer矩形全体をCanvas内へ収める。

## 10. Artwork Assembly

IDはOpaque ID制約を満たす。
Artworkが参照する全AssetBlobを返す。
参照漏れを作らない。

## 11. Error Mapping

AI module:
- timeout -> `AiTimeoutError`
- rate limit -> `AiRateLimitedError`
- config -> `AiNotConfiguredError`
- その他 -> `AiError`

HTTP status/messageはAI層で決めない。

## 12. Logging

最低限:

```text
ai.semantic_plan elapsed
ai.segmentation candidate=<id> elapsed score=<...>
ai.layer_build elapsed
ai.composition elapsed
ai.total elapsed
```

写真内容、API key、Provider raw responseをProduction Logへ出さない。

## 13. Tests

Unit:
- Internal Model validation
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

Unit Testsをreal API key / model weight必須にしない。
