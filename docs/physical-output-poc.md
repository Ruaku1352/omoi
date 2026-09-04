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

- `targetWidthMm`: 178
- `partThicknessMm`: 1.6
- `outlineMarginMm`: 0.35
- `shapeMode`: grid
- `contourSimplifyMm`: 0.10
- `gridCellMm`: 0.6
- `supportBridgeWidthMm`: 1.8
- `verticalSupportWidthMm`: 4
- `verticalSupportMinHeightMm`: 1
- `supportRootPadWidthMm`: 12
- `supportRootPadHeightMm`: 5
- `supportRootOverlapMm`: 2
- `supportMode`: rail
- `treeBranchWidthMm`: 2.4
- `treeSupportEdgeMarginMm`: 4
- `railBodyHeightMm`: 4
- `railSupportWidthMm`: 10
- `railEdgeMarginMm`: 0
- `mountMode`: front-tab
- `tabWidthMm`: 12
- `tabHeightMm`: 5
- `tabOverlapMm`: 2
- `slotClearanceMm`: 0.35
- `baseMode`: square-grid
- `baseWidthMm`: 170
- `baseDepthMm`: 121
- `baseLayerCapacity`: 4
- `baseSlotsPerLayer`: 3
- `baseSlotLengthMm`: 12
- `baseFrontMarginYMm`: 11
- `baseBackMarginYMm`: 5
- `baseLayerGapMm`: 7
- `baseHeightMm`: 5
- `baseSlotLabelEngraveDepthMm`: 0.45
- `baseSlotLabelDigitHeightMm`: 6
- `baseSlotLabelOffsetYMm`: 1
- `baseSlotLabelGapMm`: 0.7
- `partSlotLabelEngraveDepthMm`: 0.35
- `partSlotLabelDigitHeightMm`: 4
- `partSlotLabelOffsetYMm`: 0.4
- `partSlotLabelGapMm`: 0.45
- `backgroundFillMode`: cover-2l
- `printLayoutPageWidthMm`: 178
- `printLayoutPageHeightMm`: 127
- `material`: PLA

既定の形状生成は、0.6mmグリッド方式にした。輪郭ポリゴン押し出しは比較用に残し、必要な場合だけ `--shape-mode contour` で指定する。現行の実プリント確認では、細かい外形よりも、未接続の島を検出・接続して1パーツとして成立させることを優先する。

### 出力

生成物は `tmp/flat-photo-parts-poc/` に出る。

- Layer PNGのalphaから作る平面パーツSTL
- 4行 x 3穴の番号付きスロット土台STL
- 開発確認用の `flat-photo-print-layout.svg`
- 2L Landscape（178 x 127mm）写真紙100%印刷用の `flat-photo-print-layout.pdf`
- `flat-photo-parts-report.json`

背景Layerも既定で出力する。今回のArtwork Dataでは `layerIndex: 0` が最背面であり、背景レイヤーとして真四角パネル化して写真紙を貼る想定がチーム内で確認済みのためである。背景を除外したい場合だけ `--exclude-background` を指定する。特定Layerだけを試す場合は `--layer-id layer-3` のように指定する。

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
- `outlineMarginMm` を2.0mmから0.35mmへ下げ、細部を必要以上に太らせない
- `contourSimplifyMm` を0.10mmにし、花びらや葉の外形を前回より細かく残す
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
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-contour-fine> --outline-margin-mm 0.35 --contour-simplify-mm 0.10
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-contour-extra-fine> --outline-margin-mm 0.25 --contour-simplify-mm 0.06
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-contour-ultra-fine> --outline-margin-mm 0.20 --contour-simplify-mm 0.04
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-grid-fallback> --shape-mode grid
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-grid-2mm-margin> --shape-mode grid --outline-margin-mm 2
```

結果は成功。評価用の花、犬、人物は既定で `geometry.strategy: contour` になった。花は旧条件では15 x 21の2mmグリッドに潰れていたが、修正後は1つの外部輪郭、181頂点、732三角形の平面STLになり、葉と茎のまとまりが残る。さらに細かい0.25mm余白 / 0.06mm単純化では259頂点、1044三角形まで増えた。追加確認した0.20mm余白 / 0.04mm単純化では352頂点、1416三角形まで増え、元画像の細部に近づく。ただし、0.4mmノズルでは細い茎や葉の切れ込みがスライス後に消えるか、実物で折れるリスクがあるため、既定は0.35mm余白 / 0.10mm単純化のままにする。

比較画像は `tmp/physical-eval-sample/comparison/flower-contour-fix-20260824.png` に出した。これは共有Fixtureではなく、今回の原因確認用のローカル評価物である。

細かさ比較画像は `tmp/physical-eval-sample/comparison/flower-detail-levels-20260824.png` と `tmp/physical-eval-sample/comparison/flower-detail-levels-ultra-20260824.png` に出した。既定は0.35mm余白 / 0.10mm単純化で、0.20mm余白 / 0.04mm単純化はBambu Studio確認用の比較出力である。

まだ未検証なのは、実プリント後の強度である。輪郭は残るようになったが、細い茎が実物として折れないか、スロットがきつすぎないか、反りが出ないかはBambu Studioのスライスと実印刷で確認する必要がある。

### 平面花パーツの実プリント一次確認

2026-08-24に、評価用の花PNGから作った平面STLを白PLAで実プリントした写真を確認した。Googleドキュメントへ貼る共有画像では、机背景をそのまま使わず、印刷物だけを背景除去して `tmp/physical-eval-sample/comparison/flower-png-to-print-20260824.png` にまとめた。

結果として、花の丸い外形、葉、茎、差し込み足は実物でも読める。一方で、花芯、花びらの色、写真の濃淡、細かい立体感は平面STLルートでは残らない。これは失敗というより、このPoCの役割が「写真の外形を白い差し込みパーツへ変換すること」に寄っているためである。

次に判断することは、写真やシールを後工程で重ねるのか、白PLAのシルエット置物として成立させるのかである。前者なら印刷面や貼り付け方法を別に検証する。後者なら、花芯や葉脈のような情報を別パーツ、浅い線、または色変更で追加する必要がある。

### 背面マウントと背面土台への変更

2026-08-24に、平面パーツの置き方を見直した。旧方式では本体の下に四角い差し込み足を足し、土台も前後8mmずつの均等余白にしていた。そのため、犬や花を正面から見たときに固定の都合が前側へ出やすかった。

既定を `mountMode: rear` に変更した。正面シルエットの高さは画像由来の外形のままにし、支えは本体下部の1mm重なり位置から背面方向へ伸ばす。さらに `flat-photo-parts-slot-base.stl` は、前余白を3mm、後ろ余白を24mmにして、正面から見たときに土台が後ろへ伸びる設計へ寄せた。比較用として、旧方式は `--mount-mode front-tab` と前後8mm余白指定で再現できる。

- `frontExtensionMm` は背面マウント時に0になる
- `tabHeightMm` は正面下方向の足ではなく、背面方向の支え深さとして扱う
- 土台は正面側へ出すのではなく、組み立て時に背面方向へ伸びる前提にした
- スロット順は `layerIndex` の大きいものを手前、小さいものを奥として並べる
- SVGでは、正面に出る赤い足ではなく、背面マウント位置を青い目印として表示する

検証は次で行った。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py
python scripts/validate_contracts.py
python scripts/physical_output_mock_poc.py
python scripts/flat_photo_parts_poc.py
python scripts/validate_contracts.py tmp/physical-eval-sample/artwork.json --assets tmp/physical-eval-sample/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-rear-base>
python scripts/flat_photo_parts_poc.py --mount-mode front-tab --base-front-margin-y-mm 8 --base-back-margin-y-mm 8 --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-front-base-compare>
```

結果は成功。背面土台版のSTLは `tmp/physical-eval-sample/out-rear-base/` に出した。旧方式との説明画像は `tmp/physical-eval-sample/comparison/rear-base-direction-20260824.png` に作成した。土台寸法は旧方式が幅184mm / 奥行き36mm / 前後余白8mmずつ、新方式が幅184mm / 奥行き47mm / 前余白3mm / 後ろ余白24mmである。

まだ未検証なのは、背面方向に伸ばした支えと後ろへ長い土台が、実物の重心に対して十分に安定するかである。Bambu Studioで配置を確認し、必要なら支えを別パーツ化するか、土台側に背面リブを追加する。

### 90mm四方・4層3スロット土台への変更

2026-08-24に、土台をさらに見直した。前回の背面土台は「前より後ろへ伸びる」意図は合っていたが、幅184mmの横長バーで、スロット数も各レイヤーの足の位置に依存していた。Bambu A1 miniで扱うことや、見た目の分かりやすさを考えると、まずは土台を規格化した方がよい。

既定を `baseMode: square-grid` に変更した。`flat-photo-parts-slot-base.stl` は90mm四方、厚み8mmの正方形ベースになり、正面から奥へ4層分のスロット列を持つ。各層には3つの差し込み口を固定で置く。評価用Artworkは3レイヤーなので、4層目は空きとして残る。

