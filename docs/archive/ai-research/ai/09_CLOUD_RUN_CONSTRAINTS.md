# Cloud Run Constraints

## P0前提

今回はCloud RunのCPU構成で成立させる。GPUを必須にしない。

## 初回Deploy設定

```text
CPU: 1 vCPU
Memory: 2 GiB
Concurrency: 1
Minimum instances: 0
```

から計測する。

## Resource条件

2026-08-24時点の公式仕様:
- default 1 vCPU
- 1 vCPUでは最大4 GiB
- 2 vCPUでは最大8 GiB
- memory limit超過時instance terminate

Peak MemoryはModelだけでなく:
- Python runtime
- FastAPI
- ONNX Runtime
- decoded original images
- tensors
- masks
- PNG buffers

を含めて見る。

## CPU Runtime方針

基本:

```text
python
fastapi
google-genai
pillow
numpy
onnxruntime
```

PyTorchをCloud Run必須Runtimeへ追加しない。

## ONNX Runtime

2026-07リリースのONNX RuntimeにはPython 3.13 Linux wheelが提供されている。
omoi BackendのPython `>=3.13,<3.14` と両立可能。

ただし実Docker Build / `uv sync` で必ず確認する。

## Model Load

悪い:

```python
async def generate(...):
    session = ort.InferenceSession(...)
```

requestごとにModel loadしない。

良い:

```text
Generator / Segmenter生成時
→ ONNX Session 1回load
→ request間で再利用
```

Cloud Run instance単位で再利用する。

## Runtime Download禁止

cold start時にGitHub/Hugging Face等からmodel downloadしない。
理由:
- cold start不安定
- 外部network依存
- latency増
- version/checksum再現性低下

Model Artifactはimage build前/中に固定する。

## Input Memory

高解像度originalはLayer生成用。
Gemini / Segmentation用は必要に応じresize。
同一画像の無駄なcopyを多数保持しない。

## Concurrency

画像AI処理はPeak Memoryが大きい。
最初は `concurrency=1`。
実測後にmemory / CPU / latencyを見て上げる。

## Free Tier / Trial

P0目標は無料枠の理論最大活用ではなく:

```text
デモ・PoC負荷で安定
+ GPU無し
+ 不要な常時instance無し
```

`min instances=0`から開始し、cold startがデモを壊す場合だけ対策する。
