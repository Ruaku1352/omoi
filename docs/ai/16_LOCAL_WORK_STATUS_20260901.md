# AIローカル作業状況と残タスク（2026-09-01）

## 状態と判定ルール

これはローカルRepositoryとGitHub PRを照合した時点の引継ぎ資料である。

> **PRが作成されていない作業は、commit済み・push済みでも未完了として扱う。**

そのため、この資料では「コードがある」「検証済み」「PR提出済み」「mainへ反映済み」を分けて
記載する。未PRの変更を、プロダクトへ反映済み・完了済みとは扱わない。

## 1. ローカル構成

| Worktree | Branch / HEAD | 状態 |
| --- | --- | --- |
| Repository root | `chore/ai-performance-timing` / `7695698` | clean。remote trackingあり。 |
| `tmp/ab-candidate` | `feat/ai-general-micro-island-cleanup` / `a8234f1` | clean。PR未作成。 |
| `tmp/ab-parent` | `cedb1a6` detached | A/B比較用。変更しない。 |

作業ツリーに未commitのソース変更はない。`poc-images/`、`poc-output/`、`tmp/` 配下の写真・
生成artifact・比較worktreeはprivateな評価材料であり、commit対象ではない。

### ブランチの重要な注意

`feat/ai-general-micro-island-cleanup` は `origin/main` と比べて **30 commits behind / 3 commits ahead**
である。このままPRを作ると、main側の無関係な差分を含み、競合やレビュー負荷が増える。

PR前に、最新`origin/main`を起点に変更を積み直す（rebaseまたは新branchへcherry-pick）必要がある。
その際、各commitの責務を分離する。

## 2. 完了済み（main反映を確認）

| 項目 | 根拠 | 状態 |
| --- | --- | --- |
| architecture Layer抽出改善 | `43b0e4f` は `origin/main` のancestor | main反映済み |
| architecture A/B比較 | 親 `cedb1a6` と比較し、architecture 3ケースで改善、非architectureで明確な回帰なしを確認済み | 検証完了 |

Architectureの改善内容は、建築本体を優先候補として残し、微小な孤立成分だけを安全に除去するもの。
この項目に対して新しいPRを作る必要はない。

## 3. PR提出済みだが、状態確認・整理が必要なもの