- 土台寸法: 90 x 90 x 8mm
- 層数: 4
- 各層の差し込み口: 3
- スロット幅: `partThicknessMm + slotClearanceMm` = 2.0mm
- 各差し込み口の長さ: 16mm
- 各パーツの差し込み足幅: 16mm
- 正面から奥への割り当て: 人物、犬、花、空き

検証は次で行った。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py
python scripts/validate_contracts.py
python scripts/physical_output_mock_poc.py
python scripts/flat_photo_parts_poc.py
python scripts/validate_contracts.py tmp/physical-eval-sample/artwork.json --assets tmp/physical-eval-sample/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/physical-eval-sample/artwork.json> --assets <absolute path to tmp/physical-eval-sample/assets> --out <absolute path to tmp/physical-eval-sample/out-square-base>
```

結果は成功。新しい土台STLは `tmp/physical-eval-sample/out-square-base/flat-photo-parts-slot-base.stl` に出した。説明画像は `tmp/physical-eval-sample/comparison/square-grid-base-20260824.png` に作成した。

土台を先に作ったため、2026-08-24にパーツ側の差し込み足を8mmから16mmへ広げた。土台側の1穴は実開口が約16.8mmで、16mm足に対して左右合計0.8mmの余裕が残る。

再生成結果は成功。評価用の花、犬、人物はいずれも差し込み足が16mmになった。土台側の1穴は16.8mmなので、各パーツに0.8mmの余裕が残る。説明画像は `tmp/physical-eval-sample/comparison/part-tab-width-20260824.png` に作成した。

まだ未検証なのは、16mm足が花の細い茎や犬・人物の下部で見た目の邪魔にならないか、実物で穴にきつすぎず緩すぎず入るかである。次の実プリントでは、土台の安定性、穴のきつさ、4層目の空きが見た目として邪魔でないかを確認する。

### 実プリント写真を使った資料化

2026-08-24に、ユーザー提供の実プリント写真3枚を確認した。写真は、凹凸レリーフ本体、4層 x 3穴土台、レリーフ拡大確認の3種類である。共有用には机や手元が目立たないようにトリミングし、`tmp/physical-eval-sample/comparison/printed-relief-and-base-20260824.png` に1枚の資料画像としてまとめた。

見えたことは二つある。凹凸レリーフは、人物と犬らしい大きな構図は残るが、白PLAでは細い線や背景由来の形がノイズに見えやすい。土台は4層 x 3穴の方向で実物確認できており、次は16mm差し込み足が穴に入るか、きつすぎないか、置いたときに安定するかを確認する。

### 元写真と平面STLの横並び確認

2026-08-26に、評価用の人物、花、犬について、元写真、RGBA切り抜き、STL正面、STL斜めを横並びにした比較画像を作成した。対象はすべて `tmp/physical-eval-sample/assets/` の評価用画像で、生成済みの平面パーツSTLは `tmp/physical-eval-sample/out-square-base/` を使った。

生成した比較画像は次の通り。

- `tmp/physical-eval-sample/comparison/person-source-to-stl-20260826.png`
- `tmp/physical-eval-sample/comparison/flower-source-to-stl-20260826.png`
- `tmp/physical-eval-sample/comparison/dog-uniform-source-to-stl-20260826.png`
- `tmp/physical-eval-sample/comparison/nonhuman-source-to-stl-20260826.png`

人物は、人型の外形は残るが、顔、服、髪色、表情が落ちるため、元写真の本人らしさはほぼ残らない。平面パーツ化の技術検証としては通るが、思い出の置物として成立させるには、表面写真、シール、線画、または色分けを別工程で足す必要がある。

人以外の比較では、花は外形の記号が強く、白い平面STLでも比較的読める。犬は耳、体、しっぽの外形は残るが、かわいさは目、口、毛並み、色に依存するため、花よりも表面表現の必要度が高い。

この検証で確認したのは、写真の意味やかわいさを再現できることではなく、切り抜き済みRGBAから平らな差し込みパーツへ変換できることまでである。次は、土台に差した状態で、正面から見たときに足が邪魔にならないか、花・犬・人物を同時に並べたときに作品として読めるかを確認する。

### 特徴が弱い思い出写真の生成テスト

2026-08-26に、花・犬・人物のように外形が強い対象だけでなく、思い出としては強いが単体シルエットが弱い写真を生成して試した。対象は、誕生日テーブル、入学・卒業の場面、旅行先の風景の3種類。生成画像と評価用Artworkは `tmp/weak-memory-eval-sample/` に置いた。

今回の検証は、Segmentation精度そのものの検証ではない。VLMが選ぶべきモチーフを仮決めし、その部品をRGBAレイヤーにしたとき、既存の平面STL工程へ流せるかを見る検証である。

- 誕生日: 主役の子ども、ケーキとろうそく、プレゼント
- 入学・卒業: 式看板、子どもとランドセル、式典の花
- 旅行: 山の稜線、橋、家族と荷物

検証は次で行った。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py scripts/validate_contracts.py
python scripts/validate_contracts.py tmp/weak-memory-eval-sample/birthday/artwork.json --assets tmp/weak-memory-eval-sample/birthday/assets
python scripts/validate_contracts.py tmp/weak-memory-eval-sample/school/artwork.json --assets tmp/weak-memory-eval-sample/school/assets
python scripts/validate_contracts.py tmp/weak-memory-eval-sample/travel/artwork.json --assets tmp/weak-memory-eval-sample/travel/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/weak-memory-eval-sample/birthday/artwork.json> --assets <absolute path to tmp/weak-memory-eval-sample/birthday/assets> --out <absolute path to tmp/weak-memory-eval-sample/birthday/out-symbol-parts> --layer-id birthday-layer-child --layer-id birthday-layer-cake --layer-id birthday-layer-gift
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/weak-memory-eval-sample/school/artwork.json> --assets <absolute path to tmp/weak-memory-eval-sample/school/assets> --out <absolute path to tmp/weak-memory-eval-sample/school/out-symbol-parts> --layer-id school-layer-sign --layer-id school-layer-child --layer-id school-layer-flowers
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/weak-memory-eval-sample/travel/artwork.json> --assets <absolute path to tmp/weak-memory-eval-sample/travel/assets> --out <absolute path to tmp/weak-memory-eval-sample/travel/out-symbol-parts> --layer-id travel-layer-mountains --layer-id travel-layer-bridge --layer-id travel-layer-family
```

結果は成功。3ケースともSchema検証と平面STL生成が通り、各ケース3パーツと90mm四方の4層3スロット土台を生成できた。

生成した比較画像は次の通り。

- `tmp/weak-memory-eval-sample/comparison/weak-memory-summary-20260826.png`
- `tmp/weak-memory-eval-sample/comparison/weak-memory-birthday-source-to-stl-20260826.png`
- `tmp/weak-memory-eval-sample/comparison/weak-memory-school-source-to-stl-20260826.png`
- `tmp/weak-memory-eval-sample/comparison/weak-memory-travel-source-to-stl-20260826.png`

見えたことは明確である。特徴が弱い思い出写真では、人だけ、犬だけ、花だけを切る発想では足りない。誕生日はケーキとろうそく、入学はランドセルと看板、旅行は橋や山のように、写真の意味を読ませる記号へ翻訳する必要がある。

旅行写真は特に厳しい。人物が小さいため、家族だけを平面STL化するとただの小さい人型になりやすい。橋と山を同時に残すことで、ようやく旅行先の風景として読める。つまり、次の実装では「どこを切るか」だけでなく、「何を残せば思い出として伝わるか」をVLMに選ばせる必要がある。

残課題は、仮決めしたマスクをVLM + Segmentationで自動化できるか、複数モチーフを1レイヤーにしたときに分離パーツが出ないか、表面写真や線画なしで思い出として読めるかである。

### 1写真1パーツ方針での再テスト

2026-08-26に、特徴が弱い思い出写真の扱いを見直した。前回は1枚の写真から、誕生日なら主役、ケーキ、プレゼントのように複数パーツへ分解していた。しかし、実際の利用イメージでは、1枚の写真から出す物理パーツは基本1つでよい。入学式なら子どもと看板をまとめる。旅行なら3人で立っているまとまりを1つにする。写真の中の主役と意味を支える小道具を、1つの差し込みパーツへ翻訳する方針へ寄せた。

今回もSegmentation精度そのものの検証ではない。VLMが選ぶべき「1つの記念パーツ案」を人手で仮決めし、そのRGBAレイヤーが既存の平面STL工程へ流せるかを見た。

再テストした3件は次の通り。

- 誕生日テーブル: 誕生日の主役とケーキを1パーツにする
- 入学・卒業: 子どもと式看板を1パーツにする
- 旅行の集合写真: 旅行先に立つ家族のまとまりを1パーツにする

追加で、思い出写真としてありそうな10件を生成して試した。

- 七五三: 家族と鳥居
- 結婚式: 新郎新婦とアーチ
- 赤ちゃん: ベビーベッドと月飾り
- 運動会: ゴールする子ども
- ピアノ発表会: 子どもとピアノ
- キャンプ: 親子とテント
- 海遊び: 家族と砂の城
- 引っ越し: 家族と玄関と箱
- ペットお迎え: 家族と犬とキャリー
- 祖父母祝い: 祖父母と家族の祝い

