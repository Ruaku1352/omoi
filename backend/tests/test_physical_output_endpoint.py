from __future__ import annotations

import io
import json
import re
import zipfile
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from PIL import Image

from app.config import REPO_ROOT, Settings
from app.main import create_app

CONTRACTS = REPO_ROOT / "contracts"
EXT_BY_MIME = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
POINTS_PER_MM = 72.0 / 25.4
PHOTO_2L_LANDSCAPE_WIDTH_MM = 178.0
PHOTO_2L_LANDSCAPE_HEIGHT_MM = 127.0
MEDIA_BOX_PATTERN = re.compile(
    rb"/MediaBox\s*\[\s*(?:0|0\.0+)\s+(?:0|0\.0+)\s+([0-9.]+)\s+([0-9.]+)\s*\]"
)


def _mock_artwork() -> dict[str, Any]:
    return json.loads((CONTRACTS / "mock" / "artwork.json").read_text(encoding="utf-8"))


def _pdf_media_boxes(pdf_bytes: bytes) -> list[tuple[float, float]]:
    return [
        (float(width), float(height))
        for width, height in MEDIA_BOX_PATTERN.findall(pdf_bytes)
    ]


def _asset_uploads(artwork: dict[str, Any]) -> list[tuple[str, tuple[str, bytes, str]]]:
    assets: dict[str, str] = {}
    for photo in artwork["sourcePhotos"]:
        asset = photo["asset"]
        assets[asset["assetId"]] = asset["mimeType"]
    for layer in artwork["layers"]:
        asset = layer["asset"]
        assets[asset["assetId"]] = asset["mimeType"]
        for candidate in layer["replacementCandidates"]:
            candidate_asset = candidate["asset"]
            assets[candidate_asset["assetId"]] = candidate_asset["mimeType"]

    files = []
    for asset_id, mime_type in sorted(assets.items()):
        ext = EXT_BY_MIME[mime_type]
        path = CONTRACTS / "assets" / f"{asset_id}.{ext}"
        files.append(("assets", (path.name, path.read_bytes(), mime_type)))
    return files


def _layer_asset_uploads(artwork: dict[str, Any]) -> list[tuple[str, tuple[str, bytes, str]]]:
    files = []
    for layer in artwork["layers"]:
        asset = layer["asset"]
        ext = EXT_BY_MIME[asset["mimeType"]]
        path = CONTRACTS / "assets" / f"{asset['assetId']}.{ext}"
        files.append(("assets", (path.name, path.read_bytes(), asset["mimeType"])))
    return files


def _png_bytes(width_px: int, height_px: int, color: tuple[int, int, int, int]) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (width_px, height_px), color).save(buffer, "PNG")
    return buffer.getvalue()


def test_physical_output_exports_zip_from_artwork_and_assets(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={"artwork": json.dumps(artwork)},
        files=_asset_uploads(artwork),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="omoi-physical-output-mock-artwork-001'
    )

    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        names = set(archive.namelist())
        assert "artwork.json" in names
        assert "flat-photo-parts-report.json" in names
        assert "physical-output-config.json" in names
        assert "print/flat-photo-print-layout.svg" not in names
        assert "print/flat-photo-print-layout.pdf" not in names
        assert any(name.startswith("stl/") and name.endswith(".stl") for name in names)

        report = json.loads(archive.read("flat-photo-parts-report.json"))
        assert report["artworkId"] == artwork["artworkId"]
        assert report["schemaImpact"]["needsArtworkSchemaChange"] is False
        assert report["flatPhotoPartConfig"]["targetWidthMm"] == 178.0
        assert report["flatPhotoPartConfig"]["supportMode"] == "rail"
        assert report["flatPhotoPartConfig"]["partSlotLabelEngraveDepthMm"] == 0.35
        assert report["flatPhotoPartConfig"]["verticalSupportWidthMm"] == 4.0
        assert report["flatPhotoPartConfig"]["supportRootPadWidthMm"] == 12.0
        assert report["flatPhotoPartConfig"]["supportRootPadHeightMm"] == 5.0
        assert report["flatPhotoPartConfig"]["supportRootOverlapMm"] == 2.0
        assert report["outputs"]["printLayoutPdf"] is None
        assert report["outputs"]["printLayoutSvg"] is None
        assert all(part["outputStl"].startswith("stl/") for part in report["parts"])
        assert all(part["assemblyMarks"] for part in report["parts"])
        assert all(part["slotAssignment"]["selectedBy"] == "rowRail" for part in report["parts"])
        assert all(len(part["slotAssignment"]["slotLabels"]) == 3 for part in report["parts"])
        assert all(len(part["rails"]) == 1 for part in report["parts"])
        assert all(len(part["tabs"]) == 3 for part in report["parts"])
        lifted_parts = [
            part
            for part in report["parts"]
            if part["dimensionsMm"]["verticalSupportHeightMm"] > 0
        ]
        assert lifted_parts
        assert all(part["verticalSupports"] for part in lifted_parts)
        assert all(
            support["heightMm"] > support["overlapMm"]
            for part in lifted_parts
            for support in part["verticalSupports"]
        )
        assert all(
            support["rootPad"]["widthMm"] >= support["widthMm"]
            and (
                support["rootPad"]["heightMm"]
                >= report["flatPhotoPartConfig"]["supportRootPadHeightMm"]
            )
            and (
                support["rootPad"]["overlapIntoImageMm"]
                == report["flatPhotoPartConfig"]["supportRootOverlapMm"]
            )
            and support["rootPad"]["yMm"] < support["yMm"]
            for part in lifted_parts
            for support in part["verticalSupports"]
        )
        assert all(
            mark["label"] == part["slotAssignment"]["assemblyLabel"]
            for part in report["parts"]
            for mark in part["assemblyMarks"]
        )
        assert "omoi-physical-output-" not in json.dumps(report, ensure_ascii=False)


