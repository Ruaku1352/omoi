---
name: artwork-data
description: Artwork Data のSchema、正規化座標系、layerIndex、Asset参照の意味を扱う。Artwork JSON を読み書きするコード、型定義、Validation、Mock生成、Contract変更を検討するときに使う。座標変換やLayer順の実装で迷ったときにも参照する。
---

# artwork-data

正本は `/contracts/artwork.schema.json`。意味の要約は `/AGENTS.md` §3。
**本Skillに契約本文をコピーせず、必ず正本を読むこと。**

## 実装時に事故りやすい点

- `x` / `y` は**Layer中心**。左上基準の描画APIへ渡すときは幅・高さの半分を引く
- `scale` は**幅基準**。高さは `scale * asset.heightPx / asset.widthPx` で導出する。
  高さを独立した値として持たせない
- `layerIndex` は**配列位置と無関係**。`layers[i]` を奥行き順と解釈しない。
  描画前に `layerIndex` でソートする
- `layerIndex` の並べ替え後は `0..N-1` へ**再正規化**する
- `layers[]` の長さを4、`sourcePhotos[]` の長さを5と仮定しない

## Contract変更が必要になったら

1. 実装を進めず停止する
2. 変更内容・理由・影響を受ける担当を明示する
3. 公開チャンネルでの合意後に、**同一PRで** Schema / Mock / AGENTS.md / 関連Skills を同時更新する
4. 破壊的変更なら `schemaVersion` を上げる

## 検証

```bash
python scripts/validate_contracts.py                        # 共通Mock一式
python scripts/validate_contracts.py path/to/artwork.json   # 任意のArtwork
python scripts/validate_contracts.py path/to/response.json  # 生成成功Response
```

Artwork単体か `{artwork, assetManifest}` かは中身から自動判定する。

Real生成結果も同じSchemaを満たすことが接続確認の条件。
JSON Schemaで表現できない規則（layerIndexの連番性、Asset実体の一致、rotation不在）も
このスクリプトが検証する。
