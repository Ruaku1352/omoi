# Artwork Output Quality Gap Report

## 1. Executive Summary

2026-08-26 の最新成功 Real AI bundle を、入力写真、Gemini の Semantic Plan / bbox、
EfficientSAM の mask、RGBA Layer、最終 composition の順で追跡した。

この出力は、5枚の写真と `memoryText` を1つの金沢旅行としてまとめ、食・夜景・建築・
文化体験の4要素を選び、4 Layer / 2L Landscape / Contract整合というMVPの機能要件を
満たしている。漆皿と石塔は単体Layerとして判別でき、漆皿のmaskは特に安定している。

一方、作品品質・物理Layer品質の主なボトルネックは次の3点である。

1. **庭園母屋のmaskが複数の屋根・木・建屋断片に分裂し、明白な背景混入を含む。**
   `mask_score=0.854`でも受理され、最終作品で最も目立つ品質低下になっている。
2. **「母屋」を選ぶには遮蔽物が多いsource photoと広すぎるbboxであり、対象選定・
   source選択・bboxの組合せがSegmentationに不利である。**
3. **構図は4要素を収めることには成功したが、石塔の孤立と皿の強い前景支配により、
   “一つの思い出のLayer Artwork”より切り抜きの寄せ集めに見える。**

このレポートは調査のみであり、Prompt、Quality Gate、Segmentation、Composition、
Contract、Cloud、Frontendの実装は変更していない。

## 2. Scope / Reviewed Artifacts

### Repository state

- Reviewed branch: `feat/ai-mvp-5photos-4layers`
- Reviewed commit: `ddc3daf` (`feat(ai): add real frontend handoff bundle`)
- Base branch present locally: `main`
- Working tree at review start: user-owned `.gitignore` modification only。変更・stageしていない。
- `gh pr list` はこの実行環境のGitHub GraphQL network制限により取得不能だった。PR状態は
  本調査の画像品質判断には用いていない。

### Primary artifact

主評価対象は、最新で、5 photos + non-empty `memoryText`、4 layers、source / bbox /
mask / layer / composition evidenceをすべて持つ次の成功Real runである。

```text
poc-output/final-mvp/frontend-debug-bundle-20260826-122150/
```

このbundleの `README.md` は「Real AIへ入力した5枚の写真とmemoryTextから生成」と明記する。
`MOCK_AI` の出力は本評価に使用していない。比較用に `docs/ai/12_MVP_POC_RESULT.md` と
過去のPoC出力も確認したが、主評価を古い5 layer / 非2L結果へ混ぜていない。

| Evidence | 用途 |
|---|---|
| `memory-text.txt` | 入力の思い出文 |
| `debug/semantic-plan.json` | candidate、source、理由、Gemini bbox |
| `debug/sources/source-01..05.png` | 5枚の元写真 |
| `debug/bbox/source-01..05-bbox.png` と `debug/bbox/index.json` | bboxの目視・座標 |
| `debug/masks/mask-001..004.png` と `debug/masks/index.json` | maskの目視・Quality metric |
| `debug/layers/*.png` と `assets/layer-*.png` | RGBA Layer |
| `debug/composition-preview.png` | Artwork全体 |
| `artwork.json` / `asset-manifest.bundle.json` / `metrics.json` | Geometry、Asset、時間・score |

## 3. Current MVP Output

| 項目 | 観測値 |
|---|---|
| Input | 5 photos、非空 `memoryText` |
| `memoryText` | 「金沢観光で、庭園・伝統建築・食・文化体験を楽しんだ大切な一日。」 |
| Semantic / Composition model | `gemini-3.7-flash`（PoC時設定、FIXではない） |
| Segmentation | EfficientSAM-Ti ONNX Runtime CPU |
| Output | 4 layers、`layerIndex` 0–3 |
| Canvas | `aspectRatio=1.4015748031496063` = `178 / 127` |
| Total elapsed | 51,714 ms |
| Semantic / Composition | 29,248 ms / 9,973 ms |

