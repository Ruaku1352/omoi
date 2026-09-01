# AI処理 実装・検証・PR台帳

最終確認: **2026-09-01**。対象は `backend/ai/`、AIを呼ぶBackend設定・生成Service、AI専用の
評価/PoC script、AI設計資料である。Frontend、Physical Output、共通Contractだけの変更は、
AIの挙動を変えた場合を除きこの台帳の対象外とする。

## 1. 状態の読み方

| 表記 | 意味 |
| --- | --- |
| `PR MERGED / main反映済み` | 対応PRがMERGEDで、commitが`origin/main`のancestor。 |
| `main反映・PR未確認` | コードは`origin/main`にあるが、PR #1〜#3のcommit一覧に対応commitがない。PR未作成として**未完了**扱い。 |
| `PR提出済み` | remote branchとPRが存在する。OPENの場合はレビュー/状態整理が残る。 |
| `ローカルのみ` | local branchにだけ存在し、remote tracking・PRがない。**未完了**。 |
| `private検証` | `poc-images/` / `poc-output/` / `tmp/` のGit管理外artifact。コード/PRの反映状態を示さない。 |

このRepositoryでは、**PR未作成のcommitは未完了**として扱う。push済みであっても、PRが無ければ
完了とは扱わない。

## 2. 現行Pipelineと実装位置

| 段階 | 主な実装 | 現在の挙動 | private観測 |
| --- | --- | --- | --- |
| Input decode / source asset | `backend/ai/image_ops.py`, `gemini.py` | 入力写真をdecodeし、元写真assetを作る。 | source preview |
| Semantic Planning | `backend/ai/gemini.py` の`GeminiSemanticPlanner` | Gemini Structured Outputでcandidate、source photo、bbox、`kind`、必要componentを得る。 | `semantic-plan.json`, bbox preview |
| Segmentation | `backend/ai/segmentation.py` | EfficientSAM-Ti ONNX CPUへcomponent bboxを渡してMaskを得る。 | mask / score / attempt |
| Mask Quality / island判定 | `backend/ai/quality.py`, `gemini.py::_build_candidate` | empty/full/prompt外を拒否。physical-readyでは連結成分を確認する。 | component数、面積比、border touch、reject reason |
| RGBA Layer | `backend/ai/image_ops.py` | 採用Maskをtight cropしたRGBA PNGにする。 | Layer PNG |
| Layer selection | `backend/ai/gemini.py::_select_layers` | scene anchor最大1、v3ではarchitecture primaryを優先し、4件を選ぶ。 | candidate metrics |
| Composition | `GeminiComposer`, `backend/ai/assembly.py` | Gemini配置→Python正規化。physical-readyでは背景最小幅・下端gapを制約する。 | composition preview / physical diagnostics |
| Artwork assembly | `backend/ai/assembly.py`, `backend/app/services/generator.py` | Artwork + source/layer assetを組み、BackendでContract検証する。 | Artwork / Asset Manifest / bundle |

`GEMINI_MODEL` はSemantic PlanningとCompositionの両方に使う。Mask境界をGeminiが直接出力する設計ではない。

## 3. 飛び地・背景・浮遊量の実装ログ

「どこで不採用になるか」を、導入commitと現在の状態で示す。

| 導入 | 実装箇所 | 挙動 | 現在の状態 |
| --- | --- | --- | --- |
| `fac2ef3` | `quality.py` のdiagnostics / `QualityPolicy` | component数・最大成分比・bbox coverage・border touchを観測する。既定は`observe`で、これだけでは候補を落とさない。 | main反映済み |
| `cedb1a6` | `gemini.py::_build_candidate` | `physical_layer_v2`では最終union Maskが単一連結でないcandidateを`not_single_component`として不採用にする。十分なLayer数に届かなければ生成失敗。 | main反映済み |
| `43b0e4f` | `quality.py`、`gemini.py`、`SEMANTIC_PROFILE=physical_layer_v3_architecture` | 建築main候補を優先し、建築roleの主成分外が0.1%以下なら微小islandだけ除去。超過する大きな分離は結合せず`not_single_component`。 | main反映済み |
| `4189159` | `quality.py::clean_micro_islands`、`gemini.py`、設定 | 一般subjectでも主成分外の合計が暫定0.5%以下なら削除して採用。超過時は不採用。 | **ローカルのみ・未push・PRなし** |
| `cedb1a6` | `gemini.py::_build_scene_anchor` / `_select_layers` | `scene_anchor`を背景候補として最大2件計画し、最大1件を選ぶ。単一bboxの矩形Cropで、表示幅0.60未満なら不採用。 | main反映済み |
| `cedb1a6` | `assembly.py::bottom_gaps` / `clamp_bottom_gaps` | 下端gapが0.30超ならGemini再構図を最大1回行い、それでも超えるLayerだけYを下げる。支柱・接続・強度は扱わない。 | main反映済み |

