# AI残タスク実行バックログ

最終確認: **2026-09-01**。本資料は、品質を優先してAI残タスクを開始する順序と完了条件を固定する。
作業の完了はcommitやpushではなく、**適切なPRと必要な評価証跡が揃った時点**とする。

## 1. 実行上の前提

- 通常作業場所はRepository rootのみである。比較用worktreeは新設しない。
- rootの現在branchは未PRの変更を含み`origin/main`より遅れているため、直接PRにしない。
- 新しいPR branchは、rootで最新`origin/main`から作る。必要なlocal commitだけをcherry-pickする。
- `tmp/ab-parent`はGit worktreeではない古い比較copyである。ロック解除後、明示pathだけを削除する。
- AI担当は`backend/ai/`、AIの生成Service、AI専用評価script / docsを扱う。API非同期化、Job Store、
  Cloud Tasks、GCS、Frontend、Physical Outputは担当外であり、先回り実装しない。

品質評価の具体的な方法・採否条件は[品質評価プロトコル](18_QUALITY_EVALUATION_PROTOCOL.md)を正本とする。

## 2. 実施順序

| 順序 | 作業 | 主担当 | 完了条件 | PR / 境界 |
| ---: | --- | --- | --- | --- |
| 0 | PR / branch状態を整理する | AI + Repository管理者 | PR #3のopen状態をmainと整合させ、mainへPRなしで入った変更は経緯を記録する | AIは独断でmain履歴を書き換えない。 |
| 1 | private評価manifestとLocked regression-6を固定する | AI | case ID、input / memoryText hash、必須要素、除外背景、評価者を実行前に固定 | 画像・memoryText本文・secretはcommitしない。 |
| 2 | architecture品質の再評価 | AI + 評価者 | `cedb1a6`と`43b0e4f`を現行Cloud Run / 3.5 Flash Liteで評価し、改善・回帰を判定 | コードはmainにある。評価結果docs / artifactのPR扱いはRepository管理者と決める。 |
| 3 | 0.5%微小islandの評価 | AI + 評価者 | `4189159`を段階分離 + E2Eで比較し、主成分保持と非architecture回帰なしを確認 | 合格時だけ最新mainから最小差分PRを作る。 |
| 4 | 背景 / 浮遊Layerの品質評価 | AI + Product / Design | 背景なし許容とscene anchor必要例を作品A/B/Cで記録する | 支柱・物理強度は扱わない。 |
| 5 | `coherent_group` Planning PoC | AI + Product / Design | 器＋料理等で必須component・除外物の計画を人手確認し、誤った寄せ集めがない | 内部Semantic Planのみ。Contract変更なし。 |
| 6 | `coherent_group` Segmentation PoC | AI | component別bbox→Mask→unionで既存より必須component保持を改善し、回帰なし | 前工程の合格後に別PR branchで開始。 |
| 7 | 品質変更をPR化する | AI | test / lint / format / Contract validation / 評価証跡をPR本文へ添付 | docs、format、品質変更、速度変更を混ぜない。 |
| 8 | 速度改善の観測とPoC | AI + Backend / GCP | P0品質ベースラインを壊さず、同一条件で短縮量を示す | CPU設定変更はBackend / GCPと調整する。 |

## 3. 直近の品質作業

### 3.1 Architecture再評価

目的は`physical_layer_v3_architecture`が、建築本体を残しつつ無関係な微小islandだけを除去できるかを
再確認することである。scoreやcomponent数だけで合格にしない。

- `ARCH-01`〜`ARCH-03`で、建築本体、屋根/細部、背景混入、分裂を確認する。
- `NONARCH-01`〜`NONARCH-03`でSemantic / Mask / 4 Layer / Compositionの回帰を確認する。
- 成果物は、匿名化されたA/B package、評価表、failure stage、private manifestである。
- 判定は[品質評価プロトコル](18_QUALITY_EVALUATION_PROTOCOL.md)の採否基準に従う。

### 3.2 一般微小island cleanup

目的は、主成分を保持し、離れた無関係な微小成分だけを削除して、候補を不必要に不採用にしないことである。

- 暫定閾値`0.005`は決定済みの製品値ではない。評価結果なしに緩和・拡張しない。
- 人物、小物、料理を含め、背景混入・必須部分の削除・4 Layer到達率を評価する。
- 料理/器のような大きな意味ある分離を、このcleanupで救済しようとしない。

## 4. `coherent_group`の段階ゲート

| Gate | 実施内容 | 次へ進む条件 |
| --- | --- | --- |
| G1 | Semantic Planに`extraction_intent`、component、required、relationを追加した案を出す | 評価者が必須要素と除外物を判定できる。 |
| G2 | Planning結果をprivate datasetでレビューする | 不要物の寄せ集めや必要要素の欠落が増えない。 |
| G3 | component別Maskとunionを既存方式と比較する | 料理/器等の欠損が減り、architecture / 人物 / 小物に回帰がない。 |
| G4 | 必要時だけ内容verificationと最大1回の再計画を比較する | 品質改善がlatency増加を正当化し、無限retryを導入しない。 |

G1〜G4は別々の変更・評価単位であり、G1の設計だけでSegmentation実装へ進まない。

## 5. 速度改善へ進む条件と順序

P0品質作業が終わるまで、candidate数、Semantic Prompt、Quality Gate、Segmentation条件を速度のために
変えない。品質ベースライン確定後は、次の順に進める。

1. CPU 1→2のCloud Run実測（AI挙動を変えないため最初に行う）。
2. RGBA Layer生成のばらつきの観測分解。
3. Semantic入力準備の内訳観測。
4. rejected candidateの早期終了の品質A/B。
5. candidate数削減の品質A/B。

4・5は最終作品の品質を直接変え得るため、速度値だけで採用しない。

## 6. PR単位とDefinition of Done

| PR種別 | 含めてよいもの | 含めないもの | Done |
| --- | --- | --- | --- |
| docs | 評価手順、台帳、設計案 | AI挙動変更、format | 最新main基準、レビュー可能な責任・採否条件を明記。 |
| format | Ruff整形だけ | ロジック、docs、閾値 | format / lintが通り、挙動変更なし。 |
| 品質変更 | 一つの仮説を検証する最小AI差分とtests | 別の品質案、速度最適化、Contract変更 | 固定評価合格、test / lint / format / Contract validation成功。 |
| 速度変更 | 一つの性能仮説と必要な観測 | 品質条件の同時変更 | 同一品質条件の比較と品質回帰なし。 |

PR本文には、対象code SHA、baseline、candidate、評価ID、対象caseカテゴリ、A/B/C集計、実行した
検証、既知の限界を必ず書く。PRがないcommit・pushは未完了のままとする。

## 7. AI担当が決めないこと

- 3Dプリントの支柱、土台、接続、STL、実寸、強度、組立方法
- 非同期API、Job Store、Cloud Tasks、GCSの採用と実装
- Artwork Data / Asset Manifest / API Contractの変更
- 思い出として何を必ず残すかというプロダクト方針

これらが品質評価に必要になった場合、AI担当はartifactと判断が必要な点を提示し、担当者の決定を待つ。