検証は次で行った。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py scripts/validate_contracts.py
python scripts/validate_contracts.py tmp/weak-memory-single-part-eval-sample/<case>/artwork.json --assets tmp/weak-memory-single-part-eval-sample/<case>/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/weak-memory-single-part-eval-sample/<case>/artwork.json> --assets <absolute path to tmp/weak-memory-single-part-eval-sample/<case>/assets> --out <absolute path to tmp/weak-memory-single-part-eval-sample/<case>/out-single-part> --layer-id <case>-single-part
```

13件すべてでContract検証、平面STL生成、STL存在確認が通った。警告は出ていない。生成した比較画像は次の通り。

- `tmp/weak-memory-single-part-eval-sample/comparison/single-part-redo-3-cases-20260826.png`
- `tmp/weak-memory-single-part-eval-sample/comparison/single-part-extra-10-cases-20260826.png`
- `tmp/weak-memory-single-part-eval-sample/comparison/single-part-all-13-summary-20260826.png`

見えたことは、1写真1パーツの方がプロダクトの説明に合うということだ。複数パーツへ分解すると、写真の記念性よりも部品化の都合が前に出る。1パーツにまとめると、「この写真から作った置物」という理解はしやすい。

ただし、白い平面STLだけで読めるケースと、読みにくいケースの差は大きい。鳥居、アーチ、ピアノ、テント、玄関のように形が強い小道具がある写真は残りやすい。集合写真や祖父母祝いのように、人のまとまりが主役の写真は塊になりやすく、本人らしさはほぼ残らない。

次に作るべき工程は、単純な切り抜き精度の改善ではない。VLMで「何を1つにまとめれば思い出として読めるか」を選び、平面STLでは外形だけを作る。本人らしさ、かわいさ、学校名、表情、衣装、写真の空気は、表面写真、シール、線画、色分けのどれかで補う必要がある。

### 6〜10の記念アイコン方式テスト

2026-08-26に、追加10ケースのうち6〜10を別方式で試した。前回の1写真1パーツでは、キャンプ、海遊び、引っ越し、ペットお迎え、祖父母祝いを、人物や家族を含む1つのシルエットにまとめていた。しかし、集合写真や家族写真は白い平面STLへ落とすと塊になりやすく、本人らしさも残りにくい。

今回の方針は、写真を主役として残し、STLは「記念アイコン」に寄せることにした。人物全員を切るのではなく、外形だけで読める小道具や場面記号を1つのパーツにする。

- キャンプ: 親子とテント → テントとランタン
- 海遊び: 家族と砂の城 → 砂の城と波
- 引っ越し: 家族と玄関と箱 → 玄関と段ボール
- ペットお迎え: 家族と犬とキャリー → 犬とキャリー
- 祖父母祝い: 祖父母と家族の祝い → ケーキと花束

検証は次で行った。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py scripts/validate_contracts.py
python scripts/validate_contracts.py tmp/weak-memory-icon-eval-sample/<case>/artwork.json --assets tmp/weak-memory-icon-eval-sample/<case>/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/weak-memory-icon-eval-sample/<case>/artwork.json> --assets <absolute path to tmp/weak-memory-icon-eval-sample/<case>/assets> --out <absolute path to tmp/weak-memory-icon-eval-sample/<case>/out-memory-icon> --layer-id <case>-memory-icon
```

5件すべてでContract検証と平面STL生成が通った。警告は出ていない。キャンプも含め、全ケースが `contourCount: 1` になっており、少なくとも外部輪郭としては1つの印刷物にまとまった。

生成した比較画像は `tmp/weak-memory-icon-eval-sample/comparison/memory-icon-method-6-10-clean-20260826.png` に置いた。旧案の人物込みシルエット、新案の記念アイコン、新STLを横並びで比較している。

結果として、キャンプ、海遊び、引っ越し、ペットお迎えは改善した。人を丸ごと残すより、テント、砂の城、玄関、犬キャリーの方が白い板でも場面として読みやすい。

祖父母祝いだけは扱いを変える必要がある。ケーキと花束にすれば「祝い」の記号にはなるが、祖父母本人の記憶は残らない。このケースは、写真カードを主役にし、STLは周辺の祝い記号として添える方がよい。人物の顔や関係性をSTLへ無理に入れないことを、次の設計ルールにする。

### 8〜10の記念アイコン再修正

2026-08-26に、前回の記念アイコン方式のうち、読みにくかった8〜10だけを再修正した。キャンプと海遊びは、テント、ランタン、砂の城、波の外形が残っており、今回は据え置きにした。

問題は、引っ越し、ペットお迎え、祖父母祝いだった。玄関は棒のように見え、犬とキャリーはペット記号として弱く、ケーキ横の花束は謎の突起に見えた。そこで、白い平面STLでも外形だけでカテゴリが読める案へ寄せた。

- 引っ越し: 玄関と段ボール → 引っ越しトラックと箱
- ペットお迎え: 犬とキャリー → 大きい肉球
- 祖父母祝い: ケーキと花束 → 祝いケーキ

検証は次で行った。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py scripts/validate_contracts.py
python scripts/validate_contracts.py tmp/weak-memory-icon-v2-eval-sample/<case>/artwork.json --assets tmp/weak-memory-icon-v2-eval-sample/<case>/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to tmp/weak-memory-icon-v2-eval-sample/<case>/artwork.json> --assets <absolute path to tmp/weak-memory-icon-v2-eval-sample/<case>/assets> --out <absolute path to tmp/weak-memory-icon-v2-eval-sample/<case>/out-memory-icon-v2> --layer-id <case>-memory-icon-v2
```

3件すべてでContract検証と平面STL生成が通った。警告は出ていない。全ケースが `contourCount: 1` で、引っ越しは300三角形、ペットお迎えは612三角形、祖父母祝いは576三角形になった。

生成した比較画像は `tmp/weak-memory-icon-v2-eval-sample/comparison/memory-icon-method-8-10-v2-20260826.png` に置いた。前回案、改善案、改善STL正面を横並びで確認できる。

判断として、引っ越しはかなり改善した。玄関よりトラックの方が、白い板でも意味が立つ。ペットお迎えは犬本人をSTLで残すより、大きい肉球にした方が「ペット」の記号として安定する。祖父母祝いは祝いケーキにすると読みやすくなるが、祖父母本人の記憶は残らない。ここは引き続き、写真カードを主役にし、STLは補助記号として扱う。

### Frontend実生成データの印刷変換確認

2026-08-29に、Driveで共有されたFrontend 3Dプレビュー用の実生成データを取得し、Physical Output側の平面STL生成PoCへ流せるか確認した。共有データそのものには個人写真が含まれるため、RepositoryへはZIPや展開AssetをCommitしない。

確認したことは次の通り。

- ZIPの中には `artwork.json`、`asset-manifest.json`、`generate-success-response.json`、`assets/`、`debug/` が含まれていた
- `generate-success-response.bundle.json` と相対Asset URLを使えば、ローカルブラウザ検証用のデータとして扱える構成になっていた
- Layer AssetはRGBA PNGだったため、平面STL生成PoCの入力として利用できた
- 既存の `scripts/flat_photo_parts_poc.py` で、4層分の平面パーツSTLと4層3スロット土台STLを生成できた
- 生成結果確認用のPNGを作成し、変換前の構成画像、生成STL一覧、土台情報を1枚で確認できるようにした

検証は次で行った。

```bash
python scripts/validate_contracts.py tmp/drive-downloads/extracted/<bundle>/generate-success-response.json --assets tmp/drive-downloads/extracted/<bundle>/assets
python scripts/flat_photo_parts_poc.py --artwork <absolute path to artwork.json> --assets <absolute path to assets> --out <absolute path to print-check-default>
python scripts/flat_photo_parts_poc.py --artwork <absolute path to artwork.json> --assets <absolute path to assets> --out <absolute path to print-check-all-layers> --include-background
```

結果として、印刷データ化はローカルPoCでは可能だった。ただし、StrictなContract検証では次の不一致が出た。

- `replacementCandidates` が空で、Frontendの差し替え動作確認には足りない
- 一部Source Photo PNGがRGBAではなくRGBだった
- Source Photo側のRGBA不一致は、今回の平面STL生成には直接影響しない

重要な発見として、既存PoCの初期挙動は `layerIndex: 0` を背景扱いで除外する。しかし共通仕様では `layerIndex: 0` は「最背面」であって、背景とは限らない。今回の実生成データでも最背面Layerが実パーツだったため、実データを印刷に回す場合は `--include-background` が必要だった。

次に直すべきことは、`layerIndex: 0` を自動で除外する判断をやめ、背景除外を明示指定に寄せること。加えて、ブラウザから直接印刷データへ変換したい場合は、Frontendに「Bundle読込」「Asset解決」「STL生成」「ZIPダウンロード」の小さい検証画面を追加する必要がある。現時点のブラウザ側は3Dプレビュー確認までで、STLやG-codeを書き出す機能はまだない。

### ブラウザからSTL ZIPを書き出すPoC

2026-08-29に、Frontend上で表示しているArtwork Data + Asset Manifestから、平面パーツSTLと土台STLをZIPで書き出すPoCを追加した。3D Printerへ直接送信せず、ブラウザはSTL ZIPまでを担当し、3MF / G-code化はBambu Studioへ渡す前提にしている。

追加した画面では、共通Mockをそのまま使うほか、Driveなどで受け取った `generate-success-response.json` または `artwork.json` / `asset-manifest.json` と、対応するassets画像をまとめて選択できる。Asset ManifestのURLをBlob URLへ置き換えるだけなので、Artwork Data本体へURLやmm値は追加しない。

印刷データ生成では、各Layer PNGのalphaから0.6mmセルの平面STLを作る。離れた塊が複数ある場合は、一番大きい塊を本体とみなし、その他の塊を低い支えで本体側へ接続する。これはスライサーのサポート材ではなく、作品側に残る構造として扱う。下部には差し込み足を付け、90mm四方、4層、各層3穴の土台STLも同じZIPへ入れる。

検証は次で行った。

```bash
cd frontend
npm ci
node node_modules/typescript/bin/tsc -b
node node_modules/vitest/vitest.mjs run
node node_modules/vite/bin/vite.js build
node node_modules/oxlint/dist/cli.js
```

さらにPlaywrightで `http://127.0.0.1:5173/` を開き、`STL ZIPを生成` を押して `flat-print-mock-artwork-001.zip` がダウンロードされることを確認した。Mockでは4パーツ、90 x 90 x 8mm土台、自動支え0本だった。

