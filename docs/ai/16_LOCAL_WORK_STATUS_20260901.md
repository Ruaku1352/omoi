# AIローカル作業状況と残タスク（2026-09-01）

## 状態と判定ルール

これはローカルRepositoryとGitHub PRを照合した時点の引継ぎ資料である。

> **PRが作成されていない作業は、commit済み・push済みでも未完了として扱う。**

そのため、この資料では「コードがある」「検証済み」「PR提出済み」「mainへ反映済み」を分けて
記載する。未PRの変更を、プロダクトへ反映済み・完了済みとは扱わない。

## 1. 現行Cloud Run基準（速度検討の正本）

以下は詳細Performance Logを有効にしたCloud Runの最新実測であり、ローカルの過去設定や単発PoCより
優先する。

| 項目 | 現在の値 |
| --- | --- |
| Real AI | Gemini + EfficientSAM-Ti ONNX Runtime CPU |
| Cloud Run | CPU 1 / Memory 2 GiB / Concurrency 1 / timeout 600秒 |
| Gemini model | `gemini-3.5-flash-lite` |
| 入力 / 出力 | 写真5枚 + memoryText → 4 Layer |
| 実測入力 | 長辺3600px、quality 95、合計約12 MB |
| 結果 | 4 Layer生成成功、Contract validation OK、request全体約4分10秒、`ai.total=234.5秒` |

### 1.1 詳細Performance Logの実測内訳

| Stage | 実測 | 読み方 |
| --- | ---: | --- |
| ONNX inference | 114.4秒 / 11回（平均約10.4秒） | 最大のボトルネック。resize等ではなく`session.run(...)`本体が支配的。 |
| RGBA Layer生成 | 53.4秒 / 5回（1.9〜10.0秒） | 大きなばらつきがあり、原因未調査。 |
| Mask Quality Check | 28.3秒 / 22回 | candidate / componentの品質確認コスト。 |
| Semantic Planning | 27.7秒 | Gemini入力準備18.5秒、Gemini API 9.2秒。入力準備の方が重い。 |
| Composition | 6.6秒 | Gemini構図・正規化等を含む。 |
| input decode | 1.1秒 | 主因ではない。 |
| EfficientSAM周辺処理 | 約1.4秒 | resize / tensor準備 / mask復元の合計。推論本体と区別する。 |

candidate 12件のうち`c_07` / `c_08` / `c_09`は、各10〜12秒の処理後にcombined Mask Quality
Checkで不採用となった。最終作品に使われないcandidateへ約33秒を使っているが、これだけを理由に
early reject・candidate数削減・Quality Gate変更を行わない。品質を固定datasetと人手A/B/Cで
確認してから判断する。

元画像の単純縮小は、Backend解析画像を最大辺1536pxへ縮小する現行経路では`ai.total`を大きく
短縮しない。一方、Frontend側のresizeはCloud RunのRequest Size上限対策として必要である。
実際に5枚合計34 MBで32 MB上限を超え、413となった事例がある。

## 2. ローカル構成

| Worktree | Branch / HEAD | 状態 |
| --- | --- | --- |
| Repository root | `feat/ai-general-micro-island-cleanup` | **唯一の登録worktree**。以後のAI作業はこのDirectoryで行う。PR未作成。 |
| `tmp/ab-candidate` | なし | worktree登録・Directoryとも解消済み。 |
| `tmp/ab-parent` | なし | worktree登録は解消済み。`.pytest_cache`のアクセス拒否により、古い比較用ファイルコピーが残留している。作業には使わない。 |

作業ツリーに未commitのソース変更はない。`poc-images/`、`poc-output/`、`tmp/` 配下の写真・
生成artifact・比較worktreeはprivateな評価材料であり、commit対象ではない。

### ブランチの重要な注意

`feat/ai-general-micro-island-cleanup` は、計測時点で `origin/main` より**30 commits behind**である。
未PRのdocs / feature commitを積んでいるためahead数は更新ごとに増えるが、このままPRを作ると、
main側の無関係な差分を含み、競合やレビュー負荷が増える。rootを通常作業場所に戻したことは、
この古い混在branchをそのままPRにすることを意味しない。

