"""POST /api/v1/artworks/generate

P0で作るEndpointはこれと `GET /api/v1/jobs/{jobId}` の2つ【FIX】。
取得 / 更新 / finalize / bundle Endpointは必要性が確定するまで作らない（AGENTS.md §4）。

正式なFrontend ↔ Backend Contractは非同期一本【FIX：方針】。
写真5枚の実測でAI処理だけで234秒かかることが確認されたため
（ブラウザが4分固まる）、同期のままでは公開Contractとして成立しない。
`ASYNC_MODE`等の環境変数でこのEndpointの公開Response Contractを
切り替えることはしない。同期処理は `app/api/internal/artworks.py` に
ローカルデバッグ / Cloud Run実測 / 障害切り分け用の内部経路として残す。
"""

from __future__ import annotations

import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from ai.types import InputPhoto
from app.config import Settings
from app.errors import ApiError, ErrorCode
from app.models.job import JobAccepted
from app.services.job_store import JobStore
from app.services.task_queue import TaskQueue

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/artworks", tags=["artworks"])

ACCEPTED_PHOTO_MIME_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})
"""JPEG / PNG / WebP を基準とする。HEIC / HEIF は実機確認後【PoC後FIX】。"""


def get_settings_dep(request: Request) -> Settings:
    """`app.state.settings`（`create_app()`へ渡されたSettings）を返す。

    `app.config.get_settings()` を直接Dependしないのは、Requestごとに
    `app.state.*`を作った時のSettingsと別のSettingsを見てしまう食い違いを
    避けるため（テスト時にSettingsを差し替えても反映されない不具合になる）。
    """

    return request.app.state.settings


def get_task_queue(request: Request) -> TaskQueue:
    return request.app.state.task_queue


def get_job_store(request: Request) -> JobStore:
    return request.app.state.job_store


def public_base_url(request: Request, settings: Settings) -> str:
    """Asset ManifestのURLに使うBase URL。

    Cloud RunはTLSをFrontendで終端するため、Container内から見たRequestは常にhttp。
    公開Endpoint自体は常にhttpsでしか外部から到達できない（httpは自動でhttpsへ
    Redirectされる）ので、`APP_ENV=deployed` のときだけschemeをhttpsへ補正する。
    ローカル開発（`APP_ENV=local` 既定値）はhttpのまま変えない。
    `ASSET_PUBLIC_BASE_URL` が設定されていればこの関数の結果はAssetStore側で無視される。
    """

    base_url = str(request.base_url)
    if settings.app_env == "deployed" and base_url.startswith("http://"):
        base_url = "https://" + base_url[len("http://") :]
    return base_url


async def read_photos(photos: list[UploadFile], settings: Settings) -> list[InputPhoto]:
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


@router.post("/generate", response_model=JobAccepted, status_code=202)
async def generate_artwork(
    request: Request,
    photos: Annotated[list[UploadFile], File(description="複数画像。固定5枚ではない。")],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    task_queue: Annotated[TaskQueue, Depends(get_task_queue)],
    job_store: Annotated[JobStore, Depends(get_job_store)],
    memory_text: Annotated[str | None, Form(alias="memoryText")] = None,
) -> JobAccepted:
    input_photos = await read_photos(photos, settings)

    job_id = uuid.uuid4().hex
    base_url = public_base_url(request, settings)

    # Job作成・Task投入が失敗したら202を返さず素直にErrorにする
    # （非同期化方針Doc §3: GCS保存・Firestore Job作成・Cloud Tasks enqueue成功後に202）。
    try:
        await job_store.create(job_id, memory_text=memory_text)
        await task_queue.enqueue(job_id, input_photos, memory_text, base_url=base_url)
    except Exception as exc:
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "作品の生成に失敗しました。もう一度お試しください。",
            log_message=f"job enqueue failed: {type(exc).__name__}: {exc}",
        ) from exc

    logger.info(
        "job_enqueued job_id=%s mock_ai=%s photos=%d", job_id, settings.mock_ai, len(input_photos)
    )
    return JobAccepted(job_id=job_id)
