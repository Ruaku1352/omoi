"""AI呼び出し→契約Validation→Asset公開のcore logic。

同期の内部Debug経路（`app/api/internal/artworks.py`）と、非同期Workerの
実処理（`app/services/job_runner.py`）の両方から呼ばれる共通実装。
旧`POST /api/v1/artworks/generate`が同期時代に持っていたロジックをそのまま
切り出したもので、挙動は変えていない。

失敗時は`ApiError`を投げる。`ApiError.retryable`が非同期化方針Doc §6の
Retry判定（429/503/504/timeout等は再試行、入力不正やSchema不整合は再試行しない）と
一致するようにErrorCode側で既に分類済みなので、ここでは何も特別扱いしない。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence

from pydantic import ValidationError

from ai.errors import AiError, AiNotConfiguredError, AiRateLimitedError, AiTimeoutError
from ai.types import ArtworkGenerator, InputPhoto
from app.errors import ApiError, ErrorCode
from app.models.api import GenerateSuccessResponse
from app.models.artwork import Artwork
from app.services.asset_store import AssetStore
from app.services.validation import check_artwork_rules, check_assets_present

_GENERIC_AI_MESSAGE = "作品の生成に失敗しました。もう一度お試しください。"

OnStage = Callable[[str], Awaitable[None]]


async def generate_and_publish(
    photos: Sequence[InputPhoto],
    memory_text: str | None,
    *,
    generator: ArtworkGenerator,
    asset_store: AssetStore,
    base_url: str,
    on_stage: OnStage | None = None,
) -> GenerateSuccessResponse:
    """`on_stage`はJob Runnerが進捗stage更新に使う任意Hook（同期Debug経路では渡さない）。

    `ai/`側にPer-Job Stage通知の仕組みが無いため、現状は
    「AI呼び出し前」「AI呼び出し完了後（Backend側のValidation/Asset公開中）」の
    2点でしか呼ばない。`extracting`/`composing`の細かい遷移が欲しくなったら、
    クメ先生とJob単位のObserver設計を別途相談する。
    """

    try:
        result = await generator.generate(photos, memory_text)
    except AiTimeoutError as exc:
        raise ApiError(ErrorCode.AI_TIMEOUT, _GENERIC_AI_MESSAGE, log_message=str(exc)) from exc
    except AiRateLimitedError as exc:
        raise ApiError(
            ErrorCode.AI_RATE_LIMITED,
            "混み合っています。少し時間をおいてもう一度お試しください。",
            log_message=str(exc),
        ) from exc
    except AiNotConfiguredError as exc:
        # 設定ミス（API Key / モデル未設定等）はRetryしても改善しない
        # （非同期化方針Doc §6: 認証・権限エラー・実装バグ等はRetry対象外）。
        # AiErrorのSubclassなので下のexcept AiErrorより先に置く必要がある。
        raise ApiError(
            ErrorCode.AI_FAILED,
            _GENERIC_AI_MESSAGE,
            retryable=False,
            log_message=str(exc),
        ) from exc
    except AiError as exc:
        # AI失敗をMockで埋め合わせない。失敗はそのままErrorとして返す。
        raise ApiError(ErrorCode.AI_FAILED, _GENERIC_AI_MESSAGE, log_message=str(exc)) from exc

    if on_stage is not None:
        await on_stage("finalizing")

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
        manifest = asset_store.publish(artwork.artwork_id, result.assets, base_url)
    except Exception as exc:
        raise ApiError(
            ErrorCode.ASSET_BUILD_FAILED,
            _GENERIC_AI_MESSAGE,
            log_message=f"asset publish failed: {type(exc).__name__}",
        ) from exc

    return GenerateSuccessResponse(artwork=artwork, asset_manifest=manifest)
