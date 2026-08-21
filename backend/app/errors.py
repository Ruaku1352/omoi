"""Frontendへ返すError形式。正本は AGENTS.md §4。

    {"error": {"code", "message", "retryable", "details"}}

- `code` は UPPER_SNAKE_CASE
- `message` はそのままユーザーへ出せる日本語文言
- Stack Trace / API Key / Providerの生Response / 内部File Path を返さない
- 実在しないResourceのError Codeを先回りで定義しない
  （JOB_NOT_FOUND / ARTWORK_NOT_FOUND / ASSET_NOT_FOUND は該当Resourceを作ってから）
"""

from __future__ import annotations

import logging
from enum import StrEnum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class ErrorCode(StrEnum):
    INVALID_INPUT = "INVALID_INPUT"
    UNSUPPORTED_MEDIA_TYPE = "UNSUPPORTED_MEDIA_TYPE"
    PAYLOAD_TOO_LARGE = "PAYLOAD_TOO_LARGE"
    ARTWORK_VALIDATION_FAILED = "ARTWORK_VALIDATION_FAILED"
    AI_RATE_LIMITED = "AI_RATE_LIMITED"
    AI_TIMEOUT = "AI_TIMEOUT"
    AI_FAILED = "AI_FAILED"
    ASSET_BUILD_FAILED = "ASSET_BUILD_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


_STATUS_BY_CODE: dict[ErrorCode, int] = {
    ErrorCode.INVALID_INPUT: 400,
    ErrorCode.UNSUPPORTED_MEDIA_TYPE: 415,
    ErrorCode.PAYLOAD_TOO_LARGE: 413,
    ErrorCode.ARTWORK_VALIDATION_FAILED: 500,
    ErrorCode.AI_RATE_LIMITED: 429,
    ErrorCode.AI_TIMEOUT: 504,
    ErrorCode.AI_FAILED: 502,
    ErrorCode.ASSET_BUILD_FAILED: 500,
    ErrorCode.INTERNAL_ERROR: 500,
}

_RETRYABLE: frozenset[ErrorCode] = frozenset(
    {
        ErrorCode.AI_RATE_LIMITED,
        ErrorCode.AI_TIMEOUT,
        ErrorCode.AI_FAILED,
        ErrorCode.INTERNAL_ERROR,
    }
)

_GENERIC_MESSAGE = "作品の生成に失敗しました。もう一度お試しください。"


class ApiError(Exception):
    """Frontendへそのまま返せるError。

    `log_message` には内部事情を書いてよい（Server Logのみ）。
    `message` はユーザー向け文言なので内部情報を混ぜない。
    """

    def __init__(
        self,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool | None = None,
        details: Any = None,
        status_code: int | None = None,
        log_message: str | None = None,
    ) -> None:
        super().__init__(log_message or message)
        self.code = code
        self.message = message
        self.retryable = _RETRYABLE.__contains__(code) if retryable is None else retryable
        self.details = details
        self.status_code = status_code or _STATUS_BY_CODE[code]
        self.log_message = log_message or message


def error_body(code: ErrorCode, message: str, *, retryable: bool, details: Any = None) -> dict:
    return {
        "error": {
            "code": str(code),
            "message": message,
            "retryable": retryable,
            "details": details,
        }
    }


def _response(error: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content=error_body(
            error.code,
            error.message,
            retryable=error.retryable,
            details=error.details,
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        if exc.status_code >= 500:
            logger.error("%s: %s", exc.code, exc.log_message)
        else:
            logger.info("%s: %s", exc.code, exc.log_message)
        return _response(exc)

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydanticの生Errorは内部構造を晒すのでそのまま返さない。
        logger.info("INVALID_INPUT: %s", exc.errors())
        return _response(
            ApiError(
                ErrorCode.INVALID_INPUT,
                "入力内容を確認してもう一度お試しください。",
            )
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        client_error = exc.status_code < 500
        code = ErrorCode.INVALID_INPUT if client_error else ErrorCode.INTERNAL_ERROR
        message = "リクエストを処理できませんでした。" if client_error else _GENERIC_MESSAGE
        return _response(
            ApiError(code, message, status_code=exc.status_code, log_message=str(exc.detail))
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        # Stack Traceはログにだけ残し、Frontendへは出さない。
        logger.exception("INTERNAL_ERROR: %s", type(exc).__name__)
        return _response(ApiError(ErrorCode.INTERNAL_ERROR, _GENERIC_MESSAGE))