Driveで共有された実生成Bundleも、展開済みフォルダをブラウザで選択し、`flat-print-artwork-9b00c36b3b8349448a7e7d913a8e3a54.zip` としてダウンロードできた。この実生成データでは4パーツ、90 x 90 x 8mm土台、自動支え5本になった。自動支えは最背面Layerの離れた5塊に対して追加された。

自動支えは別途、離れた2塊のテストケースで1本生成され、1つの連結形状になることを確認している。

残課題は、STLサイズが大きくなりやすいことと、支えが意味的にきれいかどうかをまだ人間が見て判断する必要があること。次の改善では、セル押し出しではなく輪郭ポリゴン方式へ寄せ、支えの候補を画面で見てON/OFFできるようにする。

### 屋敷レイヤーの再現確認と小型土台

2026-08-29に、Frontend実生成Bundleと同じ5枚・同じ思い出テキストでReal AI再生成を試した。実行環境ではGeminiのSemantic Planningが2回ともProvider側のServerErrorで失敗し、候補生成まで進まなかった。そのため、フル再生成で屋敷が再び選ばれるかは未確認である。

一方で、過去Bundleに残っている屋敷候補のbboxを使い、EfficientSAMだけを再実行した。対象は `c5_samurai_garden_house`、bboxは過去の `debug/masks/index.json` に残っていた `promptBoxPx: [1746, 314, 4032, 1703]`。結果は、旧layer PNGと同じサイズの `house-replay-layer.png` になり、pixel alpha上の分離数も同じ8個だった。屋敷の崩れはSTL化で急に発生したものではなく、bboxとmaskの段階でほぼ再現する。

このbboxは右端が画像端まで届き、品質情報でも `borderTouch: true`、`bboxCoverage: 0.2736` だった。現在の品質判定ではacceptedになっているが、物理出力へ回すには危険なmaskである。次は、AI側で「画像端に触れる」「分離が多い」「bbox内の塊が小さい」maskを再試行または不採用にする必要がある。

同日に、ブラウザSTL ZIPの土台も小型化した。旧版は90 x 90 x 8mmで大きすぎたため、既定を68 x 54 x 5mmへ変更し、差し込みタブも16mmから12mmへ下げた。ブラウザで実生成Bundleを読み直し、4パーツ、68 x 54 x 5mm土台、自動支え5本のSTL ZIPを書き出せることを確認した。屋敷レイヤーには、切り抜き済みレイヤーが分離している旨の警告も表示する。

検証生成物は次に置いた。

- `tmp/real-ai-rerun-20260829/sam-replay-house/house-sam-replay-comparison.png`
- `tmp/real-ai-rerun-20260829/sam-replay-house/house-replay-report.json`
- `tmp/browser-stl-export-small-base/flat-print-artwork-9b00c36b3b8349448a7e7d913a8e3a54.zip`

### 2L判寄り土台への再調整

2026-08-31に、土台サイズを再調整した。68 x 54mmの小型土台は印刷確認には扱いやすかったが、作品としては小さすぎる。2L判は約178 x 127mmだが、Bambu Lab A1 miniの造形範囲に対して横178mmは端まで使いすぎるため、既定は2L比率に近い170 x 121mmへ寄せた。

ブラウザSTL ZIP側の既定は次に変更した。

- 土台寸法: 170 x 121 x 5mm
- 層数: 4
- 各層の差し込み口: 3
- 土台グリッド: 1mm
- 差し込み足: 12mm幅、5mm奥行き
- スロット幅: `partThicknessMm + slotClearanceMm` = 1.95mm
- 前余白: 8mm
- 後ろ余白: 20mm

ローカルPoCスクリプトも、正方形土台専用の `baseSideMm` ではなく、`baseWidthMm` / `baseDepthMm` を持つ形に変更した。後方互換用に `--base-side-mm` は残し、指定した場合だけ幅と奥行きの両方を同じ値へ上書きする。

実生成Bundleから、4層すべてを含む印刷用データを作成した。ブラウザ側と同じ考え方に合わせるため、ローカル生成では `--shape-mode grid --grid-cell-mm 0.6` を明示した。出力は4つの平面パーツSTL、2L判寄り土台STL、1:1印刷用SVG、レポート、ZIPである。

```bash
python -m py_compile scripts/flat_photo_parts_poc.py
python scripts/flat_photo_parts_poc.py --artwork tmp/drive-downloads/extracted/frontend-debug-bundle-20260826-122150/artwork.json --assets tmp/drive-downloads/extracted/frontend-debug-bundle-20260826-122150/assets --out tmp/print-data-2l-real-bundle-20260831-v3-grid06 --include-background --shape-mode grid --grid-cell-mm 0.6
```

結果は成功。警告なしで、4パーツと土台を生成できた。生成物は `tmp/print-data-2l-real-bundle-20260831-v3-grid06/`、ZIPは `tmp/print-data-2l-real-bundle-20260831-v3-grid06.zip` に置いた。

Contract検証では、以前と同じく `replacementCandidates` が空であることと、一部Source Photo PNGがRGBであることが注意として出る。ただし、今回のSTL化はLayer PNGのalphaを入力にするため、この注意は印刷データ生成の直接ブロッカーではない。

### 2L判土台のまま素材パーツを小さくする調整

2026-08-31に、土台は2L判寄りの170 x 121 x 5mmのまま、差し込む素材パーツだけを小さくした。前回はパーツ側も `targetWidthMm: 160` を基準にしていたため、最大レイヤーが約138mm幅になり、2L土台の上で主張が強すぎた。

今回の既定は `targetWidthMm: 120` に変更した。Artwork Dataの `x / y / scale / layerIndex` はそのまま使い、物理出力Config側の実寸解釈だけを変える。これにより、2L判の土台に対して素材パーツは一回り小さくなり、棚やデスクに置く飾りとして余白が残る。

実生成Bundleを同じ条件で作り直すと、最大パーツ幅は約138mmから約103mmへ下がった。差し込み足は12mm幅、スロットは1.95mm幅のまま維持するため、既存の4層3穴土台との整合は変えない。

出力は `tmp/print-data-2l-small-parts-20260831-grid06/`、ZIPは `tmp/print-data-2l-small-parts-20260831-grid06.zip` に置いた。共有用の寸法比較PNGとして `parts-size-comparison-120mm.png` も同じフォルダへ入れた。

### 未接続レイヤーを1パーツ化する修正

2026-08-31に、Bambu Studio上で素材パーツの一部が離れた島として見える問題を確認した。STLファイル上は同じファイルに含まれていても、形状が物理的につながっていない場合、印刷後は小片として分離する。4層分のパーツが別々に並ぶことは問題ないが、1つのlayer STLの内部に未接続の島が残る状態は印刷データとして失敗扱いにする。

ローカルPoCスクリプトに、RGBA alphaをグリッド化した後で連結成分を検出し、最大成分へ細い連結橋を追加する処理を入れた。輪郭ポリゴン方式で複数輪郭が出た場合も、そのまま複数島STLにせず、グリッド方式へ戻して連結処理を通す。生成後に `connectedComponentCount` が1より大きい場合は警告を出し、成功扱いにしない。

同じ実生成Bundleを使って作り直した結果、屋敷レイヤーは元が6塊、追加した橋が5本、最終的に1塊になった。他の3レイヤーは最初から1塊だった。出力は `tmp/print-data-2l-connected-parts-20260831-grid06/`、ZIPは `tmp/print-data-2l-connected-parts-20260831-grid06.zip` に置いた。確認用PNGは `connected-parts-check-20260831.png` で、黒が元のalpha由来形状、緑が追加した連結橋である。

### ブラウザZIPへの1:1貼り込みSVG同梱

2026-09-01に、Driveの「ナンちゃん向け_開発開始ガイド」を優先資料として読み直した。そこで改めて重要だったのは、物理出力の成果物がSTLだけでは終わらず、画像と組み合わせて棚やデスクに置ける2.5D作品になることだった。