PR前には最新`origin/main`を起点に、root上で責務ごとの新branchを作り、必要なcommitだけを
cherry-pickする。順序はdocs、format、微小island品質改善、以後の品質PoCの順とし、速度変更は
品質評価が終わるまで別branchへ置く。

### 2.1 tmp残留copyの扱い

`tmp/ab-parent`は既にGit worktreeではない。Directory削除は`.pytest_cache`へのアクセス拒否で停止した。
中身を再利用せず、root作業に影響しないことを確認済みである。テスト関連processを終了できる時点で、
この**明示的な絶対pathだけ**を削除する。`tmp/`全体や評価artifactは削除しない。

## 3. main反映済みだが、PR未作成のため未完了として扱うもの

| 項目 | 根拠 | 状態 |
| --- | --- | --- |
| physical-ready Layer生成 | `cedb1a6` は `origin/main` のancestor。ただしPR #1〜#3のcommit一覧に含まれない。 | コードはmain反映済みだが、**PR未作成のため未完了** |
| architecture Layer抽出改善 | `43b0e4f` は `origin/main` のancestor。ただしPR #1〜#3のcommit一覧に含まれない。 | コードはmain反映済みだが、**PR未作成のため未完了** |
| architecture A/B比較 | 既存private A/Bには改善の示唆がある。現行Cloud Run・固定dataset・人手評価を含む再確認は未了。 | **再評価がP0** |

Architectureの改善内容は、建築本体を優先候補として残し、微小な孤立成分だけを安全に除去するもの。
しかし、PR提出を完了条件とする以上、この履歴はプロセス上未完了である。すでにmainにコードが
あるため、新PRで同じ変更を再提出するのではなく、PRなしでmainへ入った経緯の扱いを公開チャンネルで
整理する必要がある。

## 4. PR提出済みだが、状態確認・整理が必要なもの

