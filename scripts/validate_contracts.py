#!/usr/bin/env python3
"""Artwork / 生成成功Response が共通Contractを満たすか検証する。

Artwork単体（`{"schemaVersion": ...}`）と、生成成功Response
（`{"artwork": ..., "assetManifest": ...}`）のどちらを渡してもよい。
形は中身から自動判定する。

JSON Schema だけでは表現できない規則もここで検証する:
  - layerIndex が 0..N-1 の重複なし連番であること
  - layer / candidate の sourcePhotoId が sourcePhotos[] に存在すること
  - layerId / assetId / candidateId が重複しないこと
  - 参照 Asset の実ファイルが存在し、実寸が widthPx / heightPx と一致すること
  - Layer Asset が実際に透過（alpha）を持つ RGBA PNG であること
  - rotation を持ち込んでいないこと（P0では持たせない【FIX】）
  - 差し替えUIを単独検証できるよう候補が最低1件あること（Mock要件）
  - 生成成功Responseでは、Artworkが参照する全AssetをAsset Manifestが解決できること
  - 共通Mock同士（artwork.json / asset-manifest.json / generate-success-response.json）が
    ずれていないこと

usage:
  python scripts/validate_contracts.py                       # 共通Mock一式を検証
  python scripts/validate_contracts.py path/to/artwork.json  # 任意のArtworkを検証
  python scripts/validate_contracts.py path/to/response.json # 生成成功Responseを検証
  python scripts/validate_contracts.py a.json --assets dir/  # Asset置き場を指定

Real生成結果も同じSchemaを満たすことを接続確認条件とする。CIでもここを叩く。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "contracts"
MOCK = CONTRACTS / "mock"
DEFAULT_ASSETS = CONTRACTS / "assets"

ARTWORK_SCHEMA = "artwork.schema.json"
MANIFEST_SCHEMA = "asset-manifest.schema.json"
RESPONSE_SCHEMA = "generate-success-response.schema.json"

# generate-success-response.schema.json は他2つを $ref する。
# Networkへ取りに行かせず、Local Fileだけで解決する。
SCHEMA_FILES = (ARTWORK_SCHEMA, MANIFEST_SCHEMA, RESPONSE_SCHEMA)

EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def _validator(schema_file: str):
    import jsonschema
    from referencing import Registry, Resource

    schemas = {
        name: json.loads((CONTRACTS / name).read_text(encoding="utf-8")) for name in SCHEMA_FILES
    }
    registry = Registry().with_resources(
        (schema["$id"], Resource.from_contents(schema)) for schema in schemas.values()
    )
    return jsonschema.Draft202012Validator(schemas[schema_file], registry=registry)


def check_schema(document: dict, schema_file: str) -> list[str]:
    validator = _validator(schema_file)
    return [
        "schema: " + "/".join(str(p) for p in e.absolute_path) + f": {e.message}"
        for e in sorted(validator.iter_errors(document), key=lambda e: list(e.absolute_path))
    ]


def check_manifest_covers_artwork(artwork: dict, manifest: dict) -> list[str]:
    """Asset Manifest が Artwork の参照する全Assetを解決できるかを見る。

    Artwork Data はURLを持たないので、Manifestが欠けるとFrontendは描画できない。
    必須Assetが欠けたArtworkを成功扱いしない【FIX】。
    """

    errs: list[str] = []
    by_id = {a["assetId"]: a for a in manifest.get("assets", [])}

    for owner, ref in _iter_asset_refs(artwork):
        entry = by_id.get(ref["assetId"])
        if entry is None:
            errs.append(f"{owner}: assetId '{ref['assetId']}' が Asset Manifest に無い")
            continue
        actual = (entry["mimeType"], entry["widthPx"], entry["heightPx"])
        expected = (ref["mimeType"], ref["widthPx"], ref["heightPx"])
        if actual != expected:
            errs.append(
                f"{owner}: {ref['assetId']} の Manifest Metadata {actual} が "
                f"Artwork側 {expected} と一致しない"
            )

    # 未参照のManifest Entryはここでは弾かない。
    # asset-manifest.schema.json も技術設計 §9.5 も「参照を解決できること」しか要求しておらず、
    # 余分なEntryを禁止していない。Real Responseを誤ってNGにしないため、
    # 過不足なしの確認は共通Mockに対してのみ行う（check_mock_consistency）。
    return errs


def _iter_asset_refs(artwork: dict):
    for photo in artwork.get("sourcePhotos", []):
        yield photo["sourcePhotoId"], photo["asset"]
    for layer in artwork.get("layers", []):
        yield layer["layerId"], layer["asset"]
        for cand in layer.get("replacementCandidates", []):
            yield cand["candidateId"], cand["asset"]


def check_rules(artwork: dict) -> list[str]:
    errs: list[str] = []
    layers = artwork.get("layers", [])
    photo_ids = {p["sourcePhotoId"] for p in artwork.get("sourcePhotos", [])}

    indexes = sorted(l["layerIndex"] for l in layers)
    if indexes != list(range(len(layers))):
        errs.append(
            f"layerIndex は 0..{len(layers) - 1} の重複なし連番である必要がある (actual: {indexes})"
        )

    seen_layer_ids: set[str] = set()
    seen_asset_ids: set[str] = set()
    seen_cand_ids: set[str] = set()

    for photo in artwork.get("sourcePhotos", []):
        aid = photo["asset"]["assetId"]
        if aid in seen_asset_ids:
            errs.append(f"assetId が重複している: {aid}")
        seen_asset_ids.add(aid)

    for layer in layers:
        lid = layer["layerId"]
        if "rotation" in layer:
            errs.append(f"{lid}: rotation は P0 の Artwork Data に持たせない【FIX】")
        if lid in seen_layer_ids:
            errs.append(f"layerId が重複している: {lid}")
        seen_layer_ids.add(lid)

        if layer["sourcePhotoId"] not in photo_ids:
            errs.append(f"{lid}: sourcePhotoId '{layer['sourcePhotoId']}' が sourcePhotos[] に無い")

        aid = layer["asset"]["assetId"]
        if aid in seen_asset_ids:
            errs.append(f"assetId が重複している: {aid}")
        seen_asset_ids.add(aid)

        for cand in layer.get("replacementCandidates", []):
            cid = cand["candidateId"]
            if cid in seen_cand_ids:
                errs.append(f"candidateId が重複している: {cid}")
            seen_cand_ids.add(cid)
            if cand["sourcePhotoId"] not in photo_ids:
                errs.append(f"{cid}: sourcePhotoId '{cand['sourcePhotoId']}' が sourcePhotos[] に無い")
            caid = cand["asset"]["assetId"]
            if caid in seen_asset_ids:
                errs.append(f"assetId が重複している: {caid}")
            seen_asset_ids.add(caid)

    if not any(l.get("replacementCandidates") for l in layers):
        errs.append(
            "replacementCandidates を持つ Layer が1件も無い（差し替えUIを単独検証できない）"
        )

    return errs


def check_assets(artwork: dict, assets_dir: pathlib.Path) -> list[str]:
    try:
        from PIL import Image
    except ImportError:
        return ["Pillow 未インストールのため Asset 実体検証をスキップ (pip install pillow)"]

    errs: list[str] = []
    for owner, asset in _iter_asset_refs(artwork):
        aid, mime = asset["assetId"], asset["mimeType"]
        path = assets_dir / f"{aid}.{EXT[mime]}"
        if not path.exists():
            errs.append(f"{owner}: Asset ファイルが無い: {path.name}")
            continue
        with Image.open(path) as img:
            if (img.width, img.height) != (asset["widthPx"], asset["heightPx"]):
                errs.append(
                    f"{owner}: {path.name} の実寸 {img.width}x{img.height} が "
                    f"Metadata {asset['widthPx']}x{asset['heightPx']} と一致しない"
                )
            if mime == "image/png":
                if img.mode != "RGBA":
                    errs.append(f"{owner}: {path.name} は RGBA ではない (mode={img.mode})")
                elif img.getchannel("A").getextrema()[0] == 255:
                    errs.append(f"{owner}: {path.name} に透過領域が無い（Layerは透過PNG）")
    return errs


def validate_artwork(
    artwork: dict, assets_dir: pathlib.Path, skip_assets: bool
) -> list[str]:
    errors = check_schema(artwork, ARTWORK_SCHEMA)
    if errors:  # Schema が通ってからでないと構造前提が崩れる
        return errors
    errors += check_rules(artwork)
    if not skip_assets:
        errors += check_assets(artwork, assets_dir)
    return errors


def validate_response(
    response: dict, assets_dir: pathlib.Path, skip_assets: bool
) -> list[str]:
    errors = check_schema(response, RESPONSE_SCHEMA)
    if errors:
        return errors
    artwork = response["artwork"]
    errors += check_rules(artwork)
    errors += check_manifest_covers_artwork(artwork, response["assetManifest"])
    if not skip_assets:
        errors += check_assets(artwork, assets_dir)
    return errors


def check_mock_consistency() -> list[str]:
    """共通Mock同士がずれていないことを見る。

    generate-success-response.json は artwork.json と asset-manifest.json を
    そのまま束ねたもの。JSONは $ref を持てないので、内容一致をここで担保する。
    """

    errs: list[str] = []
    artwork = json.loads((MOCK / "artwork.json").read_text(encoding="utf-8"))
    manifest = json.loads((MOCK / "asset-manifest.json").read_text(encoding="utf-8"))
    response = json.loads((MOCK / "generate-success-response.json").read_text(encoding="utf-8"))

    if response["artwork"] != artwork:
        errs.append("mock: generate-success-response.json の artwork が artwork.json と一致しない")
    if response["assetManifest"] != manifest:
        errs.append(
            "mock: generate-success-response.json の assetManifest が "
            "asset-manifest.json と一致しない"
        )

    # 共通Mockは全担当のFixtureなので、参照とManifestを過不足なく一致させておく。
    # （Real Responseには課さない。上の check_manifest_covers_artwork のコメント参照）
    referenced = {ref["assetId"] for _, ref in _iter_asset_refs(artwork)}
    listed = {a["assetId"] for a in manifest["assets"]}
    unused = sorted(listed - referenced)
    if unused:
        errs.append(f"mock: Artworkから参照されないManifest Entryがある: {', '.join(unused)}")

    return errs


def _describe(document: dict, is_response: bool) -> str:
    artwork = document["artwork"] if is_response else document
    summary = (
        f"schemaVersion={artwork['schemaVersion']} "
        f"photos={len(artwork['sourcePhotos'])} layers={len(artwork['layers'])} "
        f"aspectRatio={artwork['canvas']['aspectRatio']}"
    )
    if is_response:
        summary += f" manifestAssets={len(document['assetManifest']['assets'])}"
    return summary


def _report(label: str, errors: list[str], summary: str = "") -> int:
    if errors:
        print(f"NG  {label}  ({len(errors)} 件)\n")
        for e in errors:
            print(f"  - {e}")
        return 1
    print(f"OK  {label}" + (f"\n    {summary}" if summary else ""))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "document",
        nargs="?",
        help="Artwork または 生成成功Response のJSON。省略時は共通Mock一式を検証する。",
    )
    ap.add_argument("--assets", default=str(DEFAULT_ASSETS))
    ap.add_argument("--skip-assets", action="store_true", help="Asset 実体の検証を省略する")
    args = ap.parse_args()

    assets_dir = pathlib.Path(args.assets)

    if args.document is None:
        # 共通Mock一式。Artwork単体とResponseの両方を正本Schemaへ掛ける。
        status = 0
        for name, validate in (
            ("artwork.json", validate_artwork),
            ("generate-success-response.json", validate_response),
        ):
            path = MOCK / name
            document = json.loads(path.read_text(encoding="utf-8"))
            errors = validate(document, assets_dir, args.skip_assets)
            status |= _report(path, errors, _describe(document, validate is validate_response))
        status |= _report("mock consistency", check_mock_consistency())
        return status

    path = pathlib.Path(args.document)
    document = json.loads(path.read_text(encoding="utf-8"))
    # 生成成功Response か Artwork単体かを中身から判定する。
    is_response = "artwork" in document and "assetManifest" in document
    validate = validate_response if is_response else validate_artwork
    errors = validate(document, assets_dir, args.skip_assets)
    return _report(path, errors, "" if errors else _describe(document, is_response))


if __name__ == "__main__":
    sys.exit(main())