ブラウザ版の印刷ZIPに `flat-photo-print-layout.svg` を追加した。各Layer画像を実寸mmで配置し、画像範囲、外形の目安、差し込みタブ側の領域、Layer labelを一枚のSVGへ入れる。表面素材は写真紙を第一候補にする。これにより、ブラウザだけで次の3点を同じZIPにまとめられる。

- 平面パーツSTL
- 2L判寄りの土台STL
- 写真紙用の1:1貼り込みSVG

Artwork Data本体には、URLやmm値を追加していない。画像URLは従来どおりAsset Manifestで解決し、製造条件と表面素材は `BrowserFlatPrintConfig` に置く。3D Printerへ直接送信せず、3MF / G-code化はBambu Studioへ渡す前提も維持する。

白PLAのシルエットだけで成立する対象もあるが、人物や集合写真の「本人らしさ」は外形だけでは残りにくい。MVPでは、STLは形と差し込み構造を担い、表面の記憶情報は写真紙で補う。次の実物検証では、写真紙の厚み、接着方法、外形カットの手間、端の浮きや反りを確認する。

### 差し込み脚の向き修正

2026-09-01に、Bambu Studio上でローカル生成STLの脚が写真面の背面方向へ立ち上がって見える問題を確認した。原因は、ローカルPoCスクリプトの既定が `mountMode: rear` になっていたことにある。

`rear` は写真面の下端に背面リブを足す考え方だったが、現行の土台は上面から差し込む縦スロットである。そのため、パーツを立てて組み立てるには、脚は写真面の下方向へ伸びている必要がある。背面リブのままだと、Bambu Studio上では脚だけが上へ出た寝かせパーツに見え、実物でも土台へ自然に差し込めない。

ローカルPoCスクリプトの既定を `mountMode: front-tab` に戻した。ブラウザ版の印刷ZIPと同じく、STLは写真面を上にして寝かせて印刷し、印刷後にパーツを起こして下方向のタブを土台スロットへ差し込む前提にする。

背面方向の支えが必要になった場合は、差し込み脚とは別の補助リブとして再設計する。少なくとも現行の2L判寄り土台では、脚と土台スロットの基本仕様を「下方向タブ + 上面スロット」にそろえる。

### 貼り込みSVGのガイド文字修正

2026-09-01に、`flat-photo-print-layout.svg` のガイド文字が画像や別パーツに重なって見える問題を確認した。原因は、長い `layerId` と日本語labelをそのまま紙面に出し、さらにタブ説明文を各パーツ内へ重ねていたことにある。

貼り込みSVGは、写真紙を実寸で印刷して切るための作業紙である。写真の位置とサイズが正しくても、ラベルやタブ説明が重なると、切る人がどこを残すべきか迷う。

ブラウザ版とローカルPoCスクリプトの両方で、紙面上の表示を短い `L<layerIndex> <label>` に変更した。長い `layerId` はSVGの `<title>` に残し、必要なときだけ確認できるようにした。タブ説明は各パーツへ重ねず、ページ上部の「写真紙100%印刷 / 赤い破線で切る / タブは残す」に集約する。

### 2Lキャンバス基準への再調整

2026-09-02に、実プリント写真を確認し、背景パネルが土台幅に対して小さく見える問題を見直した。原因は、前景パーツを小さめにするために `targetWidthMm: 120` を既定にしたことである。Artwork Dataの `scale` はフロントエンド表示上のキャンバス幅に対する割合なので、背景レイヤーの `scale` 約0.96も「追加の縮小率」ではなく、画面上の配置情報である。

フロントエンド表示との相対サイズを優先し、ブラウザ版とローカルPoCスクリプトの既定を `targetWidthMm: 178` に戻した。これにより、2L Landscapeの長辺を物理キャンバス幅として解釈し、背景も前景も同じ倍率でSTL化する。この時点では、Driveテストデータの背景パネルは約171mm幅になり、170mm幅の土台とほぼ揃っていた。

ただし、写真紙PDFで背景ページの左右に白余白が出ると、物理背景板としては弱く見える。2026-09-04時点の既定では、全面不透明の背景Layerだけを例外扱いし、2L Landscape全面へcover配置する。前景Layerの `x / y / scale` は従来どおり維持し、背景写真だけを歪ませずに上下cropして、背景STL板と貼り付けPDFを178 x 127mmへ揃える。

同じDriveテストデータを `targetWidthMm: 178`、`shapeMode: grid`、`gridCellMm: 0.6`、`includeBackground: true` で再生成した。出力は `poc-output/physical-print/01-kanazawa-memories-try1-2l-canvas-178/`、ZIPは `poc-output/physical-print/01-kanazawa-memories-try1-2l-canvas-178.zip` に置いた。当時の主な寸法は、背景171.03 x 132.00mm、灯籠45.36 x 40.34mm、丸皿56.96 x 55.97mm、人物85.17 x 107.66mm、土台170 x 121 x 5mmである。現在の背景寸法は後述の `backgroundFillMode: cover-2l` により178 x 127mmへ変わっている。

### 番号付きスロット土台

2026-09-02に、汎用土台の3スロット x 4列へ前から順に番号を振る方式を追加した。番号は `R1-A` のような行列記号ではなく、手前左から右へ `1, 2, 3`、次の列を `4, 5, 6`、奥の列を `10, 11, 12` とする。

番号は位置再現そのものではなく、組み立て時の差し込み先を間違えないためのガイドである。位置再現は、Artwork Dataの `x / layerIndex` からどの固定スロットを使うかを選び、選んだスロット位置に合わせてパーツ側のタブや接続部を設計することで担保する。スロットからレイヤー本体までが離れすぎる場合は、ブリッジが長くなって見た目や強度へ影響するため、警告または別方式を検討する。

土台STLでは、番号を上面から0.45mmだけ浅く彫った7セグメント風の立体文字として生成する。スロット穴そのものは埋めず、穴の手前側に番号を置く。これにより、土台上面に余計な出っ張りを作らず、Bambu Studio上でも番号の位置を確認できる。

レポートには、土台全体の `slotNumbering`、各番号の `slotLabels`、各スロットの `assemblyLabel` / `slotNumber` を残す。現時点では、各パーツに対して同じ奥行き行の3スロットを `compatibleSlotLabels` として出している。パーツ側へ番号を入れる場合は、次の段階でArtwork Dataの `x` に近い番号を1つ選び、その番号をタブまたは裏側へ付ける。

Driveテストデータでは次を実行した。

```bash
python scripts/flat_photo_parts_poc.py --artwork tmp/drive-physical-test-20260901/extracted/01-kanazawa-memories-physical_layer_v2-try1/artwork.json --assets tmp/drive-physical-test-20260901/extracted/01-kanazawa-memories-physical_layer_v2-try1/assets --out poc-output/physical-print/01-kanazawa-memories-try1-2l-canvas-178-engraved-base --include-background --shape-mode grid --grid-cell-mm 0.6
```

結果は成功。出力は `poc-output/physical-print/01-kanazawa-memories-try1-2l-canvas-178-engraved-base/` に置いた。土台STLは `flat-photo-parts-slot-base.stl` で、寸法は170 x 121 x 5.0mmである。番号部分は上面から0.45mm下げて彫り込むため、土台の最大高さは変わらない。

### Frontend STL生成PoCの撤去

2026-09-02に、技術設計を読み直し、Frontend側に置いていたTypeScript製のSTL ZIP生成PoCを撤去した。

技術設計では、Frontendの責任範囲は3D Preview、2D Edit、確定Artwork Data + Assetsの受け渡しである。Physical Outputは、確定Artwork Data + Assetsを受け取って実寸変換し、STL等を生成する領域として扱われている。Physical Outputの実行場所はPoC後FIXだが、少なくとも現時点ではFrontend TypeScriptをSTL生成ロジックの正本にはしない。

撤去したFrontend実装は次の範囲である。

- `frontend/src/print/flatPrint.ts`
- `frontend/src/print/PrintExportPanel.tsx`
- `frontend/src/print/simpleZip.ts`
- 上記に対応するFrontend test

同じ作業で `origin/frontend/3d-preview` の最新Frontendを取り込んだ。最新Frontend側にはSTL生成TypeScriptは含まれていない。残っている `frontend/src/bundle/artworkBundle.ts` は、確定Artwork Dataと参照AssetをPhysical Outputへ渡すためのPortable Artwork Bundleであり、STL / PDF / G-codeを生成しない。

今後の物理出力PoCの正本は `scripts/flat_photo_parts_poc.py` とする。Frontendから直接STL / PDF / G-code、またはSTLを含む印刷ZIPを生成する必要が出た場合は、共通技術設計でPhysical Outputの実行場所をFrontend内にFIXしてから再実装する。

同時に、Python PoCの既定値も現行の実プリント検証へ寄せた。`shapeMode` は `grid`、`gridCellMm` は0.6mm、背景レイヤーは既定で出力対象にする。背景を除外したい場合だけ `--exclude-background` を指定する。これにより、引数なしの最小実行でも「確定Artwork Data + Assetsを物理出力へ渡す」流れに近い4層出力を確認できる。