採用された要素は、木組み復元模型、金箔蒔絵の漆皿、夜間石塔、武家屋敷の庭園と母屋である。
庭園・伝統建築・食・文化体験という入力のカテゴリを概ねカバーしており、写真にない対象の
生成は観測されなかった。

## 4. Functional Requirements

本レビューは `AGENTS.md` のArtwork SSOT、P0の4-layer 2L Landscape、及び
`docs/ai/08_ACCEPTANCE_CRITERIA.md` のSemantic / Segmentation / Layer / Composition /
Contract受入項目を、画像品質の観点まで具体化して評価した。

評価記号は **○ 問題なし / △ 改善余地あり / × 明確な問題 / ? 判断材料不足**。
物理出力の最小幅等の製造閾値は本レポートで決定しない。

## 5. Requirement Gap Matrix

| 要件 | 判定 | 根拠 | Gap |
|---|---|---|---|
| 5 photos + memoryTextを一つの思い出として扱う | ○ | `memory-text.txt` と `semantic-plan.json` の `memory_summary` が一致 | 個別写真の単純列挙ではない |
| 4つの意味ある要素 | △ | 皿・石塔・模型は明確。庭園母屋は抽出結果が意味を失う | 4つ目のLayerが作品素材として不安定 |
| source / bbox / mask / RGBA追跡可能 | ○ | debug evidence一式が揃う | 観測可能性は十分 |
| RGBA独立Layer | △ | 全4件がRGBAだが、母屋には背景混入、模型には物理化リスクの高い複雑な細部が残る | 「透過PNG」であることだけでは独立性を保証しない |
| 物理Layerとしてまとまりがある | × | `mask-004.png` の大きな分離屋根片・小島 | 母屋Layerは一枚の物理Layerとして不自然 |
| 4Layerの統一感・視認性 | △ | 4件とも見えるが、皿が前景を強く支配し石塔が孤立 | 視覚的接続が弱い |
| Artwork / Asset整合 | ○ | JSON、実Asset、座標を後述の検証で確認 | データ欠損は未検出 |

## 6. Overall Artwork Review

`debug/composition-preview.png` は、金沢の文化体験（皿）、建築（模型・母屋）、庭園夜景
（石塔）を一画面へ収めることに成功している。漆皿の金色の蛙・音符は一目で分かり、
木組み模型も大きな主題として認識できる。

しかし、右上に散る瓦屋根断片、石塔の孤立、皿の大きな円形前景により、要素間の関係が弱い。
特に母屋Layerの断片は「庭園と母屋」の意味を補強せず、最終画面で背景混入として認識される。
このため、MVP統合・Frontend handoffには使えるが、現状を物理作品の品質合格と呼ぶ根拠はない。

## 7. Per-Layer Review

| Layer (index) | Semantic | Source | BBox | Mask | Physical shape | Composition | Overall |
|---|---|---|---|---|---|---|---|
| 0 武家屋敷の日本庭園と母屋 | △ | × | △ | × | × | × | × |
| 1 金沢城の木組み復元模型 | ○ | ○ | ○ | △ | △ | ○ | △ |
| 2 夜間ライトアップの石塔 | ○ | △ | ○ | ○ | △ | △ | △ |
| 3 金箔蒔絵の漆塗り銘々皿 | ○ | ○ | ○ | ○ | △ | △ | ○ |

配列位置ではなく `layerIndex` で表記した。各Layerの詳細は後節に記す。

## 8. Semantic Review

### Observed

- `semantic-plan.json` の `memory_summary` は入力文と同じ金沢観光の庭園・伝統建築・食・
  文化体験を要約する。
- 採用4要素は異なるカテゴリで、同一対象の重複ではない。未採用候補には桜、竹垣、石灯籠が
  含まれ、候補探索自体には幅がある。
- 皿は「蛙と音符柄漆器丸皿」として実写に存在し、石塔・模型・母屋もsourceに存在する。
  捏造は見つからなかった。

