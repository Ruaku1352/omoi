# Codex調査プロンプト：現状Artwork出力の品質ギャップ分析

あなたは Tornado 2026 Team G「omoi = Our Memories, One Image」のAI・画像処理担当として、**現在のReal AI出力を実際に調査し、ArtworkData生成における品質改善点を洗い出す**。

今回は改善実装を行うタスクではない。

目的は、

> 現在の生成結果が、omoiのArtworkとして何を満たしていて、何が足りていないのか

を、実際の生成Artifactを根拠に明らかにすることである。

その結果をMarkdownレポートとしてRepositoryへ残す。

---

# 0. 今回の最重要ルール

今回は、

**調査 → 評価 → 原因候補の特定 → 改善項目の洗い出し**

まで。

原則として以下は行わない。

- AI Pipelineの品質改善実装
- Prompt変更
- Quality Gate閾値変更
- Mask post-processing追加
- EfficientSAM変更
- SAM 2.1導入
- Gemini Model変更
- Compositionロジック変更
- Contract変更
- Cloud/GCP変更
- Frontend変更

「こう直せそう」という案はレポートへ書いてよいが、実装しない。

まず現状を理解することを優先する。

ただし、**既存Artifactだけでは品質判断に必要な証拠が不足する場合、調査目的に限定した部分実行・追加生成を行ってよい。**

この追加実行は「改善実装」ではなく、**現状のPipelineがどのような出力をするかを確認するための観測・再現実験**として扱う。

詳細は後述の「追加実行ルール」に従うこと。

---

# 1. 最初にRepositoryの現在状態を確認する

Repository:

https://github.com/Ruaku1352/omoi

最初に必ず確認する。

- current branch
- main
- open PR
- working tree
- `backend/ai/*`
- `contracts/*`
- `docs/archive/ai-research/ai/*`
- `scripts/*`
- AI tests
- PoC output
- Frontend handoff bundle

特に、現在のMVP品質改善が含まれているbranch / PR #2周辺の状態を確認する。

既存情報を想像で補わない。

---

# 2. 実際のReal生成結果を探す

まず、現在手元に存在する**最新かつ代表的なReal AI生成結果**を特定する。

既知の候補として、

```text
poc-output/final-mvp/frontend-debug-bundle-20260826-122150/
```

があるが、存在を確認してから使用すること。

存在しない場合は、

- `poc-output/`
- debug bundle
- Real AI result
- metrics
- composition preview
- source preview
- bbox preview
- mask preview
- layer preview

等から最新のReal生成Artifactを探す。

Mock結果をReal結果として評価してはいけない。

複数のReal生成結果が存在する場合は、

1. 最新
2. MVP条件を満たす
3. debug evidenceが多い

ものを主評価対象とする。

必要に応じて過去runも比較対象として使う。

---

# 3. MVP前提

今回評価する代表MVPは、

```text
Input:
exactly 5 photos
+ non-empty memoryText

Output:
exactly 4 layers

Canvas:
2L Landscape
178 mm × 127 mm
aspectRatio = 178 / 127
```

である。

Shared Contract自体の配列長は可変であるため、
Contractを5枚/4Layer固定へ変更する話ではない。

---

# 4. ArtworkDataに求める品質要件

現在の出力を、以下の観点ですべて評価する。

---

## A. 思い出理解

- 5枚を別々の写真ではなく、1つの思い出として理解できているか
- memoryTextが主要信号として反映されているか
- 写真上で目立つだけの対象に引っ張られていないか
- 本人が残したいと思う象徴要素になっているか
- 写真に存在しない対象を捏造していないか

---

## B. 4要素の選択

- 4Layerそれぞれに意味があるか
- 意味が重複していないか
- 4つを並べたときに思い出全体を表現できているか
- 同カテゴリへ偏りすぎていないか
- 主役と補助的要素が存在するか
- Layer化したとき意味不明になる対象を選んでいないか
- 二値Maskと極端に相性の悪い対象を不必要に選んでいないか

---

## C. Source Photo選択

同じ対象が複数写真に存在する場合、

- 十分大きく写っているか
- 対象が欠けていないか
- 遮蔽が少ないか
- 背景と分離しやすいか
- 画質が良いか
- 他対象との重なりが少ないか
- Layerとして使ったときに見栄えがよいか

を確認する。

Semantic上正しい対象を選べていても、
Source Photo選択が悪ければ別のfailureとして扱う。

---

## D. BBox

- 対象全体を含んでいるか
- 頭・足・屋根等を切っていないか
- 余計な背景を含みすぎていないか
- 隣接対象を巻き込みすぎていないか
- 細長い対象でも適切か
- component単位で妥当か

を実際のbbox previewで確認する。

---

## E. Segmentation / Mask