2026-09-04時点で、過去のFrontend STL生成PoCはPR #4としてmainへ取り込み済みである。そのため、対応は「未マージPRを閉じる」ではなく、次のPRでmain上の `frontend/src/print/*` を削除し、Backend/FastAPIのPhysical Output Endpointへ責務を移す形にする。Frontendに残すZIP生成は、検証用のArtwork Data + Assets Bundleに限定し、STL/PDF生成とは扱いを分ける。

### FastAPI artwork直渡しPoC

2026-09-02に、Frontend TypeScriptで行っていたSTL/PDF生成ではなく、BackendのFastAPIからPython PoC生成器を呼ぶ候補実装を追加した。

Endpointは `POST /api/v1/physical-output/exports`。入力はZIPではなく、Drive仕様の導線に合わせて次のmultipart form-dataにする。

- `artwork`: 確定Artwork Data JSON文字列
- `assets`: 現在の `layers[]` が参照するLayer Asset画像
- `outputFormat`: `stlZip` / `photoPdf` / `photoJpegZip`。未指定時は `stlZip`
- `physicalOutputConfig`: 任意JSON。未指定ならBackend側のPoC既定値（rail / 2L Landscape / 4行 x 3穴）

`sourcePhotos[]` や `replacementCandidates[]` が参照する元写真・候補画像は、物理出力STL/PDF/JPEG生成では必須にしない。Frontend側のBundleに含まれていても、今回のEndpointでは余分なAssetとして受け取り可能だが、STL/PDF/JPEG生成は現在のLayer Assetだけで行う。

Layer PNGは生成入力写真より大きくなることがあるため、生成APIの `maxPhotoBytes` ではなく、Physical Output専用の `maxPhysicalAssetBytes` / `maxPhysicalTotalAssetBytes` で検証する。とくに背景Layerは透過なしPNGになりやすく、2L相当の背景画像が15MiBを超えても物理出力上は正常な入力である。

Responseは `outputFormat` で分ける。これは、まなみん側Frontendの完成画面から用途別に「3Dプリンター用データ」「写真紙PDF」「貼り付け用レイヤーJPEG」を取得できるようにするためである。

`outputFormat=stlZip` のResponseは `application/zip`。これは入力導線をZIPに固定する意味ではなく、STL、製造条件、レポートを1回のダウンロードにまとめるための成果物コンテナである。

- `stl/`: 平面パーツSTLと番号付きスロット土台STL
- `physical-output-config.json`: Artwork Dataと分離した製造条件
- `flat-photo-parts-report.json`: 寸法、警告、スロット番号などのレポート
- `artwork.json`: 入力Artwork Dataの控え

`outputFormat=photoPdf` のResponseは `application/pdf`。写真紙を100%印刷して切るための `flat-photo-print-layout.pdf` を単体で返す。PDFの用紙サイズは既定で2L Landscape、178 x 127mmにする。各ページにはLayerの写真貼り込み面を1面ずつ原寸配置し、A4前提の余白紙面にはしない。SVGはユーザー向けの主要Downloadにしない。必要なら開発確認・手修正用の生成物として扱う。

`outputFormat=photoJpegZip` のResponseは `application/zip`。PDFが普通紙文書プリント扱いになりやすいコンビニ写真プリント向けに、2L LandscapeのJPEGを `photo/` にまとめて返す。既定は178 x 127mm、300dpi、2102 x 1500px。ZIPには `artwork.json`、`physical-output-config.json`、`flat-photo-parts-report.json`、READMEを含めるが、STLは含めない。

2026-09-04に、`photoJpegZip` の用途を貼り付け用レイヤー写真へ修正した。背景LayerはSTL/PDF上では背景パネルとして扱うが、コンビニで写真印刷して切り取り、パーツへ貼る対象は前景の切り抜きレイヤーである。そのため `photoJpegZip` には2L全面cover背景パネルを入れず、前景レイヤーのJPEGだけを入れる。

実装は `backend/app/api/v1/physical_output.py` と `backend/app/services/physical_output.py` に置く。生成処理の正本はまだ `scripts/flat_photo_parts_poc.py` のままで、Cloud Run ImageではDockerfileから `scripts/` を同梱して呼び出す。正式FIX時には、Physical Output runtimeをBackend内Packageへ移すか、独立Local Toolに切り出すかを改めて決める。

検証は次で行った。

```bash
cd backend
uv run pytest tests\test_physical_output_endpoint.py tests\test_no_extra_endpoints.py
uv run ruff check .
uv run pytest
cd ..
python -m py_compile scripts\flat_photo_parts_poc.py
git diff --check
```

結果は成功。狭いテストでは `12 passed`、backend全体では `78 passed`。`outputFormat=stlZip` はSTL ZIPを返し、`outputFormat=photoPdf` はPDF単体を返す。STL ZIPにはPDF/SVGを含めず、写真紙用PDFは別ボタンで取得する前提にした。

2026-09-03に、Frontend側から共有された `01-kanazawa-memories-physical_layer_v2-try1` Bundleを、FastAPI候補Endpointへ `assets/` ごと渡して確認した。Bundle内には元写真とLayer PNGが混在していたが、Endpoint側では `artwork.layers[]` が参照する4枚だけを使い、未使用Assetは無視した。

結果は成功。`outputFormat=stlZip` は4つの平面パーツSTLと番号付きスロット土台STLを含むZIPを返し、`outputFormat=photoPdf` は写真紙100%印刷用PDFを返した。出力は `poc-output/physical-api-real-test-20260903/` に置いた。背景Layerはalphaが全て255の透過なし画像で、真四角パネルとして扱う。他3Layerはalpha 0/255を持つ切り抜き済み画像として扱う。

### Frontend物理プレビュー検証

2026-09-03に、まなみん側へ共有する前の検証として、別作業ツリーでFrontendのThree.js Preview上へ番号付き土台を仮表示した。

この実装はSTL / PDF生成をFrontendへ戻すものではない。Frontendは、Artwork Dataの `x / y / scale / layerIndex` を読み、物理出力PoCと同じ3スロット x 4列の規則で、表示用の差し込み番号を派生計算する。Artwork Data本体には番号、mm値、土台情報を追加しない。

仮表示で描くものは次である。

- 170 x 121mm相当の土台
- 手前左から `1, 2, 3`、次列を `4, 5, 6` と進む12個の番号付き差し込み口
- `layerIndex` の大きいLayerを手前、`layerIndex: 0` を奥にした行割り当て
- 各Layerの `x` から最寄り列を選んだ差し込み番号
- 各パーツ側の番号バッジ
- 選択スロットから垂直に立つ表示用の支柱

初期の3D Previewでは、Layerを選択スロットの真上へスナップした物理成立後の位置で表示していた。しかし、固定スロット中心へ寄せるとFrontend上の構図と実物がずれやすい。現在は、STL側の `supportMode: tree` と同じ考え方に寄せ、Layer本体はArtwork Dataの `x` を土台幅へ写した位置に置き、長い差し込み溝と中心支柱、必要な場合の斜め補助リブで差分を吸収する。

この番号は、編集中に毎回Backendへ問い合わせないための即時プレビューである。最終出力時は、確定Artwork Data + AssetsをFastAPIの物理出力Endpointへ渡し、STL ZIP内の `flat-photo-parts-report.json` と実際に生成された土台・パーツ側の番号を正とする。

この検証用実装は、今回のBackend移管PRには含めない。まなみん側が正式実装する場合は、同じ考え方をFrontendの構成へ合わせて移植し、必要ならBackendの物理出力APIにPreview専用の軽いPlan Responseを追加する。

手元検証では、`?screen=preview` または `?screen=done` で共通Mockの該当画面から起動できるデバッグ入口も追加した。これは検証用であり、本番の画面遷移仕様ではない。

同日追記として、微調整画面のLayer Panelにも表示用の差し込み番号を出した。ユーザーは2D編集でLayerをドラッグ、四隅リサイズ、前後入れ替えできる。検証用には左右・上下・大きさのスライダーも追加し、操作後にスロット番号がどう変わるかを確認できるようにした。ここでの番号もArtwork Dataへ保存する値ではなく、現行Artwork Dataから派生した表示である。

### Artwork y位置からの垂直支え生成

2026-09-03に、平面パーツSTLへ垂直支えを追加した。これまでのPython PoCは、alphaから切り抜いた画像外形のすぐ下に差し込みタブを付けていたため、Frontend上で浮いて見えるLayerでも、実物では画像下端が土台面まで落ちたような部品になっていた。

Artwork Schemaには物理的な高さFieldを追加しない。支え高さは、`targetWidthMm / canvas.aspectRatio` で物理キャンバス高さを出し、各Layerの `y / scale` とRGBA alphaの下端から「画像下端からキャンバス下端までのgap」を生成時に計算する。このgapが `verticalSupportMinHeightMm` 以上ある場合だけ、画像下端からタブまでまっすぐな支え板を追加する。

追加したConfigは次の2つである。

- `verticalSupportWidthMm`: まっすぐ下へ落とす支え板の幅。既定は4mm
- `verticalSupportMinHeightMm`: この高さ未満なら支えを出さない閾値。既定は1mm