### Gap

「庭園と母屋」という広い複合景観は、レイヤーに切り出す対象として不利だった。
Semantic上の旅行らしさはある一方、単体Layerのidentityと物理化可能性を十分に優先した
選択だったとは画像から言えない。

**Likely stage:** Semantic / Source (Medium)。選定理由は妥当だが、後段で孤立物体にしにくい
「景観全体」を選択している。Semantic指示だけが根因とは断定できない。

## 9. Source Photo Review

| Candidate | Source evidence | 評価 | 観測 |
|---|---|---|---|
| 木組み模型 | `debug/sources/source-05.png` | ○ | 大きく、全体が正面寄りに写り、模型の意味を認識できる |
| 漆皿 | `debug/sources/source-03.png` | ○ | 大きな円形で遮蔽が少ない。柄も残る |
| 石塔 | `debug/sources/source-02.png` | △ | 縦方向には十分写るが、夜景の樹木・水面とのコントラストが複雑 |
| 庭園母屋 | `debug/sources/source-04.png` | × | 樹木が建屋を遮り、瓦屋根・幹・低木が重なる。単体の「母屋」sourceとして分離しにくい |

母屋はsourceが悪いというより、選んだ写真中に明確な単体silhouetteがない。これを
Segmentation単独の失敗として扱うと、根因を過小評価する。

## 10. BBox Review

| Candidate | Evidence / prompt box | 評価 | 観測 |
|---|---|---|---|
| 木組み模型 | `bbox/source-05-bbox.png`; `[258,916,3601,2401]` | ○ | 模型全体を含み、別の展示物・外枠を大きく巻き込まない |
| 漆皿 | `bbox/source-03-bbox.png`; `[76,863,2888,3383]` | ○ | 円皿全体を含む。背景紙はあるが円の輪郭は明確 |
| 石塔 | `bbox/source-02-bbox.png`; `[2516,986,2822,1869]` | ○ | 石塔全体を頭部から基部まで含む |
| 庭園母屋 | `bbox/source-04-bbox.png`; `[1746,314,4032,1703]` | △ | 母屋の一部は含むが、前景の太い樹木と複数屋根面を広く含む。右端まで接し、対象境界を限定していない |

母屋bboxの問題は、bboxが画像上で明白に誤位置ということではない。対象名が「庭園と母屋」と
広く、箱の中に複数の高コントラスト構造があるため、単一object promptとして曖昧である。

## 11. Segmentation / Mask Review

| Candidate | score / area / coverage / border | 判定 | 観測 |
|---|---:|---|---|
| 木組み模型 | 0.904 / 0.285 / 0.699 / false | △ | `masks/mask-001.png` は模型全体を大きく捉えるが、細い梁・内部空隙が多い |
| 漆皿 | 0.987 / 0.449 / 0.772 / false | ○ | `masks/mask-002.png` は円皿の外周をほぼ正しく捉える |
| 石塔 | 0.948 / 0.012 / 0.541 / false | ○ | `masks/mask-003.png` は石塔の段形状を保つ。背景混入は目立たない |
| 庭園母屋 | 0.854 / 0.071 / 0.274 / true | × | `masks/mask-004.png` は分離した屋根片、建屋・樹木の縦片、微小な飛び地を含む |

### Quality Gate gap

`backend/ai/quality.py` は空mask・画像全体mask・prompt外maskのみをhard failにする。
そのため、母屋の `borderTouch=true`、`bboxCoverage=0.274`、断片化は記録されても
`accepted=true` になる。これは実装不具合の断定ではなく、現Quality Gateが意図どおり
「強い閾値をFIXしない」設計であり、物理Layer品質をまだ判定していないという観測である。

## 12. RGBA Layer Review

全4 assetは実ファイルでも `RGBA` PNGで、宣言寸法と一致した。alpha=0の割合は母屋 69.24%、
模型 28.64%、石塔 41.53%、皿 22.38%であり、いずれにも透明領域がある。

