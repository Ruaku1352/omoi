"""MOCK_AI=true 用の Generator。

共通Mock（`/contracts/mock/artwork.json` + `/contracts/assets/`）を
Real生成と**同じ形式**で返す。明示的に有効化する開発・デモ用Modeであり、
Real処理失敗時の隠れFallbackではない（AGENTS.md §9）。

`ai/` ではなくBackend側に置く。`ai/` は AI・画像処理担当の領域で、
呼び出し境界（`ai/types.py`）とReal実装（`ai/gemini.py`）だけを持たせる。
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from pathlib import Path

from ai.errors import AiNotConfiguredError
from ai.types import AssetBlob, GenerationResult, InputPhoto

_EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _iter_asset_refs(artwork: dict):
    for photo in artwork.get("sourcePhotos", []):
        yield photo["asset"]
    for layer in artwork.get("layers", []):
        yield layer["asset"]
        for candidate in layer.get("replacementCandidates", []):
            yield candidate["asset"]


class MockArtworkGenerator:
    """共通Fixtureをそのまま返す。写真の枚数や内容は結果に反映しない。"""

    def __init__(self, contracts_dir: Path) -> None:
        self._artwork_path = contracts_dir / "mock" / "artwork.json"
        self._assets_dir = contracts_dir / "assets"

    async def generate(
        self,
        photos: Sequence[InputPhoto],
        memory_text: str | None,
    ) -> GenerationResult:
        del photos, memory_text  # Mockは入力に依存しない

        if not self._artwork_path.is_file():
            raise AiNotConfiguredError(
                f"共通Mockが見つからない: {self._artwork_path}（CONTRACTS_DIR を確認する）"
            )

        artwork = json.loads(self._artwork_path.read_text(encoding="utf-8"))

        assets: list[AssetBlob] = []
        for ref in _iter_asset_refs(artwork):
            ext = _EXT_BY_MIME.get(ref["mimeType"])
            if ext is None:
                raise AiNotConfiguredError(f"未対応のmimeType: {ref['mimeType']}")
            path = self._assets_dir / f"{ref['assetId']}.{ext}"
            if not path.is_file():
                raise AiNotConfiguredError(
                    f"Mock Assetが見つからない: {path.name}"
                    "（python scripts/generate_mock_assets.py を実行する）"
                )
            assets.append(
                AssetBlob(
                    asset_id=ref["assetId"],
                    mime_type=ref["mimeType"],
                    width_px=ref["widthPx"],
                    height_px=ref["heightPx"],
                    data=path.read_bytes(),
                )
            )

        return GenerationResult(artwork=artwork, assets=tuple(assets))
