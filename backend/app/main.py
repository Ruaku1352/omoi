"""FastAPI Application。Cloud Run へ載せる Deploy Unit の入口。

uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.artworks import router as artworks_router
from app.config import Settings, get_settings
from app.errors import register_exception_handlers
from app.services.asset_store import LocalDirAssetStore
from app.services.generator import build_generator

API_V1_PREFIX = "/api/v1"

logger = logging.getLogger(__name__)


def _configure_cors(app: FastAPI, settings: Settings) -> None:
    """CORSを設定し、設定ミスに起動ログで気づけるようにする。

    CORSの失敗はServer側からは見えない。許可Originが一致しなくてもHTTPは200で返り、
    足りないのはResponse Headerだけなので、curlやHealth Checkでは正常に見えて
    **ブラウザだけが失敗する**。だからここで「実際に効いている値」をログへ出す。
    """

    invalid = settings.invalid_cors_origins
    if invalid:
        logger.warning(
            "CORS_ORIGINS に Origin として解釈できない項目がある: %s / "
            "`scheme://host[:port]` 形式で書く（Pathやクォートを含めない）。"
            'gcloud なら --set-env-vars "^|^CORS_ORIGINS=..." を使う。docs/deploy.md 参照',
            ", ".join(repr(item) for item in invalid),
        )

    if not settings.allowed_origins:
        logger.warning(
            "CORS_ORIGINS が未設定または空。別OriginのFrontendからは呼べない。"
            "Requestは HTTP 200 で返るが Access-Control-Allow-Origin が付かないため、"
            "curl では成功して見えてブラウザだけが失敗する。"
            "設定方法は docs/deploy.md 参照"
        )
        return

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_methods=["POST", "GET", "OPTIONS"],
        # P0はCookie / 認証情報を使わないので allow_credentials は既定(False)のまま。
        # 有効化すると Origin ごとの厳格化が必要になるため、必要になってから足す。
        allow_headers=["*"],
    )
    # 末尾スラッシュ等を正規化した「実際に効いている値」を出す。
    # gcloud が渡した値がそのまま入っているかをここで確認できる。
    logger.info(
        "CORS許可Origin (%d件): %s",
        len(settings.allowed_origins),
        ", ".join(settings.allowed_origins),
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    # Root Loggerへ handler が無いと INFO が握り潰され、診断ログが Cloud Run に出ない。
    logging.basicConfig(
        level=settings.log_level.upper(), format="%(levelname)s %(name)s %(message)s"
    )

    app = FastAPI(title="omoi Backend", version="0.0.0")
    app.state.settings = settings

    _configure_cors(app, settings)

    register_exception_handlers(app)

    app.state.generator = build_generator(settings)
    app.state.asset_store = LocalDirAssetStore(
        root=settings.asset_dir,
        mount_path=settings.asset_mount_path,
        public_base_url=settings.asset_public_base_url,
    )

    # Asset Binary Storage方式が決まるまでの暫定静的配信。
    # Product API Contract（/api/v1 配下）ではない。
    settings.asset_dir.mkdir(parents=True, exist_ok=True)
    app.mount(
        settings.asset_mount_path,
        StaticFiles(directory=settings.asset_dir),
        name="dev-assets",
    )

    app.include_router(artworks_router, prefix=API_V1_PREFIX)

    # Health Checkは担当裁量。Product API Contractには含めない（AGENTS.md §4）。
    # CORSの実効値をここに載せる。ブラウザを開かなくても
    # `curl <backend>/health` で「何が許可されているか」を確認できるようにするため。
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, object]:
        return {
            "status": "ok",
            "mockAi": settings.mock_ai,
            "corsOrigins": settings.allowed_origins,
            "corsOriginsInvalid": settings.invalid_cors_origins,
        }

    if settings.mock_ai:
        logger.warning("MOCK_AI=true。共通Mockを返す開発・デモ用Modeで起動している。")

    return app


app = create_app()