| 項目 | Branch / PR | 現在の観測 | 次アクション |
| --- | --- | --- | --- |
| 詳細Performance Timing Log | `chore/ai-performance-timing`, [PR #3](https://github.com/Ruaku1352/omoi/pull/3) | OPEN、base=`feat/ai-mvp-5photos-4layers`、merge state=`CLEAN`、GitHub上のcheck表示なし。commit `7695698` 自体は`origin/main`のancestor。 | PR #3がmainへ既に取り込まれた状態と整合しないため、担当者がPRをclose/mergeして状態を解消する。新しい性能改善はこのPRへ混ぜない。 |

PR #3は「PR未作成」ではない。ただしopenのままなので、レビュー・マージ記録としては未整理である。

## 4. 未完了（PR未作成）のローカル変更

### 4.1 Ruff整形

| Commit | 内容 | 検証 | 未完了理由 |
| --- | --- | --- | --- |
| `21e3938 chore(ai): format backend sources` | Backendの機械的format | 当時Backend test 50 passed、Backend ruff check / format check通過 | PR未作成 |

この整形commitは画像品質の変更と混ぜない。必要なら単独の`chore` PRとしてmain最新から提出する。

### 4.2 一般subjectの微小飛び地除去

| Commit | 内容 | 検証済み | 未完了理由 |
| --- | --- | --- | --- |
| `4189159 feat(ai): retain masks with micro islands` | `single_form`相当のsubjectで、主成分以外の合計が暫定0.5%以下なら削除して採用する。設定は `MASK_MICRO_ISLAND_MAX_AREA_RATIO`。 | Backend tests 51 passed、Backend ruff check / format check、Contract validation。金沢で人物候補の飛び地0.4788%を除去して採用。 | PR未作成。main最新への積み直しと再検証が必要。 |

この変更は、元写真にない画素の生成・Maskの橋渡し・物理出力の判断を行わない。3%以上の意味ある
分離候補を無条件に採用する変更でもない。

### 4.3 共通Layer抽出設計資料

| Commit | 内容 | 未完了理由 |
| --- | --- | --- |
| `a8234f1 docs(ai): propose common layer extraction design` | [共通Layer抽出設計案](15_COMMON_LAYER_EXTRACTION_DESIGN.md)。料理専用処理を追加せず、`single_form` / `coherent_group` / `scene_anchor` を提案。 | PR未作成。設計提案のみで、実装着手・採否決定は未了。 |

この資料は、器＋料理、人物＋手持ち物、建物＋一体の付属物を同じ仕組みで扱う案である。Artwork Contract、
API、Physical Outputの製造条件は変更していない。

## 5. 3.5 Flash Lite検証の現状

| 項目 | 事実 | 判定 |
| --- | --- | --- |
| 主作業ツリーの実効Model | `backend/.env` から `GEMINI_MODEL=gemini-3.7-flash` を確認 | 3.7 Flashを使用中 |
| 過去の金沢評価のModel表記 | 一時的に3.5 Flash Liteと記載したが、実行設定の証拠がなく、3.7 Flashへ訂正 | 記録訂正済み |
| `gemini-3.5-flash-lite` のAPI利用 | 明示環境変数でSemantic Planningが成功し、Structured Outputで12候補を取得 | API / Structured Outputは確認済み |
| 3.5 Flash Liteの金沢E2E | 2回とも途中までMask artifactを出したが、`summary.json` / `metrics.json`を残さず終了 | **未完了**。4 Layer成功・品質比較は未確認 |
| Cloud Runの実設定 | `gcloud`認証期限切れで読めなかった | **未確認** |

評価runnerは実効`GEMINI_MODEL`と、異常終了時の終了状態をartifactへ必ず残せていない。
3.5 Flash Liteを採用・比較する前に、private評価artifactへmodel provenanceとfailure情報を残せる
ようにする必要がある。

## 6. 未実装の設計改善

`15_COMMON_LAYER_EXTRACTION_DESIGN.md` は提案であり、以下はまだコード化していない。

1. 内部Semantic Planの `extraction_intent` とcomponent関係。
2. `coherent_group` のcomponent別bbox → Mask → union。
3. 必須component保持・背景混入を確認する共通Quality Check。
4. GeminiによるLayer内容Verificationと、上限1回のcomponent再計画。
5. 多様な固定datasetでの匿名A/B評価。

料理の「皿だけが残り、料理が抜ける」問題は、この未実装の`coherent_group`で解く対象である。
一般subjectの0.5%微小飛び地除去だけでは解決しない。

## 7. 推奨する実施順序

### P0 — PRとブランチを整理する

1. PR #3のopen状態とmain反映済みcommitの関係を解消する。
2. `21e3938` を単独のformat PRにするか明示的に廃棄するか決める。
3. 最新`origin/main`から、`4189159` を最小差分で積み直す。
4. Backend tests、ruff、format、Contract validation、固定金沢ケースを再実行する。
5. 微小飛び地修正のPRを作成する。PR前に3.5 Flash Lite検証を混ぜない。
6. `a8234f1` の資料は、必要ならdocs-only PRとして独立提出する。

### P1 — 3.5 Flash Liteを測定可能にする

1. Quality evaluation runnerのprivate出力に実効Model、profile、終了状態、例外種別を保存する。
2. 同一固定dataset・明示`GEMINI_MODEL=gemini-3.5-flash-lite`で再実行する。
3. 3.7 Flashとの比較で、Semantic / Source / BBox / Mask / Layer / Composition、4 Layer到達率、
   latencyを匿名評価する。
4. Cloud Runの認証を復旧して、デプロイ済み`GEMINI_MODEL`も読み取り確認する。

### P2 — 共通Layer抽出をPoCする

1. 料理・人物・建築・小物を含む固定datasetと、必須要素/除外背景の評価ラベルを用意する。
2. Semantic Planのみで`coherent_group`のcomponent計画をレビューする。
3. component別Mask unionを既存方式とA/B比較する。
4. 回帰がないことを確認してから、限定Verification / 再計画を検討する。

## 8. 今回行わないこと

- 未PRのlocal commitを「完了」と扱うこと。
- 3.5 Flash Liteの未完了runを成功扱いすること。
- 料理専用のMask後処理や、Maskの橋渡しを追加すること。
- Physical Outputの支柱・STL・実寸閾値をAI側で決めること。
- 評価画像の結果だけに合わせてPrompt・閾値を調整すること。