タブ番号は従来どおりタブ側に彫る。支え板は番号を持たず、画像下端とタブをつなぐ構造として扱う。これにより、前後位置は `layerIndex`、横位置は固定スロット番号、縦方向の浮きはArtworkの `y` から派生した支え高さで再現する。

FastAPI候補Endpointでも同じConfigを受け取れるようにした。`flat-photo-parts-report.json` には、各パーツの `dimensionsMm.verticalSupportHeightMm`、`verticalSupports[]`、`artworkPlacementMm.visibleBottomYMm`、`artworkPlacementMm.bottomGapToCanvasMm` を残す。写真貼り付け用PDF/SVGにも支え位置のガイド線を出し、STL側の形状と写真紙の切り取り範囲が対応するようにした。

Frontend側から共有された `01-kanazawa-memories-physical_layer_v2-try1` BundleをFastAPI候補Endpointへ投げ直し、STL ZIPの生成を確認した。結果は4パーツ + 土台STLで計5 STL。支え高さは、背景0mm、灯籠系Layer 10.268mm、丸皿系Layer 15.153mm、人物0mmになった。背景と人物は画像下端がキャンバス下端まで届くため、追加支えを出していない。

### 長い差し込み溝とtree支えの検証

2026-09-03に、固定スロット中心へLayer位置を寄せない案として、検証用の `supportMode: tree` を追加した。当初の通常既定は `supportMode: straight` のままで、既存のまっすぐな支え方を維持していた。

`supportMode: tree` では、土台の各横列を3分割し、各区画に長い差し込み溝を置く。パーツ側も同じ長さに近い横長タブを持つ。Layer本体の支柱は、タブ中心ではなく画像パーツの中心から下ろし、タブ上の左右差は斜めの補助リブで受ける。これにより、Artwork Dataの `x` を短いスロット中心へ丸める量を減らしつつ、穴がない位置にも支柱を立てられる。

追加したConfigは次である。

- `supportMode`: `straight` または `tree`
- `treeBranchWidthMm`: 斜め補助リブの幅。既定は2.4mm
- `treeSupportEdgeMarginMm`: 横長タブ端から補助リブを内側へ逃がす余白。既定は4mm

Frontend側から共有された `01-kanazawa-memories-physical_layer_v2-try1` Bundleで、次を実行した。

```bash
python scripts/flat_photo_parts_poc.py --artwork C:\Users\indod\Downloads\01-kanazawa-memories-physical_layer_v2-try1\01-kanazawa-memories-physical_layer_v2-try1\artwork.json --assets C:\Users\indod\Downloads\01-kanazawa-memories-physical_layer_v2-try1\01-kanazawa-memories-physical_layer_v2-try1\assets --out poc-output\physical-print\01-kanazawa-memories-tree-support-20260903 --include-background --shape-mode grid --grid-cell-mm 0.6 --support-mode tree --base-slot-length-mm 55 --tab-width-mm 54
```

結果は成功。出力は `poc-output/physical-print/01-kanazawa-memories-tree-support-20260903/` に置いた。支えが出たLayerは2つで、灯籠系Layerはスロット中心から -10.2mm、丸皿系Layerは +9.07mmずれた位置から中心幹を下ろし、それぞれ2本の斜め補助リブを生成した。支え高さは、灯籠系Layer 10.268mm、丸皿系Layer 15.153mmである。

確認用として、土台と全パーツを組み立て姿勢に変換した `assembled-tree-support-validation.stl` も同じ出力ディレクトリに作成した。これは分割印刷用の正本ではなく、Bambu Studio等で位置関係を見るための検証用STLである。

### Frontend長溝プレビュー追随

2026-09-03に、別作業ツリーの検証用Frontendで、Three.js Previewを上記の `supportMode: tree` 出力に合わせた。表示上は `supportMode: tree`、`baseSlotLengthMm: 55` にし、土台の横方向を3分割した長い溝として見せる。

Layer本体は短いスロット中心へスナップしない。Artwork Dataの `x` を170mm土台幅へ写した `targetBaseXCenterMm` に置き、支柱はそのLayer中心からまっすぐ下へ出す。選択された長溝の中心とLayer中心がずれる場合は、STL側と同じく斜め補助リブを表示する。

この変更は、FrontendでSTLやPDFを生成するための実装ではない。まなみん側Frontendへ共有する「物理側の見た目・差し込み制約」の検証用であり、確定データの生成正本は引き続きBackend/FastAPI側のPhysical Outputに置く。

### 横レール方式の検証

2026-09-04に、短い差し込み口へLayer位置を丸めず、Artwork Dataの `x` をより素直に扱うための検証用 `supportMode: rail` を追加した。

`supportMode: rail` では、土台そのものは4行 x 3穴の短い差し込み口のまま維持する。各Layerパーツ側に、その行の3穴すべてへ差し込む横レールを付ける。Layer本体は横レール上の `targetBaseXCenterMm` から立ち上げるため、1つの穴の中央へ寄せずに `x` 位置を再現できる。Artwork上で下端がキャンバス下端から浮いているLayerは、横レール上面からLayer下端まで中央支柱を伸ばす。

追加したConfigは次である。

- `supportMode`: `straight`、`tree`、`rail`
- `railBodyHeightMm`: 横レール本体の高さ。既定は4mm
- `railSupportWidthMm`: 横レールとLayer本体をつなぐ支え板の幅。既定は10mm
- `railEdgeMarginMm`: 横レールを土台左右端から内側へ逃がす余白。既定は0mm

レポートには、各Partへ `rails[]` を追加する。`slotAssignment.selectedBy` は `rowRail`、`assemblyLabel` は `1-3`、`4-6` のように行全体を表す。`tabs[]` は従来の1つではなく、同じ行の3穴へ入る3つの差し込み足を持つ。Backend/FastAPI候補Endpointも `physicalOutputConfig.supportMode: "rail"` を受け取れる。

別作業ツリーの検証用Three.js Previewも `supportMode: rail` に合わせた。選択状態は各行の3穴すべてを強調し、Layer本体は `targetBaseXCenterMm` 上に置く。Previewは確定データの生成正本ではなく、物理側仕様をまなみん側Frontendへ共有するための参照実装である。

2026-09-04に、Frontendへ物理寸法や土台情報を持たせず、Backend側をPhysical Output仕様の正本に寄せるため、`FlatPhotoPartConfig.supportMode` のPoC既定値を `rail` に変更した。`physicalOutputConfig` は引き続き任意overrideとして受け取れるが、Frontendから未指定で呼んでもrail / 2L Landscape / 4行 x 3穴のBackend既定値でSTL ZIPまたは写真紙PDFを生成する。

Frontend側から共有された `01-kanazawa-memories-physical_layer_v2-try1` Bundleで、次を実行した。

```bash
python scripts/flat_photo_parts_poc.py --artwork C:\Users\indod\Downloads\01-kanazawa-memories-physical_layer_v2-try1\01-kanazawa-memories-physical_layer_v2-try1\artwork.json --assets C:\Users\indod\Downloads\01-kanazawa-memories-physical_layer_v2-try1\01-kanazawa-memories-physical_layer_v2-try1\assets --out poc-output\physical-print\01-kanazawa-memories-rail-support-20260904 --include-background --shape-mode grid --grid-cell-mm 0.6 --support-mode rail
```

結果は成功。出力は `poc-output/physical-print/01-kanazawa-memories-rail-support-20260904/` に置いた。各Partは横レール1本と差し込み足3つを持つ。支え高さは、背景0mm、灯籠系Layer 10.268mm、丸皿系Layer 15.153mm、人物0mmである。行割り当ては、人物 `1-3`、丸皿 `4-6`、灯籠 `7-9`、背景 `10-12` になった。

差し込み状態の確認用として、土台と全パーツを組み立て姿勢に変換した `assembled-rail-support-validation.stl` も同じ出力ディレクトリに作成した。これは分割印刷用の正本ではなく、Bambu Studio等で位置関係を見るための検証用STLである。ZIPは `poc-output/physical-print/01-kanazawa-memories-rail-support-20260904-assembled.zip` に置いた。

検証は次で行った。

```bash
python -m py_compile scripts\flat_photo_parts_poc.py
cd backend
uv run pytest tests\test_physical_output_endpoint.py tests\test_no_extra_endpoints.py
uv run ruff check .
```

結果は成功。Backendの狭いテストは `14 passed`、Ruffも通った。FrontendのPreview追随は別作業ツリーの検証として扱い、今回のBackend移管PRには含めない。

### 支柱根元の補強

2026-09-04に、実出力したパーツで、横レールや支柱からLayer本体へ入る根元がほぼ点接触になり、剥がれや折れのリスクが高いことを確認した。特に丸い皿のような下端が曲線のパーツでは、細い支柱だけを生やすと接触面積が不足しやすい。

このため、支柱が必要なLayerには、支柱本体とは別に `rootPad` を追加する。既定値は `supportRootPadWidthMm: 12.0`、`supportRootPadHeightMm: 5.0`、`supportRootOverlapMm: 2.0` とし、Layer本体の下端へ2mm食い込ませながら、支柱根元を幅広い面で接続する。支柱本体は従来どおり中心からまっすぐ生やすが、根元だけは補強面を重ねて、写真紙を貼る対象の輪郭と支持構造が分離しすぎないようにする。

