"""POST /api/v1/physical-output/exports

Physical Output候補Endpoint。入力は確定Artwork Data + Assetsで、
出力は3Dプリント用STL ZIP、写真紙用PDF、または2L写真紙用JPEG ZIP。

Artwork Dataを物理mm値で上書きしない。製造条件はBackend側のPoC既定値
（rail / 2L Landscape / 4行 x 3穴）を使い、physicalOutputConfig JSONは
必要な場合だけ任意overrideとして受け取る。
"""

from __future__ import annotations

import logging
import pathlib
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile

from app.config import Settings
from app.errors import ApiError, ErrorCode
from app.services.physical_output import (
    PhysicalOutputBuildError,
    PhysicalOutputInputError,
    UploadedAsset,
    build_asset_blobs,
    build_physical_output_archive,
    build_physical_output_pdf,
    build_physical_output_photo_jpeg_zip,
    parse_artwork_payload,
    parse_physical_output_config,
    required_layer_asset_ids,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/physical-output", tags=["physical-output"])


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


@router.post(
    "/exports",
    responses={
        200: {
            "content": {
                "application/zip": {},
                "application/pdf": {},
            },
            "description": "3Dプリンター用STL ZIP、写真紙用PDF、または2L写真紙用JPEG ZIP",
        }
    },
)
async def create_physical_output_export(
    request: Request,
    artwork: Annotated[str, Form(description="確定Artwork Data JSON")],
    assets: Annotated[list[UploadFile], File(description="Artworkが参照するAsset画像")],
    settings: Annotated[Settings, Depends(get_settings_dep)],
    output_format: Annotated[
        str,
        Form(
            alias="outputFormat",
            description=(
                "stlZip は3Dプリンター用ZIP、photoPdf は写真紙用PDF、"
                "photoJpegZip は2L写真紙用JPEG ZIP"
            ),
        ),
    ] = "stlZip",
    physical_output_config: Annotated[
        str | None,
        Form(
            alias="physicalOutputConfig",
            description="任意override。未指定ならBackend側のPoC既定値を使う",
        ),
    ] = None,
) -> Response:
    del request
    try:
        if output_format not in {"stlZip", "photoPdf", "photoJpegZip"}:
            raise PhysicalOutputInputError(
                ["outputFormat must be stlZip, photoPdf, or photoJpegZip"]
            )
        parsed_artwork = parse_artwork_payload(artwork)
        config = parse_physical_output_config(physical_output_config)
        layer_asset_ids = required_layer_asset_ids(parsed_artwork)
        uploaded_assets = []
        for upload in assets:
            filename = upload.filename or ""
            if _asset_id_from_upload_filename(filename) not in layer_asset_ids:
                continue
            uploaded_assets.append(
                UploadedAsset(
                    filename=filename,
                    content_type=upload.content_type,
                    data=await upload.read(),
                )
            )
        asset_blobs = build_asset_blobs(parsed_artwork, uploaded_assets, settings)
        if output_format == "photoPdf":
            archive = build_physical_output_pdf(
                artwork=parsed_artwork,
                assets=asset_blobs,
                config=config,
            )
        elif output_format == "photoJpegZip":
            archive = build_physical_output_photo_jpeg_zip(
                artwork=parsed_artwork,
                assets=asset_blobs,
                config=config,
            )
        else:
            archive = build_physical_output_archive(
                artwork=parsed_artwork,
                assets=asset_blobs,
                config=config,
            )
    except PhysicalOutputInputError as exc:
        raise ApiError(
            ErrorCode.INVALID_INPUT,
            "印刷用データの入力を確認してください。",
            details={"issues": exc.issues},
            log_message=str(exc),
        ) from exc
    except PhysicalOutputBuildError as exc:
        raise ApiError(
            ErrorCode.ASSET_BUILD_FAILED,
            "印刷用データの生成に失敗しました。もう一度お試しください。",
            log_message=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("physical output export failed")
        raise ApiError(
            ErrorCode.INTERNAL_ERROR,
            "印刷用データの生成に失敗しました。もう一度お試しください。",
            log_message=f"{type(exc).__name__}: {exc}",
        ) from exc

    return Response(
        content=archive.content,
        media_type=archive.media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{archive.filename}"',
            "X-Omoi-Physical-Warning-Count": str(len(archive.report.get("warnings", []))),
        },
    )


def _asset_id_from_upload_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/").split("/")[-1]
    return pathlib.PurePosixPath(normalized).stem
