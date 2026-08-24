# 物理出力PoC

## 現在の判断

物理出力は、まだRootに `physical-output/` を作らない。STL生成をBrowser、Backend、独立Local Toolのどこで動かすかはPoC後に決めるため、最初の検証は `scripts/physical_output_mock_poc.py` に置く。

このPoCは、共通Mockの `contracts/mock/artwork.json` と `contracts/mock/asset-manifest.json` を入力にして、Artwork Dataを物理mmへ変換できるかを見る。Artwork Schemaには手を入れない。

## 入力

- `contracts/mock/artwork.json`
- `contracts/mock/asset-manifest.json`
- `contracts/assets/`

Artwork Dataで読む値は、`canvas.aspectRatio`、各Layerの `x`、`y`、`scale`、`layerIndex`、Assetの `widthPx`、`heightPx`。

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
