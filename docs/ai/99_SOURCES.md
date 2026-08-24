# Sources / Current External Facts

2026-08-24時点で技術選定時に確認した外部情報。

## EfficientSAM

Official:
https://github.com/yformer/EfficientSAM

確認事項:
- Point-prompt
- Box-prompt
- Segment Everything
- EfficientSAM-Ti / EfficientSAM-S
- ONNX version / ONNX example
- Apache-2.0 license

ONNX example:
https://github.com/yformer/EfficientSAM/blob/main/EfficientSAM_onnx_example.py

## ONNX Runtime

PyPI:
https://pypi.org/project/onnxruntime/

2026-07-25 releaseでは:
- Python >=3.11
- Python 3.13 classifier
- Linux x86_64 CPython 3.13 wheelあり

実装時は`uv`で現在のlock resolutionを必ず確認する。

## Cloud Run

Memory:
https://docs.cloud.google.com/run/docs/configuring/services/memory-limits

CPU:
https://docs.cloud.google.com/run/docs/configuring/services/cpu

Pricing:
https://cloud.google.com/run/pricing

確認事項:
- default 1 vCPU
- 1 vCPU: up to 4 GiB
- 2 vCPU: up to 8 GiB
- memory limit超過時instance termination
- free tierあり

## Repository Sources

- `/AGENTS.md`
- `/contracts/artwork.schema.json`
- `/backend/ai/types.py`
- `/backend/ai/errors.py`
- `/backend/ai/gemini.py`
- `/skills/ai-image-processing/SKILL.md`
- `/backend/app/api/v1/artworks.py`
- `/backend/app/services/generator.py`
- `/backend/app/config.py`
- `/Dockerfile`
- `/backend/pyproject.toml`

外部仕様は変わり得る。
モデル・SDK・Cloud Run制約に依存する実装を変更するときは再確認する。
