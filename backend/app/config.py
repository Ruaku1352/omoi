"""環境変数からの設定読み込み。

Key名の共有は Repository Root の `.env.example`。Secret値はCommitしない（AGENTS.md §10）。
【PoC後FIX】の値をコードへ直書きせず、ここへ集約して環境変数で差し替えられるようにする。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 実行環境 ----
    app_env: str = "local"

    # ---- Mock ----
    # true で実Geminiを呼ばず共通Mock相当を返す。明示Modeであり隠れFallbackではない。
    mock_ai: bool = False
    # 共通Contract（`contracts/`）の場所。Deploy時にCopy先が変わるなら差し替える。
    contracts_dir: Path = REPO_ROOT / "contracts"

    # ---- CORS ----
    # Frontend と Backend は別Origin。Productionでは必要最小限へ限定する。
    cors_origins: str = ""

    # ---- AI ----
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    gemini_segmentation_model: str | None = None

    # ---- Upload制限【PoC後FIX】----
    # 代表ケースは写真5枚だが、固定5枚の契約ではない。実測後に見直す。
    max_photos: int = Field(default=20, ge=1)
    max_photo_bytes: int = Field(default=15 * 1024 * 1024, ge=1)
    max_total_upload_bytes: int = Field(default=60 * 1024 * 1024, ge=1)

    # ---- Asset公開【未決定】----
    # Asset Binary Storage方式は未決定。暫定はLocal Directory + 静的配信で、
    # 決まったら AssetStore の実装を差し替える（API境界は変えない）。
    asset_dir: Path = BACKEND_DIR / ".dev-assets"
    # 静的配信のURL Prefix。Product APIの `/api/v1` 配下には置かない。
    asset_mount_path: str = "/dev/assets"
    # 外部Storage等へ移したときのURL Prefix上書き。未設定ならRequestのOriginを使う。
    asset_public_base_url: str | None = None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def contracts_assets_dir(self) -> Path:
        return self.contracts_dir / "assets"


@lru_cache
def get_settings() -> Settings:
    return Settings()
