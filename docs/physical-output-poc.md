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
- `outlineMarginMm`: 0.35
- `shapeMode`: contour
- `contourSimplifyMm`: 0.10
- `gridCellMm`: 2
- `mountMode`: rear
- `tabWidthMm`: 16
- `tabHeightMm`: 7
- `tabOverlapMm`: 1
- `slotClearanceMm`: 0.4
- `baseMode`: square-grid
- `baseSideMm`: 90
- `baseLayerCapacity`: 4
- `baseSlotsPerLayer`: 3
- `baseSlotLengthMm`: 16
- `baseFrontMarginYMm`: 8
- `baseBackMarginYMm`: 24
- `baseLayerGapMm`: 7
- `baseHeightMm`: 8
- `material`: PLA

既定の形状生成は、2mmグリッドではなく輪郭ポリゴン押し出しにした。OpenCVが使えない、または輪郭の三角形化に失敗した場合だけグリッド方式へフォールバックする。意図せずフォールバックした場合は、レポートの `warnings` に出す。

### 出力

生成物は `tmp/flat-photo-parts-poc/` に出る。

- `label` が花、犬、人物になっているダミーLayerの背面マウントつき平面パーツSTL
- パーツの背面マウント位置に対応したスロット土台STL
- カット線、背面マウント位置、貼り込み範囲を入れた1:1印刷用 `flat-photo-print-layout.svg`
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