- 対象本体が欠けていないか
- 背景混入がないか
- 隣接対象を巻き込んでいないか
- 不要な飛び地がないか
- 不自然な穴がないか
- 細い構造を失いすぎていないか
- 境界が過度に粗くないか
- 対象外領域が残っていないか

をmask previewとsource imageの両方から確認する。

---

## F. RGBA Layer品質

- 背景が正しく透明か
- 対象の色・質感が維持されているか
- 不要な透明余白が過大ではないか
- 対象が途中で切れていないか
- PNGとして自然な独立Layerになっているか
- 単体で見たとき「何なのか」が分かるか

---

# 5. 物理Layerとしての品質

omoiは最終的に**物理レイヤーアート**へ変換する。

そのため、単なる画像としての正しさとは別に、
「1枚の物理Layerとして成立するか」を必ず評価する。

---

## G. Fragmentation / 島

透過Layer内について、

- 本体から離れた小さな島が点々としていないか
- 意味のない背景片が孤立して残っていないか
- 小componentが大量発生していないか
- 離れたcomponentそれぞれに意味があるか
- 1枚のLayerとして視覚的にまとまっているか

を見る。

重要:

```text
connected components > 1
```

だけを問題としてはいけない。

人物+持ち物、木、複数人物等、
正当に複数componentになるケースがある。

評価すべきなのは、

> その分離に意味があるか

である。

---

## H. Thin Structure / Fragility

画像を見て、

- 極端に細い線だけの領域
- 細い橋だけで大きな領域がつながる形
- 毛髪・枝・柵等の過度に細かい構造
- 小さすぎる突起
- 非常に複雑な輪郭
- 細かい穴の大量発生

が目立たないか確認する。

ただし、

```text
何mm以下NG
```

等の製造閾値は今回FIXしない。

Physical Outputの実機PoCが必要なためである。

今回は**明らかに物理化しづらそうな形状を発見・記録するだけ**とする。

---

## I. Layer Identity

1Layer単体で見たとき、

- 何のLayerか理解できるか
- 重要な特徴が残っているか
- 小さな背景片の集合になっていないか
- 物理化しても意味が伝わりそうか

を評価する。

---

# 6. Composition品質

最終composition previewを必ず確認する。

---

## J. Layout

- 4Layerすべて視認できるか
- 主役が分かるか
- 重要度に応じたサイズ差があるか
- 全Layerが同じ大きさではないか
- 単純な横並びになっていないか
- 不自然に四隅へ配置されていないか
- 適切な重なりがあるか
- 余白が不自然ではないか

---

## K. 「浮いて見える」問題

物理レイヤー作品として、

- 切り抜いたオブジェクトを単に置いただけに見えないか
- Layer同士が過度に離れていないか
- Canvas中央に単独で浮いている対象がないか
- 他要素との視覚的関係が存在するか
- 適度な重なりで一つの作品としてつながっているか
- 全Layerが宙に浮いている印象になっていないか

を確認する。

failure候補として、

```text
visually_floating
poor_visual_connection
isolated_layer
```

等を使ってよい。

---

## L. Occlusion

- 重要なLayerが他Layerに隠れすぎていないか
- 顔や象徴的部分を隠していないか
- 小Layerが完全に埋もれていないか
- 4Layer存在するのに2〜3Layerにしか見えない状態でないか

を確認する。

---

# 7. Geometry / ArtworkData integrity

以下についても確認する。

- exactly 4 layers
- Canvas aspectRatio = 178 / 127
- LayerがCanvas外へ出ていない
- x / y / scaleが妥当
- layerIndexが0..3
- layerIndex重複なし
- Source Photo参照が正しい
- Asset参照が正しい
- widthPx / heightPxと実画像が一致
- Artwork / Asset Manifestに参照漏れがない
- labelが人間に理解可能

ここは作品品質と区別して、
データ整合性として評価する。

---

# 8. 実際の画像を必ず見る

JSONだけ見て評価してはいけない。

最低限、

```text
source photo
bbox preview
mask preview
RGBA layer preview
composition preview
```

を目視する。

可能なら、

```text
source
→ bbox
→ mask
→ layer
→ final composition
```

をLayerごとに追跡する。

---

# 9. Layer単位で評価する

4Layerそれぞれについて表を作る。

例:

| Layer | Semantic | Source | BBox | Mask | Physical shape | Composition | Overall |
|---|---|---|---|---|---|---|---|
| 漆皿 | ○ | ○ | ○ | ○ | ○ | △ | ○ |
| 石塔 | ○ | ○ | △ | △ | △ | ○ | △ |

評価値は、

```text
○ 問題なし
△ 改善余地あり
× 明確な問題
? 判断材料不足
```

とする。

---

