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
- `outlineMarginMm`: 0.6
- `shapeMode`: contour
- `contourSimplifyMm`: 0.25
- `gridCellMm`: 2
- `tabWidthMm`: 8
- `tabHeightMm`: 7
- `tabOverlapMm`: 1
- `slotClearanceMm`: 0.4
- `baseLayerGapMm`: 7
- `baseHeightMm`: 8
- `material`: PLA

既定の形状生成は、2mmグリッドではなく輪郭ポリゴン押し出しにした。OpenCVが使えない、または輪郭の三角形化に失敗した場合だけグリッド方式へフォールバックする。意図せずフォールバックした場合は、レポートの `warnings` に出す。

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

### 実物寄り生成画像でのローカル評価

共通MockのAssetは見た目評価用ではないため、花、犬、人物の実物寄り透過PNGを別途生成し、`tmp/physical-eval-sample/` に評価用Artworkとして置いた。共通Fixtureではないので、`contracts/mock/` と `contracts/assets/` は変更していない。

生成方法はRepository内ではまだFIXされていない。今回の評価では、透明背景の単体切り抜き画像を作り、余白を整えたうえで、Artwork Dataの `assetId`、`x / y / scale / layerIndex` から既存の平面パーツPoCへ入力した。

2026-08-24に次を確認した。

```bash
python scripts/validate_contracts.py tmp/physical-eval-sample/artwork.json --assets tmp/physical-eval-sample/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out>
```

結果はどちらも成功。花、犬、人物の3つの実物寄りLayerから、差し込み足つき平面パーツSTL、スロット土台STL、1:1印刷用SVGを生成できた。警告は出ていない。

ただし、ここで確認できたのは「実物寄り透過PNGを取り込んで平面パーツ化できること」までである。実プリント時のスロットのきつさ、足の強度、反り、細部の欠け、飾り物としての見た目は未検証。

### 2mmグリッド外形の修正

実物寄りの花PNGをBambu Studioで見ると、花びら、葉、茎が「丸い塊」に近くなり、茎や下部の細い情報が消えて見えた。原因はSAMや写真生成ではなく、平面パーツ化の後段にあった。旧方式はalphaを2mmグリッドへ量子化し、さらに2mmの外形余白で太らせていたため、細い茎や葉のくびれがマス目へ吸収されていた。

2026-08-24に、平面パーツの既定生成を次のように直した。

- `shapeMode: contour` を既定にし、RGBA alphaから外部輪郭を取り出してポリゴン押し出しする
- `outlineMarginMm` を2.0mmから0.6mmへ下げ、細部を必要以上に太らせない
- `gridCellMm` は比較用・フォールバック用に残す
- 差し込み足はパーツ下部の実際の支持区間から置き、1.0mmだけ本体へ重ねる
- 既定の輪郭生成に失敗してグリッドへ戻った場合は、レポートに警告を出す

検証は次で行った。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py
python scripts/validate_contracts.py
python scripts/physical_output_mock_poc.py
python scripts/flat_photo_parts_poc.py
python scripts/validate_contracts.py tmp/physical-eval-sample/artwork.json --assets tmp/physical-eval-sample/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-contour>
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-grid-fallback> --shape-mode grid
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-grid-2mm-margin> --shape-mode grid --outline-margin-mm 2
```

結果は成功。評価用の花、犬、人物は既定で `geometry.strategy: contour` になった。花は旧条件では15 x 21の2mmグリッドに潰れていたが、修正後は1つの外部輪郭、88頂点、360三角形の平面STLになり、葉と茎のまとまりが残る。

比較画像は `tmp/physical-eval-sample/comparison/flower-contour-fix-20260824.png` に出した。これは共有Fixtureではなく、今回の原因確認用のローカル評価物である。

まだ未検証なのは、実プリント後の強度である。輪郭は残るようになったが、細い茎が実物として折れないか、スロットがきつすぎないか、反りが出ないかはBambu Studioのスライスと実印刷で確認する必要がある。
