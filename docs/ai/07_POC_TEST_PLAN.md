# Segmentation / AI PoC Test Plan

## 目的

「EfficientSAMが強いか」ではなく、
**omoiのLayer Assetとして十分か**を判断する。

## Dataset

代表E2Eは、利用同意済みの写真5枚とmemoryTextを1組として、4層・2L判Landscapeの
Frontend handoff bundleまで生成する。可変長入力の探索ケースとは結果を分けて記録する。

最低10〜20対象。

含める:
- 人物全身
- 人物上半身
- 髪
- 指
- 手に持った物
- 人物同士の重なり
- 背景と似た色の服
- ケーキ
- ぬいぐるみ
- 建物
- 遊具
- 細い物体
- 小物
- Long-tailな思い出要素

チーム所有または利用同意済み写真のみ。

## Pipeline Test

各対象:

```text
Gemini bbox
→ EfficientSAM-Ti
→ mask
→ RGBA PNG
```

を保存。

## 目視評価

3段階:
- A: そのまま作品に使える
- B: 軽微な欠損/混入だが許容
- C: 明確に使えない

見るポイント:
- 対象間違い
- body part欠損
- background混入
- 穴
- 細部
- 過剰crop
- 不自然な輪郭

## 数値計測

```text
photo_id
candidate_label
image_width
image_height
gemini_elapsed_ms
segmentation_elapsed_ms
layer_build_elapsed_ms
total_elapsed_ms
model_score
mask_area_ratio
result_grade
```

可能なら:
- process RSS / Peak memory
- ONNX session load time
- cold vs warm inference

## Frontend handoff確認

Real生成結果を1フォルダにまとめ、成功Response、Artwork、Manifest、全Asset、memoryText、
metrics、README、composition / bbox / mask / layer previewを確認する。READMEだけでBackend
Responseとフォルダ内ファイルの対応が分かることを受入条件にする。

`.env.example` に沿って `GEMINI_API_KEY` と `EFFICIENTSAM_MODEL_PATH` をローカル環境へ設定し、
Backendの再現環境から代表ケースを実行する。

```powershell
cd backend
uv run python ../scripts/run_real_ai_poc.py --memory-text "思い出の説明文" --max-photos 5 --output-dir ../poc-output/final-mvp
```

`run_multi_real_ai_poc.py` は複数ケース比較用の補助PoCであり、Frontend handoffの正規Bundleは
上記 `run_real_ai_poc.py` で生成する。

## Cloud Run Test

Local成功後:

```text
1 vCPU
2 GiB
concurrency 1
min instance 0
```

から開始。

確認:
- cold start
- warm request
- 5 photos / 4 layers程度
- OOMしない
- timeoutしない

## 次モデルへ進む条件

### SAM 2.1
EfficientSAMでbboxが正しいのに境界/対象形状の品質不足が継続。

### YOLOE
bbox内の複数対象から誤対象を選ぶ等、意味情報をSegmentation側にも渡す必要がある。

### Matting
Mask対象は正しいが髪/soft edgeだけが品質を壊す。

## P0主経路の継続判断

EfficientSAMで:
- 代表写真群の大部分が作品素材として使える
- Cloud Run CPUで許容Latency
- Memory安定
- 実装複雑性が低い

ならP0主経路を維持し、比較モデルを増やさない。
「もっと強いモデルがある」だけでは追加比較しない。
