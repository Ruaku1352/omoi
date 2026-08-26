# backend/ai — AI・画像処理Module

Backendと同一Python実行環境の内部Module。**Top Levelに独立した `ai/` を作らない。**

Gemini Developer API は意味理解 / 象徴要素選定 / bbox / 構成情報生成を担い、
EfficientSAM-Ti ONNX Runtime CPU はbboxをPromptとしてSegmentationを担う。
Pillow/PythonがMaskをRGBA PNG Layer AssetとArtwork Dataへ変換する。

モデルID、Segmentation Backend、Model Pathは環境変数で差し替え可能にする。Model Weightを
RuntimeでDownloadせず、Cloud Run RuntimeへPyTorchを必須依存として持ち込まない。
詳細は `/skills/ai-image-processing/SKILL.md`。
