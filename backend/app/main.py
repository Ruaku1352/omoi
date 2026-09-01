"""FastAPI Application。Cloud Run へ載せる Deploy Unit の入口。

uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.internal.artworks import router as internal_artworks_router
from app.api.internal.jobs import router as internal_jobs_router
from app.api.v1.artworks import router as artworks_router
from app.api.v1.jobs import router as jobs_router
from app.config import Settings, get_settings
from app.errors import register_exception_handlers
from app.services.asset_store import build_asset_store
from app.services.generator import build_generator
from app.services.job_input_store import build_job_input_store
from app.services.job_runner import JobRunner
from app.services.job_store import build_job_store
from app.services.task_queue import build_task_queue

API_V1_PREFIX = "/api/v1"

# uvicornは自分のLogger("uvicorn"系)しか設定しない。Root Loggerには何もHandlerが
# 無いままなので、Python標準の"handler of last resort"（WARNING以上だけ・Formatなし）
# しか働かず、`logger.info(...)`はどこにも出ない。Cloud Run(標準出力をLogとして収集)でも
# ローカルでも同じなので、明示的に設定してINFOログを見えるようにする。
# `logging.basicConfig`はRoot Loggerに既にHandlerがあれば何もしない(冪等)ので、
# `create_app()`がテストで何度呼ばれても問題ない。
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    app = FastAPI(title="omoi Backend", version="0.0.0")
    app.state.settings = settings

    # Frontend(Firebase Hosting) と Backend(Cloud Run) は別Origin。
    # 許可Originは環境変数で管理し、Productionでは必要最小限へ限定する（AGENTS.md §2.1）。
    if settings.allowed_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.allowed_origins,
            allow_methods=["POST", "GET", "OPTIONS"],
            allow_headers=["*"],
        )
    else:
        logger.warning("CORS_ORIGINS が空。別OriginのFrontendからは呼べない。")

    register_exception_handlers(app)

    app.state.generator = build_generator(settings)
    app.state.asset_store = build_asset_store(settings)

    if settings.asset_backend == "local":
        # Asset Binary Storage方式が決まるまでの暫定静的配信。
        # Product API Contract（/api/v1 配下）ではない。
        settings.asset_dir.mkdir(parents=True, exist_ok=True)
        app.mount(
            settings.asset_mount_path,
            StaticFiles(directory=settings.asset_dir),
            name="dev-assets",
        )

    # ---- 非同期化: Job Store / Job Input Store / Task Queue ----
    app.state.job_store = build_job_store(settings)
    app.state.job_input_store = build_job_input_store(settings)
    if settings.job_input_backend == "local":
        settings.job_input_dir.mkdir(parents=True, exist_ok=True)
    app.state.job_runner = JobRunner(
        generator=app.state.generator,
        asset_store=app.state.asset_store,
        job_store=app.state.job_store,
    )
    app.state.task_queue = build_task_queue(
        settings, app.state.job_runner, app.state.job_input_store
    )

    app.include_router(artworks_router, prefix=API_V1_PREFIX)
    app.include_router(jobs_router, prefix=API_V1_PREFIX)
    app.include_router(internal_jobs_router)
    app.include_router(internal_artworks_router)

    # Health Checkは担当裁量。Product API Contractには含めない（AGENTS.md §4）。
    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok", "mockAi": str(settings.mock_ai).lower()}

    if settings.mock_ai:
        logger.warning("MOCK_AI=true。共通Mockを返す開発・デモ用Modeで起動している。")

    return app


app = create_app()