| 項目 | Branch / PR | 現在の観測 | 次アクション |
| --- | --- | --- | --- |
| 詳細Performance Timing Log | `chore/ai-performance-timing`, [PR #3](https://github.com/Ruaku1352/omoi/pull/3) | OPEN、base=`feat/ai-mvp-5photos-4layers`、merge state=`CLEAN`、GitHub上のcheck表示なし。commit `7695698` 自体は`origin/main`のancestor。Cloud Runで上記234.5秒の詳細実測を取得済み。 | PR #3がmainへ既に取り込まれた状態と整合しないため、担当者がPRをclose/mergeして状態を解消する。新しい性能改善はこのPRへ混ぜない。 |

PR #3は「PR未作成」ではない。ただしopenのままなので、レビュー・マージ記録としては未整理である。

## 5. 未完了（PR未作成）のローカル変更

### 5.1 Ruff整形

| Commit | 内容 | 検証 | 未完了理由 |
| --- | --- | --- | --- |
| `21e3938 chore(ai): format backend sources` | Backendの機械的format | 当時Backend test 50 passed、Backend ruff check / format check通過 | PR未作成 |

この整形commitは画像品質の変更と混ぜない。必要なら単独の`chore` PRとしてmain最新から提出する。

### 5.2 一般subjectの微小飛び地除去

| Commit | 内容 | 検証済み | 未完了理由 |
| --- | --- | --- | --- |
| `4189159 feat(ai): retain masks with micro islands` | `single_form`相当のsubjectで、主成分以外の合計が暫定0.5%以下なら削除して採用する。設定は `MASK_MICRO_ISLAND_MAX_AREA_RATIO`。 | Backend tests 51 passed、Backend ruff check / format check、Contract validation。金沢で人物候補の飛び地0.4788%を除去して採用。 | PR未作成。main最新への積み直しと再検証が必要。 |

この変更は、元写真にない画素の生成・Maskの橋渡し・物理出力の判断を行わない。3%以上の意味ある
分離候補を無条件に採用する変更でもない。

### 5.3 共通Layer抽出設計資料

| Commit | 内容 | 未完了理由 |
| --- | --- | --- |
| `a8234f1 docs(ai): propose common layer extraction design` | [共通Layer抽出設計案](15_COMMON_LAYER_EXTRACTION_DESIGN.md)。料理専用処理を追加せず、`single_form` / `coherent_group` / `scene_anchor` を提案。 | PR未作成。設計提案のみで、実装着手・採否決定は未了。 |

この資料は、器＋料理、人物＋手持ち物、建物＋一体の付属物を同じ仕組みで扱う案である。Artwork Contract、
API、Physical Outputの製造条件は変更していない。

## 6. 既存physical-ready処理の現状

以下は、建築・背景・浮遊量・連結成分に対して既に存在するAI側の処理である。各項目の
「実装済み」は、要求どおりに解決済み・PR不要という意味ではない。

| 領域 | 現在の挙動 | 有効範囲 | 状態 / 制約 |
| --- | --- | --- | --- |
| 建築向けSemantic処理 | `physical_layer_v3_architecture` は、明確な歴史的建築がある場合に `architecture_primary` として建築本体全体を候補化し、選定時に優先する。`architecture_detail` は分離した非重複の細部だけに限定する。 | `SEMANTIC_PROFILE=physical_layer_v3_architecture` のみ | **main反映済み**。既定Profileは`physical_layer_v2`のため、通常実行で常に有効ではない。建築固有のSegmentation ModelやMask合成はない。 |
| 建築の微小飛び地 | v3の建築roleは、主成分外の合計が0.1%以下なら最大成分だけを残す。 | v3の`architecture_primary` / `architecture_detail` | **main反映済み**。閾値超過の成分を結合・補正しない。 |
| 一般subjectの微小飛び地 | 主成分外の合計が0.5%以下なら削除する。 | `physical_layer_v2` / v3の一般subject | **ローカルcommitのみ、PR未作成**（`4189159`）。mainの既定挙動ではない。 |
| 大きな飛び地 / 意味ある分離 | 閾値を超えた分離成分は残したまま候補を`not_single_component`で不採用にする。 | mainのv2/v3、および未PRの0.5%案 | **「修正」機能は未実装**。Maskを橋渡しせず、無関係な物体を寄せ集めない安全側の挙動。4 Layerに届かなければ生成自体を失敗として返す。 |
| 背景Layer | Geminiは`scene_anchor`を最大2候補まで計画できる。最重要の1件だけを選び、単一bboxの矩形Cropを背景Layerとして使う。 | `physical_layer_v2` / v3 | **main反映済み・既定v2で有効**。幅がCanvasの0.60未満になる候補は不採用。背景が無い場合はprivate診断`background_missing=true`を残すだけで、背景を自動生成・代替しない。 |
| 浮遊Layer管理 | 各Layerの表示矩形下端からCanvas下端までのgapを測る。0.30を超えた場合、Geminiへ1回だけ再構図を要求し、まだ超えるものだけを決定論的に下方へclampする。 | `physical_layer_v2` / v3 | **main反映済み・既定v2で有効**。支柱・土台・接続部を作らず、物理強度も判定しない。透明Alpha形状ではなく、Layer Assetの表示矩形に基づく制約である。 |

### 6.1 建築向け処理の位置づけ

建築向けProfileは、建築本体を「背景の断片」や「屋根だけ」として失わないための**Semantic
Planning / Layer Selection上の優先処理**である。既存private A/Bに改善の示唆はあるが、現行の
優先検証は、固定datasetと人手A/B/Cでarchitecture品質向上・非architecture回帰なしを再確認する
ことである。一般対象を建築専用アルゴリズムで切り抜くものではない。

ただし、既定Profileがv2である以上、建築写真を通常実行しただけではv3の主建築優先が有効に
ならない。どの入力条件でv3を使うか、または将来の共通`extraction_intent`設計へ統合するかは
未決定である。ここを、料理専用・建築専用の後処理を増やす方向で解かない。

### 6.2 大きな飛び地の扱い

「大きな飛び地をきれいに修正する」処理は現状存在しない。これは意図的である。大きな分離は、
背景混入・Mask失敗の場合もあれば、人物＋持ち物や器＋料理のような意味ある複数要素の場合もある。
面積閾値だけで削除・結合すると、どちらかを必ず壊す。

現行は以下の安全側の挙動である。

1. 微小ノイズだけを削除できる設定値以内で除去する。
2. 超過する分離は候補を不採用にし、次候補を試す。
3. 十分なLayer数に届かなければ、Mockで埋めず明示的に生成失敗にする。

器＋料理のように大きな複数要素を一Layerとして残す改善は、`15_COMMON_LAYER_EXTRACTION_DESIGN.md`
の`coherent_group`で扱う未実装項目である。componentを意味的に宣言して個別Maskをunionし、
必須component保持を検証してから採否を決める。単なる大きな飛び地修正ではない。

### 6.3 背景と浮遊量の未解決点

背景は、`scene_anchor`が計画・選定できた場合だけ設定される。`background_missing`は公開Response
へ出ず、現状は作品生成を失敗にも再計画にもしていない。「背景らしいLayerがなければ無しでもよい」
という許容を持つ一方、背景を必ず成立させる保証はない。

浮遊量の0.30は【PoC後FIX】のAI構図上の暫定値で、物理的に許容できるgapを表すmm値ではない。
下方clampにより画像上の位置は修正できるが、Layer間の実接続、支柱の必要性、印刷後に立つかどうかは
Physical Outputの責務である。さらに現在のgapはAsset外接矩形で測るため、Alpha形状の実際の下端との
ずれは未評価である。

### 6.4 この領域の残タスク

1. 一般subjectの0.5%微小飛び地修正をmain最新へ積み直し、PRとして提出する。
2. v3建築Profileを使う入力条件を固定datasetで評価する。通常v2への無条件統合はしない。
3. 背景なしを許容する条件と、`scene_anchor`を優先する条件を作品評価で確認する。
4. Asset外接矩形gapとAlpha形状の見た目の差をprivate診断で観測する。製造閾値は決めない。
5. `coherent_group` PoCで、大きく分離したが意味的に一まとまりな対象を一般化して扱えるか検証する。

## 7. Gemini modelと3.5 Flash Lite検証の現状

| 項目 | 事実 | 判定 |
| --- | --- | --- |
| 現行Cloud Run | `gemini-3.5-flash-lite`、5写真から4 Layer生成・Contract validation成功を実測 | **Runtimeの現行基準** |
| 詳細Performance Log | 3.5 Flash LiteでSemantic / Compositionを含む234.5秒の`ai.total`を取得 | 実測済み |
| 過去のローカル`backend/.env` | 一時点で`gemini-3.7-flash`を確認 | Cloud Runの現行設定を表すものではない履歴 |
| 過去の金沢評価のModel表記 | 実行設定の証拠に基づかない3.5 Flash Lite表記を3.7 Flashへ訂正した | private artifactの履歴訂正済み |
| ローカル3.5 Flash Lite試行 | Semantic Planning成功後、E2E artifactが不完全に終了した | ローカルrunnerのfailure記録改善課題。Cloud Runの4 Layer成功を否定しない |

以後のモデル比較は、Cloud Runで実効modelをartifact / logに残し、同じ入力・candidate数・
Profileで品質とlatencyを比較する。3.7と3.5を、異なる処理内容・写真数で単純比較しない。
ローカルquality runnerは異常終了時の終了状態をartifactへ必ず残せていないため、比較実験の
再現性を上げる改善対象である。ただし、これはCloud Runで確認済みの3.5 Flash Lite・4 Layer成功を
否定するものではない。

## 8. 未実装の設計改善

`15_COMMON_LAYER_EXTRACTION_DESIGN.md` は提案であり、以下はまだコード化していない。

1. 内部Semantic Planの `extraction_intent` とcomponent関係。
2. `coherent_group` のcomponent別bbox → Mask → union。
3. 必須component保持・背景混入を確認する共通Quality Check。
4. GeminiによるLayer内容Verificationと、上限1回のcomponent再計画。
5. 多様な固定datasetでの匿名A/B評価。

料理の「皿だけが残り、料理が抜ける」問題は、この未実装の`coherent_group`で解く対象である。
一般subjectの0.5%微小飛び地除去だけでは解決しない。

## 9. 推奨する実施順序

### P0 — 品質改善を先に完了する

1. **評価基準を固定する**: architecture 3ケース以上、非architecture 3ケース以上、料理/器・人物・
   背景あり/なしを含むprivate datasetを固定する。各caseで残す対象・除外背景・A/B/C rubricを
   実行前に記録する。
2. **architectureを再評価する**: `cedb1a6`と`43b0e4f`を、現行Cloud Runの5写真・4 Layer・
   3.5 Flash Lite条件で比較する。Semantic / Source / BBox / Mask / Layer / Compositionを匿名化して
   人手評価し、建築改善と非architecture回帰なしを確認する。
3. **微小island改善を評価する**: `4189159`は閾値に合わせた採用ではなく、人物・小物・料理を
   含む固定datasetで主成分保持・背景混入・4 Layer到達率を比較する。品質が確認できた場合だけ
   main最新から独立PRにする。
4. **料理/器の課題をPoC化する**: `coherent_group`は、まずSemantic Planのcomponent関係を
   人手レビューし、その後bbox別Mask unionをA/Bする。料理専用後処理や大きな飛び地の強制結合はしない。
5. **背景・浮遊Layerを品質評価する**: 背景なしが許容される場合と、`scene_anchor`を選ぶべき場合を
   作品として評価する。0.30 gapは物理強度ではなく構図制約として扱う。

この段階ではcandidate数、Quality Gate、Semantic Prompt、Segmentation条件を速度目的で変更しない。
品質を変える実験は必ず同じ入力条件で最終作品を人手A/B/C評価する。

### P1 — 品質変更をPR単位へ分離する

1. root上で最新`origin/main`からdocs-only branchを作り、設計・台帳資料をPRにする。
2. `21e3938`のformatはdocs・品質変更から分け、単独`chore` PRとして扱う。
3. P0の評価を通過した`4189159`だけを新branchへcherry-pickし、test / lint / format / Contract validation /
   fixed dataset evidenceを添えてPRにする。
4. `coherent_group`など次の品質PoCは、前のPRの採否後に新branchで始める。

### 運用P0 — PRとブランチを整理する

1. PR #3のopen状態とmain反映済みcommitの関係を解消する。
2. root以外の比較worktreeを新たに作らない。比較が必要な場合も、rootでbranchを切り替えるか、
   事前にartifactを出してから一時worktreeを明示的に作成・解消する。
3. `tmp/ab-parent`の残留copyは、ロック解除後に明示pathだけを削除する。

### P2 — 速度改善を品質ベースラインの後に行う

1. **CPU 1 → CPU 2**: ONNX inferenceの短縮量を同一入力・同一candidate数・同一Profileで測る。
   AIの選定・Mask・Quality Gateを変えないため、最初に試す速度改善候補とする。
2. **RGBA Layerばらつき**: 1.9〜10.0秒の差をasset寸法、alpha面積、crop、PNG encode等に分解して
   観測する。原因を確認するまで最適化しない。
3. **Semantic入力準備**: 18.5秒をthumbnail / PNG変換等へ分解して観測する。元写真resizeは
   Request Size上限対策として維持し、AI速度改善と混同しない。
4. **rejected candidate / candidate数**: 約33秒の未採用処理を短縮できる可能性があるが、P0の
   固定品質datasetで回帰なしを確認した後だけearly reject・候補数変更をA/Bする。

P2でも、速度だけを理由にcandidate数、Quality Gate、Semantic Prompt、Segmentation条件を変更しない。
技術指標と最終作品の人手A/B/Cを両方満たしたものだけをPRにする。

### 並行事項 — 非同期化の責任境界を維持する

4分規模の公開処理を同期HTTPで待たせない方針である。Backend担当が次の候補を検討中であり、
AI担当は既存の生成Function境界・最終Artwork Contract・詳細stage logを維持する。

| 領域 | 方針 / 候補 | 担当境界 |
| --- | --- | --- |
| Generate API | `POST /api/v1/artworks/generate` → `202 + jobId` | BackendがAPI / Job状態を設計する。Contract変更は公開合意が必要。 |
| 進捗取得 | Frontendがjobをpolling | Frontend / Backend領域。 |
| Job実行 | Firestore、Cloud Tasks + 同一Cloud Run worker Endpoint候補 | Backend / GCP領域。AI担当は独自workerやqueueを先回りで作らない。 |
| Asset保存 | GCS候補 | Backend領域。AIは`GenerationResult`のassetを返す境界を維持する。 |

## 10. 今回行わないこと

- 未PRのlocal commitを「完了」と扱うこと。
- 異なる写真数・candidate数・Profileの速度を、モデルや画像縮小だけの差として比較すること。
- 料理専用のMask後処理や、Maskの橋渡しを追加すること。
- Physical Outputの支柱・STL・実寸閾値をAI側で決めること。
- 評価画像の結果だけに合わせてPrompt・閾値を調整すること。