### 不採用の流れ

```text
component Mask不良（empty / full / prompt外 / required component失敗）
  → candidate不採用
union後に大きな分離成分が残る
  → physical-readyでは not_single_component としてcandidate不採用
選べるLayerが4未満
  → 明示的なAI生成失敗（Mockで補完しない）
```

「大きな飛び地を修正して採用する」実装はない。無関係な背景片と、器＋料理・人物＋手持ち物の
ような意味ある複数要素を、面積だけで区別できないためである。後者は`15_COMMON_LAYER_EXTRACTION_DESIGN.md`
の`coherent_group`として未実装の検証対象である。

## 4. コード実装の時系列

| 日付 | Commit | 実装内容 | PR / Push / main状態 |
| --- | --- | --- | --- |
| 2026-08-21 | `5da5d1e` | FastAPI Backend、AI module境界、Mock generator、生成APIの初期実装。 | main反映・PR未確認 → **未完了** |
| 2026-08-21 | `9a58083` | Mock generatorをBackend側へ移し、`backend/ai/`を実AI呼び出し境界として整理。 | main反映・PR未確認 → **未完了** |
| 2026-08-23 | `a33512b` | API全体時間・AI生成時間の基本ログ、log configを追加。 | main反映・PR未確認 → **未完了** |
| 2026-08-25 | `d8cee92` | Gemini Structured Output、EfficientSAM-Ti ONNX、bbox→Mask→RGBA、Assembly、Real AI PoC scriptを導入。 | [PR #1](https://github.com/Ruaku1352/omoi/pull/1) MERGED / main反映済み |
| 2026-08-26 | `3bc97e8` | MVPの5写真→4 Layer、2L Landscape geometry、composition正規化を固定。 | [PR #2](https://github.com/Ruaku1352/omoi/pull/2) MERGED / main反映済み |
| 2026-08-26 | `ddc3daf` | source / bbox / mask / layer / compositionを追跡できるfrontend handoff bundleを追加。 | PR #2 MERGED / main反映済み |
| 2026-08-27 | `fac2ef3` | Mask診断、QualityPolicy、private quality evaluation runnerを追加。 | PR #2 MERGED / main反映済み |
| 2026-08-30 | `cedb1a6` | `physical_layer_v2`。背景`scene_anchor`、単一連結subject、下端gap再構図/clamp、private physical diagnosticsを追加。 | main反映・PR未確認 → **未完了** |
| 2026-08-31 | `43b0e4f` | `physical_layer_v3_architecture`。建築本体優先、建築微小island 0.1%除去、architecture A/B評価の記録を追加。 | main反映・PR未確認 → **未完了** |
| 2026-08-31 | `7695698` | Semantic / Segmentation attempt / ONNX inference / Mask quality / Composition / AI totalの詳細performance timing logを追加。 | remote push済み、[PR #3](https://github.com/Ruaku1352/omoi/pull/3) OPEN。commit自体は`origin/main`のancestorで、PRの状態整理が必要。 |
| 2026-08-31 | `21e3938` | Backend AI sourceのRuff formatのみ。挙動変更なし。 | **ローカルのみ・未push・PRなし** |
| 2026-09-01 | `4189159` | 一般subjectへ0.5%以下の微小island除去を拡張。`mask_cleanup`診断を追加。 | **ローカルのみ・未push・PRなし** |

## 5. AI資料・評価資料の時系列

資料は実装そのものではないが、採否・責任境界・再現条件を判断するために必要なログとして管理する。

| 日付 | Commit / Artifact | 内容 | PR / Push状態 |
| --- | --- | --- | --- |
| 2026-08-24〜27 | `d500cd7`, `93f0883`, `fac2ef3` | Model選定、Cloud Run制約、作品品質Gap、評価workflowを`docs/ai/`へ追加。 | main反映済み |
| 2026-08-31 | `poc-output/architecture-ab-*` | 親`cedb1a6`と`43b0e4f`の固定6ケースA/B。建築3ケースの改善、非建築の明確な回帰なしを確認。 | private検証、PR対象外 |
| 2026-08-31 | `poc-output/user-evaluation-*` | 匿名化した候補・source・bbox・mask・Layer・構図を人手評価できるpackage。 | private検証、PR対象外 |
| 2026-09-01 | `poc-output/kanazawa-micro-island-evaluation-*` | 金沢5枚、3.7 Flash設定で人物Maskの飛び地0.4788%を削除して4 Layer生成、Contract validation成功。 | private検証。実装`4189159`は未PR |
| 2026-09-01 | `a8234f1` | 共通Layer抽出設計案。`single_form` / `coherent_group` / `scene_anchor`を提案。 | **ローカルのみ・未push・PRなし** |
| 2026-09-01 | `699fbd3`, `a6e38c2` | local作業状況、PR未作成=未完了、建築/背景/浮遊量/飛び地の状態を記録。 | **ローカルのみ・未push・PRなし** |
| 2026-09-01 | `poc-output/kanazawa-model-evaluation-*` | `gemini-3.5-flash-lite`のSemantic Planningは成功。E2Eはsummary/metricsを残さず途中終了。 | private検証、**未完了** |

## 6. PR・push状態の一覧

| Branch / commit群 | Remote | PR | 状態 | 完了判定 |
| --- | --- | --- | --- | --- |
| `feat/real-ai-efficient-sam` / Real AI基盤 | originあり | PR #1 MERGED → main | PR #1のcommitはmain反映済み | 完了 |
| `feat/ai-mvp-5photos-4layers` / 4 Layer MVP・handoff・quality evaluation | originあり | PR #2 MERGED → main | PR #2のcommitはmain反映済み | 完了 |
| `cedb1a6`, `43b0e4f` / physical-ready・architecture | branchはoriginあり | 対応PRなし（PR #1〜#3のcommit一覧で確認） | codeはmain ancestor | **未完了（PR未作成）** |
| `chore/ai-performance-timing` / `7695698` | originあり | PR #3 OPEN、base=`feat/ai-mvp-5photos-4layers` | commitはmain ancestorだがPRはopen | PR提出済み、状態整理待ち |
| `chore/ai-ruff-hygiene` / `21e3938` | originなし | なし | local only | **未完了** |
| `feat/ai-general-micro-island-cleanup` / `4189159` + docs | originなし | なし | local only。`origin/main`より30 commits behind（台帳作成時点） | **未完了** |

## 7. 未完了事項と次アクション

| Priority | 項目 | 完了条件 | 現在の阻害要因 |
| --- | --- | --- | --- |
| P0 | PR #3の状態整理 | PRをmerge/closeしてmainとの状態を一致させる | open PRがmain ancestorと不整合 |
| P0 | Ruff整形の扱い決定 | 単独PRとして提出、または明示的に採用しない | local only |
| P0 | 0.5%微小island PR | main最新から最小差分を積み直し、test / lint / format / contract /固定評価後にPR作成 | branchがmainより遅れ、未push・未PR |
| P0 | 3.5 Flash LiteのE2E検証 | 実効model・終了状態をartifactへ残し、4 Layer生成と品質を比較 | 現行runnerは異常終了を完全記録できない |
| P1 | 背景Layer評価 | 背景あり/なしの作品品質を固定datasetで評価 | `background_missing`は観測のみ |
| P1 | 浮遊量評価 | Asset外接矩形gapとAlpha形状の見え方を比較。製造条件とは分離 | 0.30は暫定の構図値 |
| P1 | `coherent_group` PoC | 料理＋器等で必須componentを保持し、非建築も回帰しない | 設計のみ、未実装 |

## 8. 守る境界

- Artwork / Asset Manifest / API Contractを、この台帳のために変更しない。
- private評価artifactに秘密値、画像内容、memoryTextを新たに転記しない。
- 大きな飛び地を面積だけで削除・結合しない。
- 支柱・土台・STL・物理強度の判断をAI処理の成功条件へ混ぜない。
- 未PRの変更・未完了の3.5 E2Eを成功扱いにしない。
