"""AI Module と Backend の境界に置くデータ構造。

- 呼び出しは Python Function / Module 境界。内部HTTP Microserviceにしない（AGENTS.md §2.1）
- Artwork Data は Binary を持たない。Asset Binary はここで別途返す（AGENTS.md §3.3）
- Asset の公開URL決定は Backend 側の責務。AI Module はURLを知らない
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class InputPhoto:
    """Userがアップロードした写真1枚。"""

    filename: str
    mime_type: str
    data: bytes


@dataclass(frozen=True)
class AssetBlob:
    """生成されたAsset Binary1件。

    `asset_id` は Artwork Data 内の `asset.assetId` と一致させる。
    Layer Asset は透過を持つ RGBA PNG（`image/png`）。
    """

    asset_id: str
    mime_type: str
    width_px: int
    height_px: int
    data: bytes


@dataclass(frozen=True)
class GenerationResult:
    """AI Module の最終成果。

    `artwork` は `contracts/artwork.schema.json` を満たす dict。
    Schema / 参照整合性の検証は Backend 側で必ず行う（AI Moduleの自己申告を信用しない）。
    """

    artwork: dict
    assets: Sequence[AssetBlob] = field(default_factory=tuple)


class ArtworkGenerator(Protocol):
    """写真群から初期Artworkを生成する。Mock / Real の差し替え点。"""

    async def generate(
        self,
        photos: Sequence[InputPhoto],
        memory_text: str | None,
    ) -> GenerationResult: ...
