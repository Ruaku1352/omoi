"""環境変数からの設定読み込み。

Key名の共有は Repository Root の `.env.example`。Secret値はCommitしない（AGENTS.md §10）。
【PoC後FIX】の値をコードへ直書きせず、ここへ集約して環境変数で差し替えられるようにする。
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

# host[:port] として妥当な文字だけを許す。引用符や空白が紛れ込んだ値を弾くため。
# gcloud の --set-env-vars でクォートを付け損なうと `"http://a` のような値が入りうる。
_NETLOC_RE = re.compile(r"^(?:\[[0-9A-Fa-f:]+\]|[A-Za-z0-9.\-]+)(?::[0-9]+)?$")


def classify_origins(raw: str) -> tuple[list[str], list[str]]:
    """`CORS_ORIGINS` をカンマ区切りで解釈し、(正規化済み, 不正) に分ける。

    Browser が送る `Origin` ヘッダーは scheme + host + port だけで、
    末尾スラッシュを含まず、scheme と host は小文字。
    CORSMiddleware は**完全一致**で判定するため、末尾スラッシュや大文字が混じると
    HTTP 200 は返るのに `Access-Control-Allow-Origin` が付かず、
    **サーバー側は正常に見えてブラウザだけが失敗する**。ここで吸収する。

        "https://a.web.app/, HTTP://B.Web.App" -> (["https://a.web.app", "http://b.web.app"], [])

    解釈できなかった項目は捨てずに返し、起動時に警告して気づけるようにする。
    """

    valid: list[str] = []
    invalid: list[str] = []

    for item in raw.split(","):
        origin = item.strip().rstrip("/")
        if not origin:
            continue
        if origin == "*":
            valid.append(origin)
            continue
        parts = urlsplit(origin)
        if (
            parts.scheme.lower() in {"http", "https"}
            and _NETLOC_RE.match(parts.netloc)
            and not parts.path
            and not parts.query
            and not parts.fragment
        ):
            valid.append(f"{parts.scheme.lower()}://{parts.netloc.lower()}")
        else:
            invalid.append(item.strip())

    return valid, invalid


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 実行環境 ----
    app_env: str = "local"
    # Root Logger の出力Level。未設定だと INFO のログが握り潰されて診断できない。
    log_level: str = "INFO"

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
        """CORSMiddleware へ渡す許可Origin。末尾スラッシュ・大文字は正規化済み。"""

        return classify_origins(self.cors_origins)[0]

    @property
    def invalid_cors_origins(self) -> list[str]:
        """`CORS_ORIGINS` のうち Origin として解釈できなかった項目。"""

        return classify_origins(self.cors_origins)[1]

    @property
    def contracts_assets_dir(self) -> Path:
        return self.contracts_dir / "assets"


@lru_cache
def get_settings() -> Settings:
    return Settings()