# 10. 問題をStageへ帰属する

問題を見つけたら、

単に

```text
品質が悪い
```

と書かない。

例えば、

```text
Observed:
屋根の右側に小さな背景片が島として残る

Likely stage:
Segmentation

Evidence:
bbox自体には対象全体が適切に含まれている
sourceにも背景片との明確な境界が存在する
EfficientSAM maskでのみ飛び地が発生

Confidence:
High
```

のようにする。

候補Stage:

```text
Semantic
Source
BBox
Segmentation
RGBA build
Composition
Geometry
Contract / assembly
Unknown
```

---

# 11. 「症状」と「原因候補」を分ける

必ず、

```text
Observed problem
Likely root cause
Confidence
```

を分ける。

画像だけで原因が断定できない場合は、

```text
Likely
Possible
Unknown
```

と明記する。

推測を事実として書かない。

---

# 12. 改善項目を洗い出す

調査結果から改善項目を作る。

ただし、改善項目は以下の3分類にする。

---

## 【確実にやってよい】

現状の証拠だけで、

- 品質悪化リスクが低い
- 必要性が明確
- 原因理解を深める
- 明らかな不具合を直す

もの。

---

## 【検証してから実装】

有力だが、

- 他の正常ケースを壊す可能性
- Threshold決定が必要
- Model比較が必要
- 複数ケースで再現性確認が必要

なもの。

---

## 【現時点ではやらない】

証拠が不足しているもの。

例えば、

- SAM 2.1へ全面移行
- largest component以外を無条件削除
- bbox一律拡張/縮小
- 強いQuality Gate閾値FIX
- morphology常時適用

等。

---

# 13. Priorityを付ける

改善候補を、

```text
P0
P1
P2
```

へ分類する。

基準:

## P0

- ユーザーが一目で気づく品質問題
- 物理Layer化に直接影響する問題
- 高頻度または重大
- 次の品質改善判断を妨げる問題

## P1

- 明確な改善余地
- 実用性を高める
- ただしP0ほど致命的ではない

## P2

- Polish
- 将来的改善
- 現時点ではMVPを阻害しない

---

# 14. 出力レポート

以下へMarkdownとして保存する。

```text
docs/archive/ai-research/ai/13_ARTWORK_OUTPUT_QUALITY_GAP_REPORT.md
```

既に同名ファイルが存在する場合は内容を確認し、
今回の調査との関係を判断して安全に更新する。

---

# 15. レポート構成

最低限以下を含める。

```markdown
# Artwork Output Quality Gap Report

## 1. Executive Summary

## 2. Scope / Reviewed Artifacts

## 3. Current MVP Output

## 4. Functional Requirements

## 5. Requirement Gap Matrix

## 6. Overall Artwork Review

## 7. Per-Layer Review

## 8. Semantic Review

## 9. Source Photo Review

## 10. BBox Review

## 11. Segmentation / Mask Review

## 12. RGBA Layer Review

## 13. Physical Layer Suitability

### 13.1 Fragmentation / Islands
### 13.2 Thin Structures
### 13.3 Holes / Complex Contours
### 13.4 Layer Identity

## 14. Composition Review

### 14.1 Layout
### 14.2 Visual Floating
### 14.3 Occlusion
### 14.4 Overall Unity

## 15. Geometry / Contract Integrity

## 16. Failure Stage Analysis

## 17. Improvement Candidates

### 17.1 【確実にやってよい】
### 17.2 【検証してから実装】
### 17.3 【現時点ではやらない】

## 18. Priority

### P0
### P1
### P2

## 19. Recommended Next Step

## 20. Unknowns / Additional Evidence Needed

## 21. Additional Runs Performed
```

---

# 16. Evidenceを必ず残す

レポート内の重要な指摘には、

- file path
- asset filename
- candidate / label
- metric
- preview path
- log
- JSON field
- 追加実行した場合はrun条件とoutput path

等、追跡可能な根拠を書く。

例:

```text
Evidence:
poc-output/.../debug/layer-previews/03.png
poc-output/.../debug/mask-previews/03.png
```

「見た感じ悪い」で終わらせない。

---

# 17. 数値化できるものは数値も確認する

既存metricsから、

- Semantic time
- Segmentation time
- Layer build time
- Composition time
- total
- Mask score
- area ratio
- Canvas outside ratio

等が取得できる場合は利用する。

ただし今回の主目的は速度ではなく品質である。

---

# 18. 判断材料が不足する場合の追加実行ルール

既存Artifactだけで十分に判断できる場合は、追加実行を行わない。

一方で、以下のような場合は、**調査に必要な範囲で部分的な実行またはReal生成を行ってよい。**

例:

