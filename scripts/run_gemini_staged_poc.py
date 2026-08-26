"""Gemini API経路をStageごとに観測する、Git管理外のPoC runner。

このscriptはProduction APIやShared Contractを変更しない。失敗したStageで必ず停止し、
Mockへのfallback・Provider retry・HEIC変換は行わない。
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from google import genai
from pydantic import BaseModel, Field, ValidationError

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

sys.path.insert(0, str(BACKEND_DIR))

from ai.errors import AiError, AiNotConfiguredError  # noqa: E402
from ai.gemini import GeminiSemanticPlanner  # noqa: E402
from ai.image_ops import decode_photo  # noqa: E402
from ai.quality import assess_mask  # noqa: E402
from ai.segmentation import LazyEfficientSamOnnxSegmenter  # noqa: E402
from ai.types import InputPhoto  # noqa: E402
from app.config import Settings  # noqa: E402

P0_MIME_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
SKIPPED_EXTENSIONS = frozenset({".heic", ".heif"})
PROVISIONAL_SELECTED_FILES = (
    "IMG_5041.jpg",  # 着物姿の人物
    "IMG_2612.jpg",  # 庭園・池・噴水
    "IMG_2718.png",  # 複雑な木造建築模型
    "IMG_2853.jpg",  # 茶菓子
    "IMG_2844.png",  # 絵付け体験
)
MEMORY_TEXT = "金沢観光で、庭園・伝統建築・食・文化体験を楽しんだ大切な一日。"


class MinimalCandidate(BaseModel):
    label: str = Field(min_length=1)
    source_photo_index: int = Field(ge=0)
    importance: float = Field(ge=0, le=1)


class MinimalStructuredResponse(BaseModel):
    candidates: list[MinimalCandidate] = Field(min_length=1)


@dataclass(frozen=True)
class StageRecord:
    stage: str
    model: str
    success: bool
    error_type: str | None
    latency_ms: float
    photo_count: int
    selected_photo_files: tuple[str, ...]
    mime_type_counts: dict[str, int]
    input_image_bytes: dict[str, int]
    total_image_bytes: int
    usage: dict[str, int | None]
    http_api_result: str
    schema_validation: str | None
    notes: str
    candidate_count: int | None = None
    bbox_available: bool | None = None
    success_layer_count: int | None = None
    semantic_planning_latency_ms: float | None = None
    segmentation_latency_ms: float | None = None
    layer_build_latency_ms: float | None = None
    mask_scores: tuple[float | None, ...] = ()
    mask_area_ratios: tuple[float | None, ...] = ()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--photos-dir", type=Path, default=REPO_ROOT / "poc-images")
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "poc-output")
    # 手動REST Smoke Testで確認済みのPoC専用暫定モデル。最終採用モデルではない。
    parser.add_argument("--model", default="gemini-3.5-flash-lite")
    parser.add_argument("--timeout-ms", type=int, default=30_000)
    parser.add_argument("--memory-text", default=MEMORY_TEXT)
    return parser.parse_args()


def load_provisional_photos(photos_dir: Path) -> tuple[list[InputPhoto], list[str]]:
    """固定代表5枚を読み、HEIC/HEIFは明示的にskip情報だけを返す。"""

    skipped = sorted(
        path.name
        for path in photos_dir.iterdir()
        if path.is_file() and path.suffix.lower() in SKIPPED_EXTENSIONS
    )
    photos: list[InputPhoto] = []
    for filename in PROVISIONAL_SELECTED_FILES:
        path = photos_dir / filename
        extension = path.suffix.lower()
        if not path.is_file() or extension not in P0_MIME_TYPES:
            raise ValueError(f"P0 PoC対象の代表画像が見つかりません: {filename}")
        photos.append(InputPhoto(path.name, P0_MIME_TYPES[extension], path.read_bytes()))
    return photos, skipped


async def run(args: argparse.Namespace) -> int:
    if args.timeout_ms <= 0:
        raise SystemExit("--timeout-ms は正の整数にしてください")
    photos, skipped_heic = load_provisional_photos(args.photos_dir)
    output = args.output_dir / datetime.now().strftime("%Y%m%d-%H%M%S")
    output.mkdir(parents=True)
    model = args.model
    settings = Settings()
    if not settings.gemini_api_key:
        raise SystemExit("GEMINI_API_KEYが未設定です")
    client = genai.Client(api_key=settings.gemini_api_key)
    records: list[StageRecord] = []

    async def stage(name: str, photos_for_stage: list[InputPhoto], operation) -> bool:
        record = await _run_stage(
            name,
            model,
            photos_for_stage,
            operation,
            timeout_ms=args.timeout_ms,
            skipped_heic=skipped_heic,
        )
        records.append(record)
        _write_report(output, model, records, skipped_heic)
        return record.success

    if not await stage(
        "stage_1_text_smoke", [], lambda: _text_smoke(client, model, args.timeout_ms)
    ):
        return 1
    if not await stage(
        "stage_2_image_one",
        [photos[0]],
        lambda: _image_one(client, model, photos[0], args.timeout_ms),
    ):
        return 1
    if not await stage(
        "stage_3_image_five", photos, lambda: _image_five(client, model, photos, args.timeout_ms)
    ):
        return 1
    if not await stage(
        "stage_4_structured_output",
        photos,
        lambda: _minimal_structured(client, model, photos, args.timeout_ms),
    ):
        return 1
    semantic_plan_holder: list[Any] = []

    async def semantic_stage() -> dict[str, Any]:
        result = await _semantic_plan(client, model, photos, args.memory_text, args.timeout_ms)
        semantic_plan_holder.append(result.pop("_plan"))
        return result

    if not await stage("stage_5_semantic_planner", photos, semantic_stage):
        return 1
    # Stage 6はStage 5のSemanticPlanを再利用し、Compositionを通さずLayer PNGまでを確認する。
    semantic_latency = records[-1].latency_ms
    if not await stage(
        "stage_6_layers",
        photos,
        lambda: _layers_only(semantic_plan_holder[0], photos, output, settings, semantic_latency),
    ):
        return 1
    return 0


async def _run_stage(
    stage: str,
    model: str,
    photos: list[InputPhoto],
    operation,
    *,
    timeout_ms: int,
    skipped_heic: list[str],
) -> StageRecord:
    started = time.perf_counter()
    metadata = _photo_metadata(photos)
    try:
        result = await operation()
        extra = result if isinstance(result, dict) else {}
        return StageRecord(
            stage=stage,
            model=model,
            success=True,
            error_type=None,
            latency_ms=_elapsed_ms(started),
            **metadata,
            usage=extra.get("usage", {}),
            http_api_result=extra.get("http_api_result", "http_200_sdk_response"),
            schema_validation=extra.get("schema_validation"),
            notes=_notes(skipped_heic),
            candidate_count=extra.get("candidate_count"),
            bbox_available=extra.get("bbox_available"),
            success_layer_count=extra.get("success_layer_count"),
            semantic_planning_latency_ms=extra.get("semantic_planning_latency_ms"),
            segmentation_latency_ms=extra.get("segmentation_latency_ms"),
            layer_build_latency_ms=extra.get("layer_build_latency_ms"),
            mask_scores=tuple(extra.get("mask_scores", ())),
            mask_area_ratios=tuple(extra.get("mask_area_ratios", ())),
        )
    except Exception as exc:
        error_type, http_result = classify_error(exc)
        return StageRecord(
            stage=stage,
            model=model,
            success=False,
            error_type=error_type,
            latency_ms=_elapsed_ms(started),
            **metadata,
            usage={},
            http_api_result=http_result,
            schema_validation="failed" if error_type == "schema_validation_failure" else None,
            notes=_notes(skipped_heic),
        )


async def _text_smoke(client: genai.Client, model: str, timeout_ms: int) -> dict[str, Any]:
    response = await _generate(client, model, "Reply with exactly: OK", timeout_ms=timeout_ms)
    return {"usage": _usage(response), "http_api_result": _http_result(response)}


async def _image_one(
    client: genai.Client, model: str, photo: InputPhoto, timeout_ms: int
) -> dict[str, Any]:
    response = await _generate(
        client,
        model,
        _image_input("Briefly describe this image in one sentence.", [photo]),
        timeout_ms=timeout_ms,
    )
    return {"usage": _usage(response), "http_api_result": _http_result(response)}


async def _image_five(
    client: genai.Client, model: str, photos: list[InputPhoto], timeout_ms: int
) -> dict[str, Any]:
    response = await _generate(
        client,
        model,
        _image_input("これらの写真に共通する旅行体験を2〜3文で説明してください。", photos),
        timeout_ms=timeout_ms,
    )
    return {"usage": _usage(response), "http_api_result": _http_result(response)}


async def _minimal_structured(
    client: genai.Client, model: str, photos: list[InputPhoto], timeout_ms: int
) -> dict[str, Any]:
    response = await _generate(
        client,
        model,
        _image_input(
            "写真群から思い出を表す候補を1〜3件返してください。"
            "source_photo_indexは0始まり、importanceは0から1です。",
            photos,
        ),
        timeout_ms=timeout_ms,
        response_schema=MinimalStructuredResponse.model_json_schema(),
    )
    parsed = MinimalStructuredResponse.model_validate_json(response.output_text)
    return {
        "usage": _usage(response),
        "http_api_result": _http_result(response),
        "schema_validation": "passed",
        "candidate_count": len(parsed.candidates),
    }


async def _semantic_plan(
    client: genai.Client,
    model: str,
    photos: list[InputPhoto],
    memory_text: str,
    timeout_ms: int,
) -> dict[str, Any]:
    planner = GeminiSemanticPlanner(client, model, 1536, timeout_ms)
    plan = await planner.plan([decode_photo(photo).image for photo in photos], memory_text)
    return {
        "schema_validation": "passed",
        "candidate_count": len(plan.candidates),
        "bbox_available": all(
            component.box_2d for item in plan.candidates for component in item.components
        ),
        "_plan": plan,
    }


async def _layers_only(
    plan: Any,
    photos: list[InputPhoto],
    output: Path,
    settings: Settings,
    semantic_planning_latency_ms: float,
) -> dict[str, Any]:
    decoded = [decode_photo(photo) for photo in photos]
    segmenter = LazyEfficientSamOnnxSegmenter(
        settings.efficientsam_model_path, settings.segmentation_max_side
    )
    layers_dir = output / "layers"
    layers_dir.mkdir(exist_ok=True)
    success = 0
    segmentation_elapsed_ms = 0.0
    layer_build_elapsed_ms = 0.0
    scores: list[float | None] = []
    areas: list[float | None] = []
    for candidate in sorted(plan.candidates, key=lambda item: item.importance, reverse=True)[
        : settings.target_layer_max
    ]:
        if candidate.source_photo_index >= len(decoded):
            continue
        masks = []
        for component in candidate.components:
            from ai.image_ops import gemini_box_to_px

            image = decoded[candidate.source_photo_index].image
            started = time.perf_counter()
            segmented = await asyncio.to_thread(
                segmenter.segment, image, gemini_box_to_px(component.box_2d, image.size)
            )
            segmentation_elapsed_ms += _elapsed_ms(started)
            quality = assess_mask(segmented.mask, segmented.prompt_box_px, segmented.score)
            if not quality.accepted:
                continue
            masks.append(segmented.mask)
            scores.append(quality.score)
            areas.append(quality.area_ratio)
        if not masks:
            continue
        from ai.image_ops import mask_to_rgba_png, union_masks

        started = time.perf_counter()
        png, _, _ = mask_to_rgba_png(
            decoded[candidate.source_photo_index].image,
            union_masks(masks),
            padding_px=settings.layer_padding_px,
        )
        layer_build_elapsed_ms += _elapsed_ms(started)
        (layers_dir / f"{success + 1:02d}.png").write_bytes(png)
        success += 1
    if not success:
        raise RuntimeError("layer_build_failed")
    return {
        "candidate_count": len(plan.candidates),
        "bbox_available": True,
        "success_layer_count": success,
        "semantic_planning_latency_ms": semantic_planning_latency_ms,
        "segmentation_latency_ms": segmentation_elapsed_ms,
        "layer_build_latency_ms": layer_build_elapsed_ms,
        "mask_scores": scores,
        "mask_area_ratios": areas,
    }


async def _generate(
    client: genai.Client,
    model: str,
    contents: str | list[dict[str, str]],
    *,
    timeout_ms: int,
    response_schema: dict[str, Any] | None = None,
):
    request: dict[str, Any] = {"model": model, "input": contents, "timeout": timeout_ms / 1000}
    if response_schema is not None:
        request["response_format"] = {
            "type": "text",
            "mime_type": "application/json",
            "schema": response_schema,
        }
    return await asyncio.to_thread(
        client.interactions.create,
        **request,
    )


def classify_error(exc: Exception) -> tuple[str, str]:
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    name = type(exc).__name__.lower()
    if status == 429 or "rate" in name or "resourceexhausted" in name:
        return "rate_limited", "http_429"
    if status == 503:
        return "service_unavailable", "http_503"
    if status == 504:
        return "gateway_timeout", "http_504"
    if "readtimeout" in name or "read_timeout" in name:
        return "client_timeout", "client_read_timeout"
    if "timeout" in name or "deadline" in name:
        return "client_timeout", "client_timeout"
    if isinstance(exc, ValidationError):
        return "schema_validation_failure", "no_http_response"
    if isinstance(exc, AiNotConfiguredError):
        return "local_configuration_error", "no_http_request"
    if isinstance(exc, AiError):
        return "e2e_integration_error", "no_http_request"
    if isinstance(exc, ValueError):
        return "input_selection_error", "no_http_response"
    return "provider_error", f"http_{status}" if status else "provider_error"


def _photo_metadata(photos: list[InputPhoto]) -> dict[str, Any]:
    mime_counts: dict[str, int] = {}
    byte_counts: dict[str, int] = {}
    for photo in photos:
        mime_counts[photo.mime_type] = mime_counts.get(photo.mime_type, 0) + 1
        byte_counts[photo.filename] = len(photo.data)
    return {
        "photo_count": len(photos),
        "selected_photo_files": tuple(photo.filename for photo in photos),
        "mime_type_counts": mime_counts,
        "input_image_bytes": byte_counts,
        "total_image_bytes": sum(byte_counts.values()),
    }


def _image_input(prompt: str, photos: list[InputPhoto]) -> list[dict[str, str]]:
    """Interactions APIのcontent block形式へ、P0画像をBase64で明示変換する。"""

    return [
        {"type": "text", "text": prompt},
        *[
            {
                "type": "image",
                "data": base64.b64encode(photo.data).decode("ascii"),
                "mime_type": photo.mime_type,
            }
            for photo in photos
        ],
    ]


def _usage(response: Any) -> dict[str, int | None]:
    usage = getattr(response, "usage", None) or getattr(response, "usage_metadata", None)
    return {
        "input": getattr(usage, "input_tokens", None) or getattr(usage, "prompt_token_count", None),
        "output": getattr(usage, "output_tokens", None)
        or getattr(usage, "candidates_token_count", None),
        "thought": getattr(usage, "thought_tokens", None)
        or getattr(usage, "thoughts_token_count", None),
        "total": getattr(usage, "total_tokens", None) or getattr(usage, "total_token_count", None),
    }


def _http_result(response: Any) -> str:
    status = getattr(response, "status", None)
    return f"http_200_status_{status}" if status else "http_200_sdk_response"


def _notes(skipped_heic: list[str]) -> str:
    return f"P0ではHEIC/HEIFを除外: {', '.join(skipped_heic) if skipped_heic else 'none'}"


def _write_report(
    output: Path, model: str, records: list[StageRecord], skipped_heic: list[str]
) -> None:
    payload = {
        "model": model,
        "mvpMemoryTextRequired": True,
        "representative_selection": {
            "status": "provisional",
            "files": list(PROVISIONAL_SELECTED_FILES),
        },
        "p0_excluded_files": {
            "policy": "HEIC/HEIF are excluded without conversion",
            "files": skipped_heic,
        },
        "stages": [asdict(record) for record in records],
    }
    (output / "metrics.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run(parse_args())))
