# AI品質評価プロトコル

最終確認: **2026-09-01**。本資料は、AI品質変更を採用する前に必要な評価方法・証跡・
判定基準の正本である。対象は `backend/ai/` とAIを呼ぶ生成Serviceに限る。Artwork Data、
Asset Manifest、API Contract、Frontend、Physical Outputの責務は変更しない。

## 1. 固定する原則

1. **品質を先に評価し、速度改善は品質ベースライン確定後に行う。**
2. 少数の成功画像にPrompt・閾値・候補数を合わせない。開発用画像と採否用画像を分ける。
3. Gemini出力の揺れを、単発実行の見た目でコード差と断定しない。
4. 変更対象のstageだけを比較できる場合は、同じ上流artifactを再生する段階分離評価を併用する。
5. Real AIが4 Layerを作れない場合にMockやreject済みMaskで補完しない。
6. 意味的な完全保証は現時点のAI責務に含めない。ただし、思い出として不適切な対象選定・
   必須対象の欠損は評価記録に残し、品質変更による悪化を許容しない。

## 2. 評価対象と固定条件

初回MVP評価Profileは次で固定する。Contractの`sourcePhotos[]` / `layers[]`が可変長であることは
変わらないが、代表評価の成功条件は5写真から4 Layerである。

| 項目 | 固定値 / ルール |
| --- | --- |
| 入力 | 写真5枚 + memoryText |
| 成功出力 | RGBA PNGを持つ4 Layer、Artwork / Asset ManifestのContract validation成功 |
| Semantic / Composition model | `gemini-3.5-flash-lite` |
| Segmentation | EfficientSAM-Ti + ONNX Runtime CPU |
| 実行環境 | Cloud Run。revision、CPU / memory / concurrency / timeoutを実行manifestへ記録する。 |
| 比較 | 同じ写真、memoryText、model、環境変数、code revision以外の条件を揃える。 |
| 比較禁止 | 写真数、candidate数、Profile、Prompt、Quality Gateを同時に変えて原因を混ぜる。 |

Cloud Runの基準性能値は[ローカル作業状況](16_LOCAL_WORK_STATUS_20260901.md)を参照する。

## 3. private datasetの分離

評価画像・memoryText・生成artifactはprivate領域（`poc-images/`、`poc-output/`）にのみ置き、
Gitへ画像内容・memoryText・secretをcommitしない。画像の代わりにcase IDとハッシュをmanifestへ残す。

| 集合 | 目的 | 運用 |
| --- | --- | --- |
| Development pool | 原因調査、Prompt / 設計PoC | 追加・入替可。採否の根拠に単独で使わない。 |
| Locked regression-6 | 変更採否、回帰検知 | 以下の6 caseを固定し、変更に都合よく入替・除外しない。 |
| Extension pool | 回帰の疑い・新しい失敗型の再現 | 結果を記録する。繰り返し現れる型だけ、次の評価版でlocked集合へ追加する。 |

`Locked regression-6`は次の役割を持つprivate case IDで構成する。写真の選択、file hash、
memoryText hash、必要要素、明確な除外背景は、評価開始前にprivate manifestへ固定する。

| Case ID | 必須特性 | 主な回帰検知 |
| --- | --- | --- |
| `ARCH-01` | 遮蔽された建築 | 建築本体の欠損、前景混入 |
| `ARCH-02` | 複雑な背景を持つ建築 | 背景混入、建築の誤選定 |
| `ARCH-03` | 細部・屋根等が分離しやすい建築 | 必要細部の削除、不自然な分裂 |
| `NONARCH-01` | 人物または動物 | 主成分の欠損、微小飛び地 |
| `NONARCH-02` | 小物または食べ物 | 主題と器・周辺物の取り違え |
| `NONARCH-03` | 人物・小物・食べ物以外の代表例 | semantic / Mask / Compositionの一般回帰 |

金沢の料理/器はDevelopment poolで必ず評価する。`NONARCH-02`へ採用するかは、既存caseを
置換せず、次の評価版で追加する場合だけ決める。これにより、画像数が少ないことを理由に
新しい実装へ都合のよいcaseだけへ最適化することを防ぐ。

## 4. 評価manifestと保存artifact

各実行はprivateな`evaluation-manifest.json`に次を記録する。任意の画像binaryやmemoryText本文、
API keyは入れない。

```json
{
  "evaluationId": "quality-YYYYMMDD-<change>",
  "variant": "baseline | candidate",
  "codeRevision": "git SHA",
  "cloudRunRevision": "revision ID",
  "profile": "semantic profile",
  "geminiModel": "gemini-3.5-flash-lite",
  "runtime": {"cpu": 1, "memory": "2Gi", "concurrency": 1, "timeoutSeconds": 600},
  "environmentFingerprint": "secretを含まない設定hash",
  "cases": [{"caseId": "ARCH-01", "inputHash": "...", "memoryTextHash": "...", "run": 1}]
}
```