def test_physical_output_cover_crops_opaque_background_to_2l(
    client: TestClient,
) -> None:
    artwork = _mock_artwork()
    background = next(layer for layer in artwork["layers"] if layer["layerIndex"] == 0)
    background["asset"] = {
        "assetId": "opaque-background",
        "mimeType": "image/png",
        "widthPx": 140,
        "heightPx": 104,
    }
    background["scale"] = 0.8
    artwork["layers"] = [background]

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "physicalOutputConfig": json.dumps({"gridCellMm": 20.0}),
        },
        files=[
            (
                "assets",
                (
                    "opaque-background.png",
                    _png_bytes(140, 104, (32, 64, 96, 255)),
                    "image/png",
                ),
            )
        ],
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        report = json.loads(archive.read("flat-photo-parts-report.json"))

    [background_part] = report["parts"]
    assert report["flatPhotoPartConfig"]["backgroundFillMode"] == "cover-2l"
    assert background_part["imageAreaMm"] == {
        "xMm": 0.0,
        "yMm": 0.0,
        "widthMm": PHOTO_2L_LANDSCAPE_WIDTH_MM,
        "heightMm": PHOTO_2L_LANDSCAPE_HEIGHT_MM,
    }
    assert background_part["photoPrintLayoutMm"] == {
        "pageIndex": 0,
        "xMm": 0.0,
        "yMm": 0.0,
        "widthMm": PHOTO_2L_LANDSCAPE_WIDTH_MM,
        "heightMm": PHOTO_2L_LANDSCAPE_HEIGHT_MM,
        "pageWidthMm": PHOTO_2L_LANDSCAPE_WIDTH_MM,
        "pageHeightMm": PHOTO_2L_LANDSCAPE_HEIGHT_MM,
        "overflowsPage": False,
    }
    assert background_part["backgroundFill"]["mode"] == "cover-2l"
    assert background_part["backgroundFill"]["cropPx"] == {
        "left": 0,
        "top": 2,
        "right": 140,
        "bottom": 102,
        "widthPx": 140,
        "heightPx": 100,
    }
    assert background_part["geometry"]["strategy"] == "solid-rect"


def test_physical_output_exports_photo_pdf_from_artwork_and_assets(
    client: TestClient,
) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "outputFormat": "photoPdf",
        },
        files=_layer_asset_uploads(artwork),
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="omoi-photo-print-layout-mock-artwork-001'
    )
    assert response.content.startswith(b"%PDF")
    media_boxes = _pdf_media_boxes(response.content)
    assert media_boxes
    expected_width = PHOTO_2L_LANDSCAPE_WIDTH_MM * POINTS_PER_MM
    expected_height = PHOTO_2L_LANDSCAPE_HEIGHT_MM * POINTS_PER_MM
    for width, height in media_boxes:
        assert abs(width - expected_width) < 0.25
        assert abs(height - expected_height) < 0.25


