# backend/ai — AI・画像処理Module

Backendと同一Python実行環境の内部Module。**Top Levelに独立した `ai/` を作らない。**

Gemini Developer API を第一候補とし、意味理解 / 象徴要素選定 / 構成情報生成 /
Segmentation / 透過Layer Asset生成を担う。

モデルIDは環境変数（`GEMINI_MODEL` / `GEMINI_SEGMENTATION_MODEL`）で差し替え可能にする。
詳細は `/skills/ai-image-processing/SKILL.md`。
