"""POST /internal/artworks/generate-sync

ローカルデバッグ / Cloud Run実測 / 障害切り分け用の内部経路（非同期化方針Doc §7）。
旧`POST /api/v1/artworks/generate`（同期版）とまったく同じ挙動をそのまま残したもの。
Product API Contract（`/api/v1`）ではない。OpenAPI Schemaにも載せない。

`ASYNC_MODE`のような環境変数で`/api/v1/artworks/generate`の公開Contractを
切り替えることはしない。公開APIを叩きたいだけならこのEndpointは使わない。
"""

from __future__ import annotations

import logging
import time
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from ai.types import ArtworkGenerator
from app.api.v1.artworks import get_settings_dep, public_base_url, read_photos
from app.config import Settings
from app.errors import ApiError, ErrorCode
from app.models.api import GenerateSuccessResponse
from app.services.asset_store import AssetStore
from app.services.generation import generate_and_publish

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/internal/artworks", tags=["internal"])


def get_generator(request: Request) -> ArtworkGenerator:
    return request.app.state.generator


def get_asset_store(request: Request) -> AssetStore:
    return request.app.state.asset_store


@router.post("/generate-sync", response_model=GenerateSuccessResponse, include_in_schema=False)
async def generate_artwork_sync(
    request: Request,
    photos: Annotated[list[UploadFile], File()],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    generator: Annotated[ArtworkGenerator, Depends(get_generator)],
    asset_store: Annotated[AssetStore, Depends(get_asset_store)],
    memory_text: Annotated[str | None, Form(alias="memoryText")] = None,
) -> GenerateSuccessResponse:
    started_at = time.perf_counter()
    input_photos = await read_photos(photos, settings)

    try:
        response = await generate_and_publish(
            input_photos,
            memory_text,
            generator=generator,
            asset_store=asset_store,
            base_url=public_base_url(request, settings),
        )
    except ApiError:
        raise
    except Exception as exc:
        raise ApiError(
            ErrorCode.INTERNAL_ERROR, "生成に失敗しました。", log_message=str(exc)
        ) from exc
    finally:
        logger.info(
            "generate_sync elapsed=%.3fs mock_ai=%s photos=%d",
            time.perf_counter() - started_at,
            settings.mock_ai,
            len(input_photos),
        )

    return response