def test_physical_output_config_stays_separate_from_artwork(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "physicalOutputConfig": json.dumps({"targetWidthMm": 120.0}),
        },
        files=_asset_uploads(artwork),
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archived_artwork = json.loads(archive.read("artwork.json"))
        config = json.loads(archive.read("physical-output-config.json"))

    assert config["targetWidthMm"] == 120.0
    assert "targetWidthMm" not in json.dumps(archived_artwork)
    assert "physicalOutput" in archived_artwork


def test_physical_output_can_generate_tree_supports(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "physicalOutputConfig": json.dumps(
                {
                    "supportMode": "tree",
                    "baseSlotLengthMm": 55.0,
                    "tabWidthMm": 54.0,
                }
            ),
        },
        files=_asset_uploads(artwork),
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        report = json.loads(archive.read("flat-photo-parts-report.json"))

    assert report["flatPhotoPartConfig"]["supportMode"] == "tree"
    lifted_supports = [
        support
        for part in report["parts"]
        if part["dimensionsMm"]["verticalSupportHeightMm"] > 0
        for support in part["verticalSupports"]
    ]
    assert lifted_supports
    assert any(support["branches"] for support in lifted_supports)


def test_physical_output_can_generate_full_row_rails(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "physicalOutputConfig": json.dumps({"supportMode": "rail"}),
        },
        files=_asset_uploads(artwork),
    )

    assert response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        report = json.loads(archive.read("flat-photo-parts-report.json"))

    assert report["flatPhotoPartConfig"]["supportMode"] == "rail"
    assert all(part["slotAssignment"]["selectedBy"] == "rowRail" for part in report["parts"])
    assert all(len(part["slotAssignment"]["slotLabels"]) == 3 for part in report["parts"])
    assert all(len(part["rails"]) == 1 for part in report["parts"])
    assert all(len(part["tabs"]) == 3 for part in report["parts"])
    lifted_supports = [
        support
        for part in report["parts"]
        if part["dimensionsMm"]["verticalSupportHeightMm"] > 0
        for support in part["verticalSupports"]
    ]
    assert lifted_supports
    assert all(not support["branches"] for support in lifted_supports)


def test_physical_output_requires_only_current_layer_assets(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={"artwork": json.dumps(artwork)},
        files=_layer_asset_uploads(artwork),
    )

    assert response.status_code == 200


def test_physical_output_ignores_unused_assets(client: TestClient) -> None:
    artwork = _mock_artwork()
    files = _layer_asset_uploads(artwork)
    files.append(("assets", ("source-unused.png", b"not an image", "image/png")))

    response = client.post(
        "/api/v1/physical-output/exports",
        data={"artwork": json.dumps(artwork)},
        files=files,
    )

    assert response.status_code == 200


def test_physical_output_uses_physical_asset_limits(
    tmp_path: Path,
    mock_artwork: dict[str, Any],
) -> None:
    settings = Settings(
        app_env="test",
        mock_ai=True,
        contracts_dir=CONTRACTS,
        cors_origins="http://localhost:5173",
        asset_dir=tmp_path / "assets",
        max_photo_bytes=1,
        max_physical_asset_bytes=15 * 1024 * 1024,
        _env_file=None,
    )

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        response = client.post(
            "/api/v1/physical-output/exports",
            data={"artwork": json.dumps(mock_artwork)},
            files=_layer_asset_uploads(mock_artwork),
        )

    assert response.status_code == 200


def test_physical_output_rejects_missing_asset(client: TestClient) -> None:
    artwork = _mock_artwork()
    files = [
        file
        for file in _asset_uploads(artwork)
        if not file[1][0].startswith("layer-1.")
    ]

    response = client.post(
        "/api/v1/physical-output/exports",
        data={"artwork": json.dumps(artwork)},
        files=files,
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "INVALID_INPUT"
    assert "Asset実体が無い" in json.dumps(body, ensure_ascii=False)


def test_physical_output_rejects_invalid_config(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "physicalOutputConfig": json.dumps({"targetWidthMm": -1}),
        },
        files=_asset_uploads(artwork),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_physical_output_rejects_invalid_config_type(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "physicalOutputConfig": json.dumps({"targetWidthMm": "wide"}),
        },
        files=_asset_uploads(artwork),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"


def test_physical_output_rejects_invalid_output_format(client: TestClient) -> None:
    artwork = _mock_artwork()

    response = client.post(
        "/api/v1/physical-output/exports",
        data={
            "artwork": json.dumps(artwork),
            "outputFormat": "svg",
        },
        files=_asset_uploads(artwork),
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_INPUT"