| Layer | Asset evidence | 評価 | 観測 |
|---|---|---|---|
| 母屋 | `assets/layer-b0062e16fa9f45b9b23e1c69ab269281.png` | × | 複数の屋根・幹・建屋断片。単体で「庭園と母屋」と理解しにくい |
| 模型 | `assets/layer-0070ae0ba3784fc385bd7d3dc987eb88.png` | △ | 色と形は保つが、木組みの細部が非常に密。単一の塊ではない |
| 石塔 | `assets/layer-dde2bfb996314a4797c04063135c8eed.png` | ○ | 対象を判別できる縦長Layer |
| 皿 | `assets/layer-a7bd0d48330b4f1e8b749013246f4752.png` | ○ | 円形と蛙・音符が自然で、背景は透明 |

RGBAであること・tight cropであることは確認できたが、alpha面積の大きさだけでは背景混入や
fragmentationを検出できない。

## 13. Physical Layer Suitability

### 13.1 Fragmentation / Islands

`mask-004.png` には、中央の縦長建屋片とは離れた屋根片が少なくとも3つ、さらに小さな島が
目視できる。これらは人物と持ち物のような意味ある複数componentではなく、同一の「母屋」から
偶発的に切れた見え方である。物理Layerにすると、別パーツ・不要な支持のいずれかになり得る。

模型は多数の梁で複雑だが、対象自体が模型であり、主な成分は意味のある構造である。皿はほぼ
単一円形、石塔は一続きの段形状で、不要な島は目立たない。

### 13.2 Thin Structures

- 木組み模型: 多数の細い梁、格子、内部空隙を持つ。画像上ではidentityに寄与するが、物理化の
  強度・再現性リスクが高い。
- 石塔: くびれ、屋根の張り出しが小さく、縮小時に細部が失われる可能性がある。
- 母屋: 屋根端・枝・木の幹の細い断片が多い。
- 皿: 円周と模様はあるが、外形は最も単純で安定している。

閾値（mm）はPhysical Output PoCの責務であり、本レポートではFIXしない。

### 13.3 Holes / Complex Contours

模型には意図的な梁間の大きな空隙が多い。母屋には意図が判別できない切れ目と複雑な輪郭が
混在する。皿の外形は単純で、石塔は段形状に対応する凹凸である。

### 13.4 Layer Identity

皿は「漆皿」、石塔は「石塔」、模型は「木組み模型」と単体で理解できる。母屋は屋根・建物・
樹木の断片の集合に見え、labelの意味を単体で保てていない。

## 14. Composition Review

### 14.1 Layout

`debug/composition-preview.png` では、模型（scale 0.86）と皿（0.44）が主役、石塔（0.18）が
補助要素としてサイズ差を持つ。4Layerはcanvas外に出ず、単純な横一列でもない。

ただし、皿が右前景の大部分を占め、母屋断片が右上へ広がる。模型と石塔の間にある小さな
背景片もノイズとして読める。大小はあるが、構図が要素間の意味関係を作れていない。

### 14.2 Visual Floating

石塔は左端に独立し、模型・皿と視覚的に接続しない。母屋の屋根断片はさらに宙に浮いて見える。
**Observed problem:** `visually_floating`, `poor_visual_connection`, `isolated_layer`。

**Likely root cause:** Composition (Medium) に、母屋のfragmentation (High) が重なったもの。
正常なLayer同士が適度に重なるべきかという審美判断は、単一runから確定できない。

### 14.3 Occlusion

皿は前面 (`layerIndex=3`) で模型の右側を覆うが、蛙・音符は完全に見える。石塔も見える。
模型の主な梁は残るため、重要部分の完全な埋没はない。一方で、母屋Layerの意味は他Layerに
隠れたからではなく、抽出時点で失われている。

### 14.4 Overall Unity

色・題材は金沢旅行として整合するが、視覚的には「独立した切り抜き4枚」の配置にとどまる。
作品としての統一性は△である。

