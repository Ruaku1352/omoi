---
name: physical-output
description: 確定Artwork Data と Assets から物理作品を作るときに使う。実寸変換、PhysicalOutputConfig、STL等の生成、Portable Artwork Bundle、板状レイヤーと土台の3Dプリントを扱う場合に参照する。
---

# physical-output

前提は `/AGENTS.md` §8。

## Repository配置は未決定
STL等の生成を Browser / Backend / 独立Local Tool のどこで実行するかは**まだ決まっていない**。
Physical Output担当がPoCで扱いやすい技術・Runtimeを選び、その結果から配置を決める。

**それまで `physical-output/` を Root に作らない。**
PoCは共通Mockを使って、Repository外の作業ディレクトリで進めてよい。
配置をFIXする段階になったら共通技術設計へ反映して共有する。

2026-09-02時点では、Frontend TypeScriptのSTL生成PoCを撤去し、
FastAPI側に `POST /api/v1/physical-output/exports` をPoC候補として置く。
これは最終RuntimeをFIXするものではない。入力は `artwork` JSON + `assets[]`
を主経路にし、Portable Artwork Bundle ZIPを入力必須にはしない。
`physicalOutputConfig` は任意overrideで、未指定時はBackend側のPoC既定値
（rail / rail支え10mm / 2L Landscape / 4行 x 3穴）を使う。
ユーザー向け出力は `outputFormat=stlZip` で3Dプリンター用STL ZIP、
`outputFormat=photoPdf` で2L Landscape（178 x 127mm）写真紙100%印刷用PDF、
`outputFormat=photoJpegZip` でコンビニ2L写真プリント用JPEG ZIPへ分ける。SVGは主要Downloadにせず、
必要なら開発確認・手修正用の生成物として扱う。

## 入力境界【FIX】
確定Artwork Data + Assets。実行場所が変わってもこの境界は維持する。
Frontend内部State / Canvas Pixel / Three.js座標 / AI Prompt へ依存しない。

別Runtimeへ渡す場合は Portable Artwork Bundle（ZIPまたは展開済みDirectory、
最低限 `artwork.json` と参照される `assets/`）を使う。
同一Runtime内で生成する場合はBundleへのSerializeを必須にしない。

**Mock Bundle を先回りで作らない。** 別Runtime / Toolへ渡す方式を採る場合のみ
必要になる（技術設計 §16.1 / §26.1）。まずは `contracts/mock/` の
Artwork + Assets をそのまま読んでPoCを進める。

FastAPI候補Endpointでは、STL / PDF生成に使う現在の `layers[]` のAssetだけを必須にする。
`sourcePhotos[]` や `replacementCandidates[]` のAssetは、受け取ってもよいが使わなければ
必須にしない。
Layer PNGは生成入力写真より大きくなる場合があるため、`maxPhotoBytes` ではなく
Physical Output専用の `maxPhysicalAssetBytes` / `maxPhysicalTotalAssetBytes` で検証する。

## 実寸変換【FIX】
```
targetHeightMm = targetWidthMm / canvas.aspectRatio
xMm            = x * targetWidthMm          # x はLayer中心
yMm            = y * targetHeightMm         # 原点は左上、y は下方向が正
layerWidthMm   = scale * targetWidthMm
layerHeightMm  = layerWidthMm * asset.heightPx / asset.widthPx
```

## PhysicalOutputConfig は分離する【FIX】
`targetWidthMm` / `layerGapMm` / `plateThicknessMm` / 土台形状 / Printer / Material は
**Artwork Data ではなく PhysicalOutputConfig 側**に持つ。
**Artwork Data を物理都合のmm値で上書きしない。**

3D Preview上のLayer間隔は表示用の値であり、物理のmm値とは無関係。

## PoCで決めること【PoC後FIX】
板 / 土台形状、厚み、Layer Gap、STL生成Library、画像の表面表現、
印刷時間、材料・コスト、耐久性、自立方法。

Artwork Schema に不足Fieldがあると判断したら、実装前に公開チャンネルへ共有する。

## 守ること
Web Applicationから3D Printerを直接操作する構成にしない。
Artworkの座標・Layer順を独自定義へ置き換えない。
