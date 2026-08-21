"""POST /api/v1/artworks/generate

P0で作るEndpointはこれだけ【FIX】。
取得 / 更新 / finalize / bundle / jobs は必要性が確定するまで作らない（AGENTS.md §4）。

同期 / 非同期どちらで返すかは【PoC後FIX】。まずは同期で実装し、
代表ケースの実測時間を計測して判断する。Job Store / Pollingを先回りで作らない。
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError

from ai.errors import AiError, AiRateLimitedError, AiTimeoutError
from ai.types import ArtworkGenerator, InputPhoto
from app.config import Settings, get_settings
from app.errors import ApiError, ErrorCode
from app.models.api import GenerateArtworkResponse
from app.models.artwork import Artwork
from app.services.asset_store import AssetStore
from app.services.validation import check_artwork_rules, check_assets_present

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/artworks", tags=["artworks"])

ACCEPTED_PHOTO_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
"""JPEG / PNG / WebP を基準とする。HEIC / HEIF は実機確認後【PoC後FIX】。"""

_GENERIC_AI_MESSAGE = "作品の生成に失敗しました。もう一度お試しください。"


def get_generator(request: Request) -> ArtworkGenerator:
    return request.app.state.generator


def get_asset_store(request: Request) -> AssetStore:
    return request.app.state.asset_store


async def _read_photos(photos: list[UploadFile], settings: Settings) -> list[InputPhoto]:
    if not photos:
        raise ApiError(ErrorCode.INVALID_INPUT, "写真を1枚以上選んでください。")
    if len(photos) > settings.max_photos:
        raise ApiError(
            ErrorCode.PAYLOAD_TOO_LARGE,
            f"写真は{settings.max_photos}枚までにしてください。",
        )

    total = 0
    result: list[InputPhoto] = []
    for photo in photos:
        if photo.content_type not in ACCEPTED_PHOTO_MIME_TYPES:
            raise ApiError(
                ErrorCode.UNSUPPORTED_MEDIA_TYPE,
                "対応していない画像形式が含まれています。JPEG / PNG / WebP を選んでください。",
                log_message=f"unsupported content_type: {photo.content_type}",
            )
        data = await photo.read()
        if len(data) > settings.max_photo_bytes:
            raise ApiError(ErrorCode.PAYLOAD_TOO_LARGE, "写真1枚あたりのサイズが大きすぎます。")
        total += len(data)
        if total > settings.max_total_upload_bytes:
            raise ApiError(ErrorCode.PAYLOAD_TOO_LARGE, "写真の合計サイズが大きすぎます。")
        result.append(
            InputPhoto(
                filename=photo.filename or "",
                mime_type=photo.content_type or "",
                data=data,
            )
        )
    return result


@router.post("/generate", response_model=GenerateArtworkResponse, response_model_by_alias=True)
async def generate_artwork(
    request: Request,
    photos: Annotated[list[UploadFile], File(description="複数画像。固定5枚ではない。")],
    settings: Annotated[Settings, Depends(get_settings)],
    generator: Annotated[ArtworkGenerator, Depends(get_generator)],
    asset_store: Annotated[AssetStore, Depends(get_asset_store)],
    memory_text: Annotated[str | None, Form(alias="memoryText")] = None,
) -> GenerateArtworkResponse:
    input_photos = await _read_photos(photos, settings)

    try:
        result = await generator.generate(input_photos, memory_text)
    except AiTimeoutError as exc:
        raise ApiError(ErrorCode.AI_TIMEOUT, _GENERIC_AI_MESSAGE, log_message=str(exc)) from exc
    except AiRateLimitedError as exc:
        raise ApiError(
            ErrorCode.AI_RATE_LIMITED,
            "混み合っています。少し時間をおいてもう一度お試しください。",
            log_message=str(exc),
        ) from exc
    except AiError as exc:
        # AI失敗をMockで埋め合わせない。失敗はそのままErrorとして返す。
        raise ApiError(ErrorCode.AI_FAILED, _GENERIC_AI_MESSAGE, log_message=str(exc)) from exc

    # AI Moduleの結果をそのまま信用せず、必ず契約へ通す。
    try:
        artwork = Artwork.model_validate(result.artwork)
    except ValidationError as exc:
        raise ApiError(
            ErrorCode.ARTWORK_VALIDATION_FAILED,
            _GENERIC_AI_MESSAGE,
            log_message=f"artwork schema violation: {exc.error_count()} error(s)",
        ) from exc

    rule_errors = check_artwork_rules(artwork) + check_assets_present(artwork, result.assets)
    if rule_errors:
        raise ApiError(
            ErrorCode.ARTWORK_VALIDATION_FAILED,
            _GENERIC_AI_MESSAGE,
            log_message="; ".join(rule_errors),
        )

    try:
        manifest = asset_store.publish(artwork.artwork_id, result.assets, str(request.base_url))
    except Exception as exc:
        raise ApiError(
            ErrorCode.ASSET_BUILD_FAILED,
            _GENERIC_AI_MESSAGE,
            log_message=f"asset publish failed: {type(exc).__name__}",
        ) from exc

    return GenerateArtworkResponse(artwork=artwork, asset_manifest=manifest)
