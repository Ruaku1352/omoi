"""Mock / Real Generator の選択。

`MOCK_AI=true` は**明示的に有効化する開発・デモ用Mode**。
Real処理が失敗したときに黙ってMockへ落ちる経路をここへ作らない（AGENTS.md §9・§11-12）。
"""

from __future__ import annotations

from ai.gemini import GeminiArtworkGenerator
from ai.types import ArtworkGenerator
from app.config import Settings
from app.services.mock_generator import MockArtworkGenerator


def build_generator(settings: Settings) -> ArtworkGenerator:
    if settings.mock_ai:
        return MockArtworkGenerator(settings.contracts_dir)
    return GeminiArtworkGenerator(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        segmentation_model=settings.gemini_segmentation_model,
    )
