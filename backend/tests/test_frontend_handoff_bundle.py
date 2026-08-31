"""Frontend handoff bundle writerの副作用をtmp_path内で検証する。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import jsonschema
import numpy as np
import pytest
from PIL import Image
from referencing import Registry, Resource

from ai.internal_models import SemanticPlan
from ai.quality import assess_mask
from ai.segmentation import SegmentationResult
from ai.types import AssetBlob
from app.models.artwork import Artwork

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACTS_DIR = REPO_ROOT / "contracts"


def _module():
    path = REPO_ROOT / "scripts" / "frontend_handoff_bundle.py"
    spec = importlib.util.spec_from_file_location("frontend_handoff_bundle", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _validator() -> jsonschema.Draft202012Validator:
    names = (
        "artwork.schema.json",
        "asset-manifest.schema.json",
        "generate-success-response.schema.json",
    )
    schemas = {
        name: json.loads((CONTRACTS_DIR / name).read_text(encoding="utf-8")) for name in names
    }
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return jsonschema.Draft202012Validator(
        schemas["generate-success-response.schema.json"], registry=registry
    )


def _mock_artwork_and_assets() -> tuple[Artwork, list[AssetBlob]]:
    artwork_payload = json.loads(
        (CONTRACTS_DIR / "mock" / "artwork.json").read_text(encoding="utf-8")
    )
    artwork_payload["canvas"]["aspectRatio"] = 178 / 127
    manifest = json.loads(
        (CONTRACTS_DIR / "mock" / "asset-manifest.json").read_text(encoding="utf-8")
    )
    extension = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}
    assets = [
        AssetBlob(
            asset_id=entry["assetId"],
            mime_type=entry["mimeType"],
            width_px=entry["widthPx"],
            height_px=entry["heightPx"],
            data=(
                CONTRACTS_DIR / "assets" / f"{entry['assetId']}.{extension[entry['mimeType']]}"
            ).read_bytes(),
        )
        for entry in manifest["assets"]
    ]
    return Artwork.model_validate(artwork_payload), assets


def _write_observer_evidence(module, output: Path) -> SemanticPlan:
    observer = module.PocDebugObserver(output / "debug")
    plan = SemanticPlan.model_validate(
        {
            "memory_summary": "海辺の思い出",
            "candidates": [
                {
                    "candidate_id": "candidate-1",
                    "label": "貝殻",
                    "source_photo_index": 0,
                    "importance": 1,
                    "selection_reason": "memoryTextと一致",
                    "components": [
                        {
                            "component_id": "component-1",
                            "label": "貝殻",
                            "box_2d": {
                                "y_min": 200,
                                "x_min": 100,
                                "y_max": 800,
                                "x_max": 900,
                            },
                        }
                    ],
                }
            ],
        }
    )
    image = Image.new("RGB", (100, 80), "white")
    observer.semantic_plan(plan, [image])

    mask = np.zeros((80, 100), dtype=bool)
    mask[20:60, 10:90] = True
    result = SegmentationResult(mask=mask, score=0.9, prompt_box_px=(10, 16, 90, 64))
    observer.segmentation_attempt(
        candidate=plan.candidates[0],
        component=plan.candidates[0].components[0],
        source_photo_index=0,
        image=image,
        result=result,
        quality=assess_mask(
            mask,
            result.prompt_box_px,
            result.score,
            diagnostics_max_side=100,
        ),
        attempt=0,
    )
    return plan


def test_writer_creates_complete_api_and_local_bundle(tmp_path: Path) -> None:
    module = _module()
    artwork, assets = _mock_artwork_and_assets()
    output = tmp_path / "frontend-debug-bundle"
    _write_observer_evidence(module, output)

    module.write_frontend_handoff_bundle(
        output_dir=output,
        artwork=artwork,
        assets=assets,
        memory_text="海辺で家族と過ごした大切な日。",
        metrics={"success": True, "photoCount": 5, "layerCount": 4},
        selected_photo_files=[f"photo-{index}.jpg" for index in range(1, 6)],
        preview_width_px=320,
    )

    required = {
        "generate-success-response.json",
        "generate-success-response.bundle.json",
        "artwork.json",
        "asset-manifest.json",
        "asset-manifest.bundle.json",
        "memory-text.txt",
        "metrics.json",
        "README.md",
        "assets",
        "debug",
    }
    assert required <= {item.name for item in output.iterdir()}
    assert (output / "debug" / "composition-preview.png").is_file()
    assert len(list((output / "debug" / "sources").glob("*.png"))) == 5
    assert len(list((output / "debug" / "layers").glob("*.png"))) >= 4

    api_response = json.loads(
        (output / "generate-success-response.json").read_text(encoding="utf-8")
    )
    bundle_response = json.loads(
        (output / "generate-success-response.bundle.json").read_text(encoding="utf-8")
    )
    _validator().validate(api_response)
    _validator().validate(bundle_response)
    assert api_response["artwork"] == bundle_response["artwork"]
    assert api_response["artwork"]["canvas"]["aspectRatio"] == 178 / 127
    assert len(api_response["artwork"]["sourcePhotos"]) == 5
    assert len(api_response["artwork"]["layers"]) == 4
    assert all(
        entry["url"].startswith("https://poc.omoi.invalid/")
        for entry in api_response["assetManifest"]["assets"]
    )
    assert all(
        entry["url"].startswith("assets/") and ".." not in entry["url"] and "\\" not in entry["url"]
        for entry in bundle_response["assetManifest"]["assets"]
    )
    for entry in bundle_response["assetManifest"]["assets"]:
        assert (output / entry["url"]).is_file()
        assert Path(entry["url"]).stem == entry["assetId"]

    readme = (output / "README.md").read_text(encoding="utf-8")
    for expected in (
        '"artwork"',
        '"assetManifest"',
        "generate-success-response.json",
        "artwork.json",
        "asset-manifest.json",
        "assets/",
        "memory-text.txt",
        "metrics.json",
        "debug/",
        "3D Preview / 2D Edit",
        "実API互換版とBundle向け版",
    ):
        assert expected in readme


def test_debug_observer_writes_real_bbox_and_mask_previews(tmp_path: Path) -> None:
    module = _module()
    _write_observer_evidence(module, tmp_path)

    assert (tmp_path / "debug" / "semantic-plan.json").is_file()
    assert (tmp_path / "debug" / "bbox" / "source-01-bbox.png").is_file()
    assert (tmp_path / "debug" / "bbox" / "index.json").is_file()
    assert (tmp_path / "debug" / "masks" / "mask-001.png").is_file()
    assert (tmp_path / "debug" / "masks" / "index.json").is_file()
    index_path = tmp_path / "debug" / "masks" / "index.json"
    attempts = json.loads(index_path.read_text(encoding="utf-8"))["attempts"]
    assert attempts[0]["diagnostics"]["componentCount"] == 1
    assert "memoryTextと一致" in (tmp_path / "debug" / "summary.md").read_text(encoding="utf-8")


def test_debug_observer_keeps_physical_ready_diagnostics_private(tmp_path: Path) -> None:
    module = _module()
    observer = module.PocDebugObserver(tmp_path / "debug")
    asset = AssetBlob("layer-private", "image/png", 10, 10, b"x")
    observer.composition_result(
        accepted=[
            module.AcceptedLayer(
                "scene-anchor", "庭園", 0, "source-layer-1", asset, 1, "scene_anchor"
            )
        ],
        diagnostics=module.PhysicalReadyDiagnostics(
            scene_anchor_candidate_id="scene-anchor",
            background_missing=False,
            initial_bottom_gaps=(("scene-anchor", 0.5),),
            recomposed=True,
            final_bottom_gaps=(("scene-anchor", 0.3),),
            y_corrections=(("scene-anchor", 0.2),),
        ),
    )

    payload = json.loads((tmp_path / "debug" / "physical-ready.json").read_text("utf-8"))
    assert payload["layers"] == [
        {
            "candidateId": "scene-anchor",
            "label": "庭園",
            "kind": "scene_anchor",
            "sourcePhotoIndex": 0,
        }
    ]
    assert payload["diagnostics"]["recomposed"] is True


def test_writer_rejects_bundle_without_bbox_and_mask_evidence(tmp_path: Path) -> None:
    module = _module()
    artwork, assets = _mock_artwork_and_assets()

    with pytest.raises(ValueError, match="Semantic/bbox/mask"):
        module.write_frontend_handoff_bundle(
            output_dir=tmp_path / "missing-debug",
            artwork=artwork,
            assets=assets,
            memory_text="海辺で家族と過ごした大切な日。",
            metrics={"success": True},
            selected_photo_files=[f"photo-{index}.jpg" for index in range(1, 6)],
        )


def test_writer_rejects_unreferenced_asset_blob(tmp_path: Path) -> None:
    module = _module()
    artwork, assets = _mock_artwork_and_assets()
    output = tmp_path / "extra-asset"
    _write_observer_evidence(module, output)
    source = assets[0]
    extra = AssetBlob(
        asset_id="unreferenced-private-photo",
        mime_type=source.mime_type,
        width_px=source.width_px,
        height_px=source.height_px,
        data=source.data,
    )

    with pytest.raises(ValueError, match="参照されないAssetBlob"):
        module.write_frontend_handoff_bundle(
            output_dir=output,
            artwork=artwork,
            assets=[*assets, extra],
            memory_text="海辺で家族と過ごした大切な日。",
            metrics={"success": True},
            selected_photo_files=[f"photo-{index}.jpg" for index in range(1, 6)],
        )