この補強値はArtwork Dataへは入れない。`FlatPhotoPartConfig` とBackendの `physicalOutputConfig` で調整可能な製造条件として扱う。SVG確認図にもrootPadを描画し、STLで追加された補強範囲を目視確認できるようにする。

Driveテストデータで再生成したところ、支柱が必要な灯籠Layerと丸皿Layerに `rootPad` が付与された。どちらも `12 x 5mm`、Layer本体への食い込みは `2mm` である。検証後、確認用に作成した `tmp\root-pad-check-20260904` は削除した。検証は `python -m py_compile scripts\flat_photo_parts_poc.py`、`uv run pytest tests\test_physical_output_endpoint.py tests\test_no_extra_endpoints.py -q`、`uv run ruff check .`、`git diff --check` で通過した。

### 2L写真紙PDFの用紙サイズ固定

2026-09-04に、`outputFormat=photoPdf` のPDF MediaBoxがA4相当になっている問題を確認した。ファイル名や物理キャンバス基準は2L寄りでも、PDFページ自体がA4だと、写真店・家庭プリンター側で用紙指定を誤りやすい。

`FlatPhotoPartConfig` に `printLayoutPageWidthMm` / `printLayoutPageHeightMm` を追加し、既定を2L Landscapeの178 x 127mmにした。`photoPdf` は各Layerの `imageAreaMm` を1ページ1面で原寸配置する。タブ、レール、支えを含むパーツ全体の確認は引き続きSVG / STL / report側で扱い、ユーザー向けPDFは写真紙に載せる画像面を2L余白なしで返す。

`flat-photo-parts-report.json` には、`printLayout.photoPdfPageSizeMm`、`photoPdfPageCount`、各Partの `photoPrintLayoutMm` を追加した。Artwork Data本体にはmm値を追加しない。

検証は次で行った。

```bash
python -m py_compile scripts\flat_photo_parts_poc.py
cd backend
uv run pytest tests\test_physical_output_endpoint.py -q
uv run ruff check .
cd ..
python scripts\flat_photo_parts_poc.py --out tmp\2l-pdf-check-20260904 --include-background
pdfinfo -box tmp\2l-pdf-check-20260904\flat-photo-print-layout.pdf
pdftoppm -png -f 1 -l 1 -singlefile tmp\2l-pdf-check-20260904\flat-photo-print-layout.pdf tmp\2l-pdf-check-20260904\page-1
```

結果は成功。Endpointの狭いテストは `11 passed`、Ruffも成功。`pdfinfo` では `Pages: 4`、`Page size: 504.48 x 360 pts`、`MediaBox: 0.00 0.00 504.48 360.00` になり、約178 x 127mmの2L Landscapeとして出力できていることを確認した。確認後、`tmp\2l-pdf-check-20260904` は削除した。

### 透過なし背景Layerの2L全面cover

2026-09-04に、背景写真が2L PDFの端まで届かず、左右に約3.5mmずつ白余白が出ることを確認した。原因は、Driveテストデータの背景画像比率が2L Landscapeより少し縦長で、画像を歪ませずに全体を収めると `171.03 x 127mm` になるためである。

現在の既定では、`FlatPhotoPartConfig.backgroundFillMode` を `cover-2l` にした。対象は `layerIndex: 0` かつalpha bboxが画像全体を覆う全面不透明PNGに限定する。該当する背景Layerは、STLの貼り込み面も写真紙PDF上の画像面も `178 x 127mm` に固定し、元画像は2L比率へ中央cover cropする。前景の切り抜きLayerにはこの特例を適用しない。

Driveテストデータでは、背景元画像 `4032 x 2994px` を `4032 x 2877px` にcropした。cropは `top: 58px`、`bottom: 2935px` で、左右は落としていない。出力は `poc-output/physical-print/01-kanazawa-memories-cover-background-20260904/` に置いた。レポート上の背景 `imageAreaMm` と `photoPrintLayoutMm` はどちらも `178 x 127mm`、`xMm: 0`、`yMm: 0` である。

Frontend側へ共有する表示要件も同じ考え方に寄せる。物理プレビューでは `layerIndex: 0` の背景をCanvas全面の平面として表示し、Three.jsのTexture `repeat / offset` を使ってcover crop表示すると、STL/PDFの背景板とプレビュー上の背景の見え方を揃えられる。

検証は次で行った。

```bash
python -m py_compile scripts\flat_photo_parts_poc.py
cd backend
uv run pytest tests\test_physical_output_endpoint.py
uv run ruff check .
cd ..
python scripts\flat_photo_parts_poc.py --artwork C:\Users\indod\Downloads\01-kanazawa-memories-physical_layer_v2-try1\01-kanazawa-memories-physical_layer_v2-try1\artwork.json --assets C:\Users\indod\Downloads\01-kanazawa-memories-physical_layer_v2-try1\01-kanazawa-memories-physical_layer_v2-try1\assets --out poc-output\physical-print\01-kanazawa-memories-cover-background-20260904 --include-background --shape-mode grid --grid-cell-mm 0.6 --support-mode rail
pdfinfo -box poc-output\physical-print\01-kanazawa-memories-cover-background-20260904\flat-photo-print-layout.pdf
pdftoppm -png -f 1 -l 1 -singlefile -r 72 poc-output\physical-print\01-kanazawa-memories-cover-background-20260904\flat-photo-print-layout.pdf tmp\pdfs\2l-cover-background-check-20260904\page-1
```

結果は成功。BackendのPhysical Output Endpointテストは `12 passed`、Ruffは成功した。`pdfinfo` では `Pages: 4`、`Page size: 504.48 x 360 pts`、`MediaBox: 0.00 0.00 504.48 360.00` で、2L Landscapeとして出力できている。確認後、`tmp\pdfs\2l-cover-background-check-20260904` は削除した。

### 土台スロット全体の奥寄せ

2026-09-04に、番号付き土台の最奥行 `10, 11, 12` が背景パネル用としては手前に見える問題を確認した。いったん後ろ余白だけを詰める案を試したが、土台全体としてもスロット列が中央寄りに見えるため、4行すべてを少し奥へ寄せる設定にした。

土台寸法は `170 x 121 x 5mm` のまま、前余白を `11mm`、後ろ余白を `5mm` にする。これにより、数字刻印が前端やスロットに食い込む余白を残しつつ、`1-3` から `10-12` までの全行を約3mm奥へ移動する。

同じ設定で `C:\Users\indod\Downloads\osaka-test.zip` も再生成した。ZIP内の `osaka-test/artwork.json` と `osaka-test/assets/` を一時展開して使い、一時展開分は生成後に残していない。出力は `poc-output/physical-print/osaka-test-slot-base-all-back-20260904/`、STLだけをまとめたZIPは `poc-output/physical-print/osaka-test-slot-base-all-back-20260904-stl.zip` に置いた。生成結果は4レイヤー + 番号付き土台で、warningsは空。report上の各行は、`1-3: 11.00-12.95mm`、`4-6: 45.35-47.30mm`、`7-9: 79.70-81.65mm`、`10-12: 114.05-116.00mm` になった。PDFは4ページ、2L Landscape、`Page size: 504.48 x 360 pts`、`MediaBox: 0.00 0.00 504.48 360.00` である。

### 横レール支えの接合強化

2026-09-04に、Bambu Studio上で横レール支えがLayer本体へ細くしか接続していない問題を確認した。原因は、rail方式の縦支えを画像中心基準の1本だけで作り、幅も `verticalSupportWidthMm: 4`、重なりも `tabOverlapMm: 1` にしていたことにある。下端の素材が左寄りのLayerでは、支えが実際の輪郭外側に寄り、印刷後に引きちぎれるリスクが高かった。

rail方式では、`verticalSupportWidthMm` ではなく `railSupportWidthMm: 10` を使う。支え位置は画像中心ではなく、alpha maskの下端4mmを走査した `bottomSupportIntervalsMm` から選ぶ。広い下端素材がある場合は同じ横レールへ2本の支えを落とし、狭い場合はその素材範囲に収まる最大10mm幅の支えを1本置く。`tabOverlapMm` も2mmへ増やし、Layer本体、`rootPad`、支え、横レール、差し込み足の重なりを増やした。

`flat-photo-parts-report.json` には、横レール側へ `railSupportSpansMm`、各支えへ `bodyAnchorSpanMm` と `imageBottomIntervalMm` を残す。これにより、支えがどの下端素材を根拠に配置されたかを後から確認できる。

同じ `C:\Users\indod\Downloads\osaka-test.zip` を新設定で再生成した。出力は `poc-output/physical-print/osaka-test-rail-strong-support-20260904/`、STLだけをまとめたZIPは `poc-output/physical-print/osaka-test-rail-strong-support-20260904-stl.zip` に置いた。結果は4レイヤー + 番号付き土台で、warningsは空。浮いている2レイヤーのうち、Tsutenkaku人物Layerは10mm幅支え2本、たこ焼き箱Layerは10mm幅支え1本になった。PDFは4ページ、2L Landscape、`Page size: 504.48 x 360 pts`、`MediaBox: 0.00 0.00 504.48 360.00` である。