## 15. Geometry / Contract Integrity

| Check | 結果 | Evidence |
|---|---|---|
| exactly 4 layers | ○ | `artwork.json` の4件 |
| 5 source photos | ○ | `artwork.json` の5件 |
| 2L aspect ratio | ○ | `1.4015748031496063 = 178 / 127` |
| `layerIndex` | ○ | 重複なしの `0,1,2,3` |
| source / asset reference | ○ | 全Layerの `sourcePhotoId` は5 source内、manifestは9 assetを解決 |
| asset metadata | ○ | 宣言と実寸が全4 layerで一致: 2122×1331, 3280×1485, 291×862, 2807×2512 |
| RGBA / transparency | ○ | 全4件がRGBA、alpha=0 pixelあり |
| Canvas outside | ○ | asset縦横比込みの矩形はすべて `[0,1]` 内。最小余白は皿のright=0.98 |
| label | ○ | 4 labelとも人間が理解できる日本語 |

この表はArtwork Dataの品質であり、画像内容の品質合格を意味しない。

## 16. Failure Stage Analysis

| Observed problem | Likely stage | Likely root cause | Confidence | Evidence |
|---|---|---|---|---|
| 母屋Layerに屋根・木・建屋の離散片 | Segmentation | 複雑で遮蔽されたbbox内から複数の高コントラスト領域をforegroundとして選択 | High | `mask-004.png`; bboxは対象領域に位置するがmaskのみで分離片が生じる |
| 母屋maskがborderに接しcoverage 0.274 | Source / BBox / Segmentation | sourceが遮蔽され、bboxも画像右端を含む広い複合景観 | High | `source-04.png`, `source-04-bbox.png`, `masks/index.json` |
| 母屋が物理Layerとして意味不明 | Semantic / Source / Segmentation | 「庭園と母屋」は孤立objectとして不向きで、抽出結果のfragmentationが増幅 | Medium | `semantic-plan.json`, `layer-b006…png`, composition preview |
| 石塔が孤立して見える | Composition | 小さな左端配置と他Layerとの非重なり | Medium | artwork `x=.15,y=.48,scale=.18`; composition preview |
| 模型の細梁・空隙が多い | Semantic / Physical suitability | 複雑な対象を選んだことによる本質的形状。mask失敗とは断定不可 | Medium | `source-05.png`, `mask-001.png`, layer asset |
| 高scoreでも母屋maskを通過 | Quality assessment | 現gateがhard failだけを判定し、fragmentation / border-touchをreject根拠にしない | High | `quality.py`, `masks/index.json` |

## 17. Improvement Candidates

以下は調査から導いた候補であり、この変更では実装していない。

### 17.1 【確実にやってよい】

| Candidate | Priority | 根拠 |
|---|---|---|
| PoC / debug evidenceにcomponent数、最大component比、small-island面積比、border-touchを**観測metricとして**追加する | P0 | 現在のscoreだけでは `mask-004` の失敗を説明できない。閾値・reject挙動を変えず原因理解を深められる |
| Layerごとのsource→bbox→mask→RGBA→compositionを並べるレビュー表を、Real PoCの標準評価にする | P0 | 今回この追跡でstage帰属が可能になった。画像品質の見落としを減らす |
| “accepted”と“物理Layer適性レビュー済み”をレポート・PoC結果で区別する | P1 | 母屋はacceptedだが作品素材品質は×。既存Quality Gateの意味を誤解しないため |

### 17.2 【検証してから実装】

