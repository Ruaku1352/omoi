# 物理出力PoC

## 現在の判断

物理出力は、まだRootに `physical-output/` を作らない。STL生成をBrowser、Backend、独立Local Toolのどこで動かすかはPoC後に決めるため、最初の検証は `scripts/physical_output_mock_poc.py` に置く。

このPoCは、共通Mockの `contracts/mock/artwork.json` と `contracts/mock/asset-manifest.json` を入力にして、Artwork Dataを物理mmへ変換できるかを見る。Artwork Schemaには手を入れない。

## 入力

- `contracts/mock/artwork.json`
- `contracts/mock/asset-manifest.json`
- `contracts/assets/`

Artwork Dataで読む値は、`canvas.aspectRatio`、各Layerの `x`、`y`、`scale`、`layerIndex`、Assetの `widthPx`、`heightPx`。

### 共通Mock Assetの扱い

`contracts/assets/` の画像は、見た目の品質評価用ではなく、Artwork Dataの参照関係を確認するためのダミーAssetである。`label` に「花」「犬」「人物」と入っていても、その画像が実際に花・犬・人物として見えることまでは保証しない。

このPoCで確認するのは、「ここにこの写真・このLayer Assetがある」という構成情報を読み、`x / y / scale / layerIndex` とRGBA alphaから物理出力用の寸法・STL・印刷レイアウトへ変換できるかである。花らしさ、犬らしさ、人物らしさ、飾り物として欲しい見た目は、別途、物理出力評価用の実画像または実物に近い透過PNGで検証する必要がある。

## PhysicalOutputConfig

PoC値はArtwork Dataへ混ぜず、スクリプト内の `PhysicalOutputConfig` とCLI引数で扱う。

- `targetWidthMm`: 160
- `plateThicknessMm`: 2
- `layerGapMm`: 6
- `slotClearanceMm`: 0.6
- `material`: PLA

## 出力

```bash
python scripts/physical_output_mock_poc.py
```

生成物は `tmp/physical-output-poc/` に出る。

- 4枚のレイヤープレートSTL
- 4スロットの差し込み土台STL
- `physical-output-config.json`
- `physical-output-report.json`

レイヤープレートは、160 x 120mm相当の板に、各Layerの配置範囲を薄いガイド枠として載せる。画像そのものをSTLへ彫るのではなく、写真・透明Layerを後工程で載せる前提の最小検証である。

## 今日確認すること

- `x / y / scale / layerIndex` から実寸へ変換できるか
- 4層分のプレートと土台をSTLとして出せるか
- `PhysicalOutputConfig` をArtwork Dataと分離できているか
- Artwork Schemaへ追加Fieldが必要か

## 確認結果

2026-08-24に、共通Mockで次を確認した。

```bash
python scripts/validate_contracts.py
python scripts/physical_output_mock_poc.py
```

結果はどちらも成功。`physical_output_mock_poc.py` は `mock-artwork-001` を入力にして、160 x 120mmのキャンバス寸法へ変換し、4枚のレイヤープレートSTLと1つの差し込み土台STLを生成した。警告は出ていない。

## 現時点の結論

この矩形プレートPoCでは、Artwork Schemaの追加は不要。製造条件は `PhysicalOutputConfig` に置けば足りる。

ただし、実プリント後に「画像の貼り方」「差し込み足」「透明板の素材」「レイヤーごとの厚み」「実物の反り」まで扱う段階では、Asset側かPhysical Output Config側に追加情報が必要になる可能性がある。そこはPoC結果を見て共有する。

## 平ら印刷パーツPoC

凹凸やheightmapではなく、写真・透過Layerを平らな印刷用パーツとして扱うPoCを追加した。

```bash
python scripts/flat_photo_parts_poc.py
```

このPoCは、共通MockのRGBA PNG Layerを読み、alphaから外形だけを取り出す。奥行きや明るさを高さに変換しない。生成するSTLは一定厚みの平面パーツで、上面には別途印刷した画像・シール・転写などを載せる前提である。

### FlatPhotoPartConfig

- `targetWidthMm`: 160
- `partThicknessMm`: 1.6
- `outlineMarginMm`: 2
- `gridCellMm`: 2
- `tabWidthMm`: 8
- `tabHeightMm`: 7
- `slotClearanceMm`: 0.4
- `baseLayerGapMm`: 7
- `baseHeightMm`: 8
- `material`: PLA

### 出力

生成物は `tmp/flat-photo-parts-poc/` に出る。

- `label` が花、犬、人物になっているダミーLayerの差し込み足つき平面パーツSTL
- パーツの差し込み足に対応したスロット土台STL
- カット線、差し込み足、貼り込み範囲を入れた1:1印刷用 `flat-photo-print-layout.svg`
- `flat-photo-parts-report.json`

背景Layerは、通常の写真台紙側で扱う想定なのでデフォルトでは除外する。必要な場合は `--include-background` で含められる。特定Layerだけを試す場合は `--layer-id layer-3` のように指定する。

### 確認結果

2026-08-24に、共通Mockで次を確認した。

```bash
python scripts/validate_contracts.py
python scripts/physical_output_mock_poc.py
python scripts/flat_photo_parts_poc.py
```

結果は成功。`flat_photo_parts_poc.py` は、`label` が花、犬、人物になっている3つのダミーLayerから、平面パーツSTLと1:1印刷用SVGを生成した。警告は出ていない。

この方式でもArtwork Schemaの追加は不要。既存の `x / y / scale / layerIndex`、Asset寸法、RGBA alphaでPoCできる。製造条件は `FlatPhotoPartConfig` に分離しておけば足りる。

### 差し込み構造の追加

同日に、平らな印刷用パーツを「置ける物」に近づけるため、差し込み足と土台のPoCを追加した。

- 各平面パーツの下部に1個または2個の差し込み足を付ける
- `partThicknessMm + slotClearanceMm` で土台側のスロット幅を決める
- `layerIndex` の奥行き順に、土台上へスロット列を並べる
- SVGには画像を貼る範囲、外形カット線、差し込み足、差し込み位置の目印を入れる

確認では、3つの平面パーツSTLに加えて `flat-photo-parts-slot-base.stl` が生成された。STLは合計4ファイル。SVGは凹凸印刷用ではなく、画像やシールを平らに出して切るための1:1レイアウトとして扱う。

この追加でもArtwork Schemaの変更は不要。足の幅、足の高さ、土台の余白、スロットのクリアランス、奥行き間隔はすべて `FlatPhotoPartConfig` 側のPoC値であり、Artwork Dataへは混ぜていない。