- bbox previewが存在せず、BBox品質を評価できない
- MaskとRGBA Layerの対応が分からない
- ある問題が再現するか判断できない
- Source選択とSegmentationのどちらが原因か切り分けられない
- Compositionだけを再確認したい
- 既存runが古く、現在branchの出力を代表していない
- 1つのArtifactだけでは偶然の失敗か判断できない

この場合、**最小限の追加実行で必要な証拠だけを増やす**。

---

## 18.1 部分実行を優先する

Pipeline全体を毎回Real E2Eで回す必要はない。

必要に応じて、

```text
Semantic Planning only
BBox conversion / preview only
Segmentation only
Mask Quality calculation only
RGBA layer build only
Composition only
Artwork assembly / validation only
```

のような部分実行を利用する。

既存のPoC runner、Fake、observer、保存済みSemantic Plan等を再利用できる場合はそれを優先する。

---

## 18.2 Real API実行が必要な場合

Geminiの実出力自体を確認しないと判断できない場合は、
必要最小限のReal Gemini API実行を行ってよい。

ただし、

- 大量runをしない
- 同じ目的のrunを無意味に繰り返さない
- Mockへsilent fallbackしない
- 実行理由を記録する
- 実行条件を記録する
- outputを追跡可能な場所へ保存する
- どの判断のために実行したかを書く

こと。

---

## 18.3 再現性確認

単発Artifactだけでは判断できない問題については、
同じ入力を少数回再実行してよい。

目的は統計的評価ではなく、

> この症状が偶発か、少なくとも複数回起きる現象か

を確認することである。

必要以上にrun数を増やさない。

---

## 18.4 改善実装は禁止

追加実行の途中で問題原因が分かっても、
その場で修正コードを入れてはいけない。

今回の目的はあくまで、

```text
現状を観測する
↓
問題を特定する
↓
改善候補をレポートする
```

ことである。

---

## 18.5 追加runの記録

追加実行を行った場合はレポートの

```text
## 21. Additional Runs Performed
```

へ、

- 実行目的
- input
- branch / commit
- model / runtime設定
- 実行したstage
- output path
- 結果
- 得られた判断材料
- API call回数（分かる範囲）

を記録する。

---

# 19. Physical Output責務との境界

今回、

```text
飛び地が多い
細すぎる
複雑すぎる
物理Layerとして不自然
```

という問題は指摘してよい。

ただし、

```text
最小幅2mm
穴3mm以下禁止
```

等の製造閾値はFIXしない。

それらはPhysical Output側の実機PoCが必要である。

今回のレポートでは、

**「物理化上リスクがある」**

までをAI側評価とする。

---

# 20. 最後に結論を明確にする

レポートの最後では、

> 現状最も大きな品質ボトルネックは何か

を最大3つまで挙げる。

さらに、

> 次の実装フェーズで最初に何を調べる/直すべきか

を順番付きで提示する。

ただし、
調査結果が特定stageを支持していない場合は、
無理に結論を出さない。

---

# 21. Git

今回変更してよいのは、原則として

```text
docs/archive/ai-research/ai/13_ARTWORK_OUTPUT_QUALITY_GAP_REPORT.md
```

のみ。

調査のために一時ファイルや追加Artifactを生成してよい。

必要なEvidence Artifactは `poc-output/` 等へ保存してよいが、
個人写真・Secret・巨大な一時ファイル・不要なdebug artifactをcommitしない。

既存ユーザー変更を触らない。

レポート完成後、

- 内容を自己レビュー
- git diff確認
- レポートのみcommit
- current quality-improvement branchへpush

まで行ってよい。

commit例:

```text
docs(ai): report current artwork quality gaps
```

新しいPRは作らない。

---

# 22. Stop条件

以下が揃うまで終了しない。

- 実際のReal Artifactを確認した
- Source / BBox / Mask / Layer / Compositionを目視した
- 4Layerを個別評価した
- 物理Layer適性を評価した
- 現状の良い点も書いた
- 明確な問題を列挙した
- 問題をstageへ可能な範囲で帰属した
- 推測と事実を分離した
- 判断材料不足なら必要最小限の追加実行を行った、または実行不要と判断した
- 追加実行した場合、その理由・条件・結果を記録した
- 【確実にやってよい】改善を抽出した
- 【検証してから実装】を分離した
- 【現時点ではやらない】を分離した
- P0/P1/P2を付けた
- 次の実装フェーズへの推奨順序を出した
- MarkdownレポートをRepositoryへ保存した

今回のゴールは、

**品質改善コードを書くことではなく、
「現状のArtworkの何が悪く、次にどこから改善すべきか」を証拠付きで明確にすること。**

判断材料が不足するなら、
必要な範囲で実際にPipelineを動かしてEvidenceを作ること。

ただし、Evidence作成と改善実装を混同しないこと。