| Candidate | Priority | 検証が必要な理由 |
|---|---|---|
| fragmentation / border-touch / bboxCoverageを用いたsoft warning又はQuality Gate候補を、複数の代表対象で評価する | P0 | 人物+持ち物など正当な複数componentを誤rejectしない検証が必要 |
| Semantic選定時に「独立Layer identity」「単純なsilhouette」「物理形状リスク」を評価軸として候補をrankする | P0 | 旅行らしさとのトレードオフがあり、Prompt変更前に複数ケースで確認が必要 |
| source photoの候補間で、遮蔽・対象サイズ・背景分離を比較して選ぶ | P1 | 同一対象の代替sourceが十分存在するデータでの再現確認が必要 |
| bboxを対象componentへ狭める/複数componentを許容する方針を比較する | P1 | 母屋のような景観と、模型のような複雑だが正当な対象を分けて評価する必要がある |
| EfficientSAM-TiとSAM 2.1を、bboxが妥当なのにmaskが悪い複数ケースで比較する | P1 | 単一の母屋caseではmodel変更の費用対効果を断定できない |
| 関係性・重なり・主従を構図評価に入れる | P1 | 単発の美的評価を固定ruleにしないため、複数作品で確認が必要 |

### 17.3 【現時点ではやらない】

- SAM 2.1への全面移行、又はP0主経路の自動fallback化。
- largest component以外を無条件に削除する後処理。
- bboxの一律拡張・一律縮小。
- morphologyを常時適用すること。
- `mask_score`、面積、thinnessの固定reject閾値を決めること。
- 製造上のmm閾値をArtwork DataやAI Pipelineへ固定すること。
- 「浮いて見える」ことだけを理由に強制的な中央寄せ・重なりを決めること。

いずれも、正常な複数component・細部を持つLayerを壊す、又はPhysical Output PoCの領域を
先取りする証拠不足のためである。

## 18. Priority

### P0

1. fragmentation等を**観測**し、複数の実写真で「高scoreだが素材として×」の頻度を把握する。
2. Semantic / source選定に、単体Layer identityと物理化リスクを入れる価値を検証する。
3. その結果を用いて母屋型の失敗をwarning / rejectする条件を検証する。

### P1

1. bboxとsourceの選択を複数候補で比較する。
2. bboxが妥当でmaskだけが継続して悪い対象でSAM 2.1比較を行う。
3. 構図の視覚的接続・主従を複数例で評価する。

### P2

1. 物理出力PoC結果に基づくthin structure / holeの数値化。
2. 前景の皿の見せ方などの作品上のpolish。

## 19. Recommended Next Step

次の実装フェーズへ進む前に、以下の順で**調査・検証**する。

1. 10–20対象の既存PoC計画に、component / island / border-touch / bboxCoverageの観測列と
   人手の素材品質評価（A/B/C）を追加する。閾値や挙動はまだ変更しない。
2. 「景観全体」「遮蔽された建物」「細い構造」「単純な皿」「人物+持ち物」を含む複数例で、
   Semantic選定・source選定・mask失敗の境界を分ける。
3. bboxが適切で失敗する症例が継続すると確認できた場合に限り、EfficientSAMとSAM 2.1を
   同一artifactで比較する。
4. 比較結果を根拠に、まずwarningかrejectか、次に後処理かmodel比較かを決める。

## 20. Unknowns / Additional Evidence Needed

- 1成功runだけでは、母屋型のfailureが再現的か、同run固有かは不明。
- memoryTextがcandidateの優先順位をどれだけ変えたかは、同写真・異なるtextの対照runなしには
  判定できない。
- source-01（昼の庭園）が最終4Layerに採用されなかったことの妥当性は、本人の希望や候補比較
  なしには判定できない。
- 物理的に許容できる最小幅、穴、component分離の数値は実機PoCが必要である。
- current branchに対するopen PRの有無は、実行環境のnetwork制限で未確認である。

## 21. Additional Runs Performed

**なし。** 主対象bundleは入力5枚、Semantic Plan、全5 source preview、全5 bbox preview、
4 mask preview、4 RGBA Layer、composition preview、metrics、Artwork、Manifestを持つため、
今回の品質判断とstage帰属に必要な証拠は既存Artifactだけで足りた。

追加のReal Gemini API呼出しやPipeline実行は、同じ判断材料を増やすだけになり、個人写真の
不要な処理とAPI消費を伴うため行っていない。
