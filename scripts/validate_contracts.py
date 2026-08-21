#!/usr/bin/env python3
"""Artwork が共通Contractを満たすか検証する。

JSON Schema だけでは表現できない規則もここで検証する:
  - layerIndex が 0..N-1 の重複なし連番であること
  - layer / candidate の sourcePhotoId が sourcePhotos[] に存在すること
  - layerId / assetId / candidateId が重複しないこと
  - 参照 Asset の実ファイルが存在し、実寸が widthPx / heightPx と一致すること
  - Layer Asset が実際に透過（alpha）を持つ RGBA PNG であること
  - rotation を持ち込んでいないこと（P0では持たせない【FIX】）
  - 差し替えUIを単独検証できるよう候補が最低1件あること（Mock要件）

usage:
  python scripts/validate_contracts.py                       # 共通Mockを検証
  python scripts/validate_contracts.py path/to/artwork.json  # 任意のArtworkを検証
  python scripts/validate_contracts.py a.json --assets dir/  # Asset置き場を指定

Real生成結果も同じSchemaを満たすことを接続確認条件とする。CIでもここを叩く。
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "contracts" / "artwork.schema.json"
DEFAULT_ARTWORK = ROOT / "contracts" / "mock" / "artwork.json"
DEFAULT_ASSETS = ROOT / "contracts" / "assets"

EXT = {"image/png": "png", "image/jpeg": "jpg", "image/webp": "webp"}


def check_schema(artwork: dict) -> list[str]:
    import jsonschema

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    return [
        "schema: " + "/".join(str(p) for p in e.absolute_path) + f": {e.message}"
        for e in sorted(validator.iter_errors(artwork), key=lambda e: list(e.absolute_path))
    ]


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
    refs: list[tuple[str, dict]] = []
    for photo in artwork.get("sourcePhotos", []):
        refs.append((photo["sourcePhotoId"], photo["asset"]))
    for layer in artwork.get("layers", []):
        refs.append((layer["layerId"], layer["asset"]))
        for cand in layer.get("replacementCandidates", []):
            refs.append((cand["candidateId"], cand["asset"]))

    for owner, asset in refs:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("artwork", nargs="?", default=str(DEFAULT_ARTWORK))
    ap.add_argument("--assets", default=str(DEFAULT_ASSETS))
    ap.add_argument("--skip-assets", action="store_true", help="Asset 実体の検証を省略する")
    args = ap.parse_args()

    artwork_path = pathlib.Path(args.artwork)
    artwork = json.loads(artwork_path.read_text(encoding="utf-8"))

    errors = check_schema(artwork)
    if not errors:  # Schema が通ってからでないと構造前提が崩れる
        errors += check_rules(artwork)
        if not args.skip_assets:
            errors += check_assets(artwork, pathlib.Path(args.assets))

    if errors:
        print(f"NG  {artwork_path}  ({len(errors)} 件)\n")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"OK  {artwork_path}\n"
        f"    schemaVersion={artwork['schemaVersion']} "
        f"photos={len(artwork['sourcePhotos'])} layers={len(artwork['layers'])} "
        f"aspectRatio={artwork['canvas']['aspectRatio']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
