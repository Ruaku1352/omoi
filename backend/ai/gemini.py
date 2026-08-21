"""Gemini Developer API を使う Real Generator。

**未実装。** 意味理解 / 象徴要素選定 / 構成情報生成 / Segmentation /
透過Layer Asset生成の中身は AI・画像処理担当（クメ先生）が入れる。
`/skills/ai-image-processing/SKILL.md` を参照。

ここで確定しているのは境界だけ:
  - モデルIDは環境変数で差し替える（`GEMINI_MODEL` / `GEMINI_SEGMENTATION_MODEL`）【PoC後FIX】
  - 意味理解用とSegmentation用が同一モデルであることを要求しない
  - Structured Output / JSON Schema で型検証可能な結果を受け取る【FIX】
  - 失敗時は AiError 系を投げる。**Mockへ黙って落ちない**（AGENTS.md §9）
"""

from __future__ import annotations

from collections.abc import Sequence

from ai.errors import AiError, AiNotConfiguredError
from ai.types import GenerationResult, InputPhoto


class GeminiArtworkGenerator:
    def __init__(
        self,
        *,
        api_key: str | None,
        model: str | None,
        segmentation_model: str | None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._segmentation_model = segmentation_model

    def _require_config(self) -> None:
        missing = [
            name
            for name, value in (
                ("GEMINI_API_KEY", self._api_key),
                ("GEMINI_MODEL", self._model),
                ("GEMINI_SEGMENTATION_MODEL", self._segmentation_model),
            )
            if not value
        ]
        if missing:
            raise AiNotConfiguredError(f"未設定の環境変数: {', '.join(missing)}")

    async def generate(
        self,
        photos: Sequence[InputPhoto],
        memory_text: str | None,
    ) -> GenerationResult:
        del photos, memory_text
        self._require_config()
        raise AiError(
            "Gemini Generator は未実装。"
            "開発中は MOCK_AI=true を明示的に有効化して共通Mockで進める。"
        )