case・runごとに、少なくとも次を`poc-output/`へ保存する。

- Semantic Plan、候補一覧、選択candidate、candidate rejection reason
- source photo ID、bbox、component / attempt診断、mask、RGBA Layer
- composition preview、Artwork Data、Asset Manifest、Contract validation結果
- stage別elapsed_ms、AI total、実行失敗時のfailure stage

artifactは評価用に匿名化した別packageを作れるようにし、評価者へcode revisionやvariant名を見せない。

## 5. 比較方法

### 5.1 段階分離評価

Mask cleanup、Mask union、Quality Gateなど上流Semanticを変えない変更は、同じSemantic Plan・
bbox・component入力を再生して比較する。ここではEfficientSAM以降の差を確認し、Geminiの揺れを
コード差と取り違えない。

Semantic Planning、Layer Selection、Composition、Prompt、candidate数を変える変更は、段階分離だけで
合格にしない。次のE2E評価も必須である。

### 5.2 E2E評価

baselineとcandidateを各case **3回**ずつ実行する。各runは別の匿名IDにし、結果を評価者へ混在提示する。
再試行は失敗を隠すために行わない。API失敗など実行不能なrunも、failure stage付きで結果に含める。

同一run内で評価する観点は次である。

| 観点 | A | B | C |
| --- | --- | --- | --- |
| Semantic | 思い出の対象として自然 | 編集前提なら利用可能 | 明確に不適切・重要対象を見失う |
| Source / BBox | 対象に適した写真・範囲 | 軽微な余白/不足 | 別写真・大きな過不足 |
| Mask | identity維持、背景混入・欠損なし | 軽微な修正で利用可 | 背景混入、必要部分の欠損、不自然な分裂 |
| Layer | 単独assetとして読める | 編集前提なら利用可 | Layerとして意味をなさない |
| Composition | 4 Layer全体が作品として読める | 軽微な編集で利用可 | 破綻、極端な浮遊、重要要素の見えにくさ |

各Cには、`semantic` / `source` / `bbox` / `mask` / `layer` / `composition` / `contract`の
failure stageを必ず一つ以上付ける。人手評価者は少なくとも2名とし、不一致または新規Cは
AI担当とProduct / Designがartifactを見て判定理由を追記する。

## 6. 採否基準

品質変更をPR候補にできるのは、次をすべて満たす場合だけである。

1. 変更の狙いに対応する改善が少なくとも1 caseで確認できる（`C → A/B`または`B → A`）。
2. `Locked regression-6`の非対象caseに、baselineで安定していなかった新規Cを増やさない。
3. 3 runの多数（2回以上）で4 Layer・Contract validationに成功し、baselineより成功率を下げない。
4. architecture変更では、建築本体・屋根等の必要部分をcleanupで落としていないことを確認する。
5. `coherent_group`変更では、必須component保持の改善と、無関係な寄せ集めの増加なしを確認する。
6. 既存test、lint、format、Contract validationが通る。

baselineとcandidateの両方にCが出た場合は、同じfailure stageかを分けて記録する。candidateに
新しいCがあれば自動採用しない。原因を切り分け、dataset・評価基準・実装のいずれかを更新する場合も、
変更理由をDecision Logへ残して次の評価版から適用する。

## 7. 背景・浮遊・意味ある分離の扱い

- `scene_anchor`がないこと自体は失敗ではない。背景がない方が作品として読みやすい場合は許容する。
- 背景が必要かは、Layer全体の作品評価で判断する。Layer配列位置に背景の意味を固定しない。
- 下端gap `0.30`はAI構図の暫定diagnostic / clamp条件であり、物理強度や支柱の可否を表さない。
  評価では「極端な浮遊で作品として読めないか」をComposition観点で確認する。
- 離れた大きなcomponentを面積だけで削除・結合しない。器＋料理等は`coherent_group`として、
  必須componentと関係を計画・検証できるようになってから扱う。

## 8. 実行・PR時のチェックリスト

1. baseline / candidateと評価対象stageを宣言する。
2. private manifestを固定し、実行前にcaseの入替を止める。
3. 段階分離評価（対象なら）とE2E 3回比較を実施する。
4. 匿名評価とfailure stage記録を完了する。
5. 採否基準を満たす場合だけ、最新`origin/main`を起点とする単独branchへ最小差分を積む。
6. PR本文に、評価ID、対象caseカテゴリ、品質結果、実行した検証、既知の限界を記載する。

速度・candidate数・Quality Gateの変更は、本プロトコルで品質ベースラインが確定した後にのみ行う。
