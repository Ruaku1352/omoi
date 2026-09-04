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

#### 既存private artifactの再確認（2026-09-01）

`cedb1a6`相当の親artifactでは、architecture 3ケース中1ケースだけが4 Layerまで到達した。
`43b0e4f`相当のcandidate artifactでは3ケースすべてが4 Layerまで到達し、`architecture_primary`も
各ケースで採用されている。この差は、建築本体を候補として残せる可能性を示す。

一方で、各variantは1回だけのローカル実行であり、現行Cloud Run条件・`gemini-3.5-flash-lite`・3回実行の
比較ではない。Codex上のcomposition preview確認では、candidateにも金閣寺・姫路城・ノートルダムで建築物の
重複や大きなLayer重なりが残る。よって、このartifactを`43b0e4f`採用の根拠にはしない。

本PoCの画像確認はCodexの画像理解と評価者の目視で行う。生成済みprivate artifactを外部VLMへ再送信する
必要はない。ただし、正式な品質評価プロトコルの匿名A/B/C評価を実施したことを意味しない。

`scripts/create_architecture_ab_run_sheet.py`は、Locked manifestからbaseline/candidate各3回、計36回の
private実行台帳を作る。台帳にはcase ID、input / memoryText hash、code revision、profile、実行回数、
未記入のCloud Run結果欄だけを持たせ、写真・memoryText本文・secretを含めない。Cloud Runのrevision、
非secret環境fingerprint、artifact directory、failure stageの記入と36回の実行はBackend/GCP担当の作業であり、
AI担当はデプロイや実行条件を変更しない。

#### Backend/GCP担当への実行依頼

AI側から必要な入力は、privateの実行台帳だけである。Backend/GCP担当は次を満たす36回を実行し、各run IDへ
結果を記入する。

1. `baseline`は`cedb1a6804823871cd00449f79ff2d9ef7edec15`・`physical_layer_v2`、`candidate`は
   `43b0e4f`・architecture 3件だけ`physical_layer_v3_architecture`、non-architecture 3件は
   `physical_layer_v2`で実行する。
2. variant内の18回は同じCloud Run revisionを使う。baseline/candidate間ではcode revisionが違うため
   Cloud Run revisionは別でよいが、CPU 1、memory 2 Gi、concurrency 1、timeout 600秒、
   `gemini-3.5-flash-lite`、`efficient_sam_onnx`は一致させる。変更が必要なら、比較を始めずAI担当へ先に共有する。
3. case IDごとに、台帳のinput hashとmemoryText hashに一致するprivate入力を使う。本文・画像・API Keyは
   台帳・Git・公開ログへ出さない。
4. runごとに、Cloud Run revision、secretを含まない環境fingerprint、4 Layer成功、Contract validation、
   failure stage、private artifact directoryを返す。artifactは台帳の8種類を揃える。

AI担当は、結果を匿名化して建築本体・屋根/細部・背景混入・不自然な分裂・non-architecture回帰を目視確認し、
採否基準へ照合する。36回の実行結果が揃うまで`43b0e4f`を採用しない。

`scripts/summarize_architecture_ab_run_sheet.py`は、記入済み台帳からvariant・caseごとの3回成功数、
failure stage、runtime記録の一貫性を集計する。Cloud Run revision、環境fingerprint、4 Layer、
Contract validation、artifact directoryのいずれかが欠けるrunは技術証跡として未完了にする。現在の台帳を
検査したprivate summaryは36 runすべて未記入のため`technicalEvidenceReady=false`（不足記録216件）である。
これは失敗結果ではなく、Backend/GCP実行前であることの明示である。匿名化目視評価はこの集計とは別に必要である。

### 3.2 一般微小island cleanup

目的は、主成分を保持し、離れた無関係な微小成分だけを削除して、候補を不必要に不採用にしないことである。

- 暫定閾値`0.005`は決定済みの製品値ではない。評価結果なしに緩和・拡張しない。
- 人物、小物、料理を含め、背景混入・必須部分の削除・4 Layer到達率を評価する。
- 料理/器のような大きな意味ある分離を、このcleanupで救済しようとしない。

2026-09-01のローカルPoCでは、5写真から4 Layerを生成し、5候補へcleanupが適用された。PoC bundleは
原寸Maskと目視用サムネイルを別名で保存するよう修正し、原寸Maskから再計算した除去面積比が実行時の
`mask_cleanup` metricsと5候補すべて小数第6位まで一致した。

同日に、建築・料理/小物・人物を含むprivate 3ケースを`physical_layer_v2`と`gemini-3.7-flash`で各1回
実行した。3ケースすべて4 Layerまで到達し、cleanupは順に3・2・3候補へ適用された。大きく分離した
候補は4・6・4件が`not_single_component`のまま不採用であり、料理/器などをcleanupで強制的に一体化
していない。Codex上の生成済みpreviewではcleanupに起因する明白な小部分の欠損は見つからなかった。

`scripts/replay_micro_island_cleanup.py`で、この3ケースのcleanup適用8候補について、保存済みの原寸Maskから
同じcleanupを再生した。8候補すべてで、再生した除去面積比・適用可否は実行時の`mask_cleanup` metricsと
一致した。この段階分離証跡は、Geminiの候補選定が揺れてもcleanup処理自体を再確認できるようにする。

同じ8枚の原寸Maskを`max_removed_area_ratio=0`でも再生した。0.5%設定で採用できた8候補は、0%設定では
すべて同じ除去面積比のまま`applied=false`となり、不採用になる。これは「候補選定の違い」ではなく、
0.5% cleanupが小さい孤立成分だけを除去して候補を利用可能にする差である。なお、E2EではGeminiの
Semantic Planが揺れるため、この段階分離結果とE2Eの4 Layer到達率を混同しない。

同じ3ケースで、`MASK_MICRO_ISLAND_MAX_AREA_RATIO=0`のbaseline E2Eも各1回実行した。baselineも
3ケースすべて4 Layerまで到達したが、Geminiが返すSemantic Planと候補集合がcandidate実行時と変わった。
したがって、E2Eの採用候補数や4 Layer到達数の差をcleanupの効果として解釈しない。

人物の二重選択や大きすぎるLayerなど、Semantic / Compositionの別問題は3ケースで確認された。このPoCは
cleanup stageの再生可能性と可視上の安全性を示す。段階分離比較と評価者目視はこの後に完了したため、
cleanupだけの独立PRとして`cbe3958`を作成し、[PR #6](https://github.com/Ruaku1352/omoi/pull/6)をOPENした。
Semantic / Compositionの問題をこのPRへ混ぜない。

2026-09-01の評価者目視では、cleanupに起因する小さい必要部分の欠損はないと確認された。料理＋器の
ケースでは料理がLayerから抜け、器だけが残った。これは0.5% cleanupの副作用ではなく、
`coherent_group`をSemantic Planとcomponent別Mask unionへ適用していない課題である。cleanup PRでは
料理専用の補正を混ぜず、`coherent_group` G2/G3の次の優先改善課題として扱う。

### 3.3 背景 / 浮遊Layerの初期PoC観測（2026-09-01）

privateの5写真入力4ケースで、実GeminiとEfficientSAM-Tiを使い、5写真から4 Layerを生成した。
すべてでContract validationは成功したが、作品品質の採否は別である。

- この4ケースではGeminiが`scene_anchor`を計画し、`background_missing=false`だった。
- その後、既存のprivate artifactから`background_missing=true`の実写真3件を再確認した。いずれも
  4 LayerとContract validationには成功している。ノートルダムv3は建築本体・尖塔・像・バラ窓が
  分かれており、背景なしでも建築自体は読めるが、一つの作品としてのまとまりは弱い。ノートルダムv2も
  塔・彫像・バラ窓が散在し、背景なしを積極的に選ぶ理由は見つからなかった。一方、料理・工芸のケースは
  黒い皿・花柄の包み・スプーンが一つの静物として読め、背景なしでも許容できる候補だった。
  この3件の`scene_anchor_candidate_id`はいずれもnullである。v3のノートルダムだけは大きすぎたバラ窓を
  下げて、最終bottom gapを0.30まで補正している。v2と料理・工芸には位置補正がない。
- 現行`physical_layer_v2`は、品質条件を満たす`scene_anchor`が1件でもあれば必ず先に採用する。
  したがって、`background_missing=true`は「scene anchorが候補化・採用されなかった」観測であり、
  背景なしを意図的に選ぶ規則ではない。
- 実装テストでは、`scene_anchor`が無いSemantic Planでも4 Layer生成を成功扱いにし、private診断へ
  `background_missing=true`を記録することを確認している。これは背景なしの**技術的な許容**であり、
  実写真で背景なしを選ぶべきかという**作品上の判断**を示すものではない。
- 複数の前景Layerが同じ被写体・場面を重複して含む場合があり、目視では大きな重なりや切り抜きの
  不自然さが確認された。これは4 Layer到達やContract validationだけでは検出できない。
- 現行のComposition PromptはCanvas内へ収めることと下端gapだけを制約にしており、Layer間の重なり量、
  同じ主題の重複、scene anchorと前景の役割の重複を制約にしていない。

この観測だけでPromptや選定規則を変更しない。背景なしの許容可否は、`scene_anchor`の有無ではなく、
Layerどうしが同じ記憶を説明する関係にあるかを最終previewで判断する必要がある。次の品質変更候補は、
背景なしを選んでよい条件と、許容できないLayer重複の基準をProduct / Designと明文化してから、別PoCとして
Codex上の画像確認と人手目視で比較する。画像、memoryText本文、生成結果はprivate artifactにのみ保持する。

候補ルールは次の二つである。

1. **過度なLayer重複を避ける（評価者承認済み）**: 前景subject同士で、一方の大きな部分を他方が隠す配置を
   避ける。`scene_anchor`が背面にあること自体は許容し、背景を常に外す規則にはしない。2026-09-02に
   Composition Promptへ追加し、private PoCで確認する。重なり率の固定閾値はまだ決めない。
2. **同じ主題を示す前景Layerを原則1件にする案（要検討）**: 「子どもの成長」のように同じ人物の複数時点を
   Layer Artworkとして表す意図があり得る。現行の二重人物例も直ちに不合格にはせず、memoryTextと作品意図を
   含めた別PoCで判断する。現在のSemantic Plan / Layer選定は変更しない。

この提案の根拠として、金沢の庭園ケースでは人物・石塔・模型とscene anchorが一つの旅行記憶として読めた。
一方、同ケースの別構成では同じ人物の後ろ姿と正面姿が両方採用され、二重表現になった。また、庭園＋模型の
ケースではscene anchor自体は必要だが、人物・模型・石塔が大きく重なり、前景の優先順位を読み取れなかった。
したがって、「背景を常に必須にする」「背景を常に外す」のどちらも採らない。

同日に、同じ金沢5写真・memoryTextを使い、Rule Aを含むComposition Promptで`physical_layer_v2`の
E2Eを1回実行した。4 Layer生成とContract validationは成功し、前景は座る人物・後ろ姿の人物・漆器に
なった。Codex上のpreviewでは二人の人物は左右に離れ、漆器も人物の大部分を隠していない。前回のprivate
artifactも同じく大きな隠れはなく、今回の1回ではPrompt追加による明確な差は観測できなかった。Geminiの
候補選定は実行ごとに変わるため、この比較を対象選定の改善根拠にはしない。Rule Aの実装はPoC作業ツリーに
留め、通常Profileへの採用やPR作成は、意図的に重なりやすい複数ケースでの目視確認後に判断する。

Rule Aの目視を再現可能な数値で補助するため、前景subjectのRGBA Alphaを縮小Canvasへ配置し、後方subjectが
前方subjectに隠れる割合をprivate diagnosticsとして追加した。`scene_anchor`との重なりは数えず、閾値による
自動reject・再配置はしない。この診断はquality evaluation runnerだけが明示的に有効にし、通常のAPI生成では
既定で実行しない。同じ金沢caseでこの診断を含む次のE2Eを1回実行したが、Semantic Planning後、
候補生成前に失敗した（failure stage=`semantic`）。この失敗は再試行で置き換えずartifactへ残したため、
重なり数値はまだ得られていない。評価runnerは以後、例外本文を保存せず`source` / `semantic` / `mask` /
`layer` / `composition` / `contract`のfailure stageをprivate recordへ残す。Rule Aの採用・PRは保留とする。

その後、同じcaseを独立3回として実行し、3回とも4 LayerとContract validationに成功した。前景subjectの
最大`back_obscured_ratio`は順に2.28%・15.66%・9.44%だった。2回目と3回目は人物・漆器・背景が読め、
前景subjectが大部分を隠す状態はなかった。一方1回目では`scene_anchor`の元写真に人物が写り込み、前景の
人物と同じ人が複数回現れた。`scene_anchor`はRule Aの測定対象外のため、この問題は重なり率だけでは検出
できない。したがって、Rule Aは「前景subjectの大きな隠れ」を観測する補助としては有効だが、同じ主題の
重複を禁止するRule Bの代替ではない。Rule Bは「子どもの成長」のような意図的な複数時点を区別する条件が
未設計のため、Semantic Plan / Layer選定を変更せず要検討のままとする。この3回はdevelopment PoCであり、
Locked regression-6の採否・通常Profileへの採用・PR作成の根拠にはしない。

## 4. `coherent_group`の段階ゲート

| Gate | 実施内容 | 次へ進む条件 |
| --- | --- | --- |
| G1 | Semantic Planに`extraction_intent`、component、required、relationを追加した案を出す | 評価者が必須要素と除外物を判定できる。 |
| G2 | Planning結果をprivate datasetでレビューする | 不要物の寄せ集めや必要要素の欠落が増えない。 |
| G3 | component別Maskとunionを既存方式と比較する | 料理/器等の欠損が減り、architecture / 人物 / 小物に回帰がない。 |
| G4 | 必要時だけ内容verificationと最大1回の再計画を比較する | 品質改善がlatency増加を正当化し、無限retryを導入しない。 |

G1〜G4は別々の変更・評価単位であり、G1の設計だけでSegmentation実装へ進まない。

### 4.1 料理＋皿のG1/G3 PoC（2026-09-01）

privateの金沢5写真・memoryText（input hash `22c1b2f7...481593a`）で、`gemini-3.7-flash`を使い
G1 Planning PoCを1回実行した。12候補中3候補が`coherent_group`として計画され、その一つ
`cand_p2_montblanc_group`は、黒陶器皿を`primary`、和栗モンブランを必須
`supported_by` componentとして別bboxにした。bboxの目視では、皿全体とモンブラン本体を
それぞれ含んでいた。

同じ保存済みPlanを使い、Geminiを再度呼ばずEfficientSAM-Ti ONNXでG3を実行した。二つの
component MaskをunionしてRGBA Layerを1件生成し、Artwork / Assetの既存validationにも通った。
previewでは黒皿とモンブランが共に残り、背景は透明だった。`mask_cleanup`は
`retained_coherent_group:2`であり、微小island cleanupや形態学的な橋渡しを行っていない。

G3 runnerはcomponent別Maskもprivate artifactとして保存するよう補強した。同じ実行では、皿Maskだけの
寄与がunion全体の69.31%、モンブランMaskだけの寄与が30.69%で、二つのMaskの重なりは30 pxだけだった。
従って、モンブランは皿Maskに偶然含まれたものではなく、別component Maskが実際にLayerへ加えた画素である。
一方、縮小診断の連結component数は細い接触や標本化に影響されるため、`coherent_group`の必須要素保持を
これだけで判定しない。評価者が最終previewを目視確認してから採否を判断する。画像・memoryText本文・
出力はGitへcommitしない。

G4として、元写真とRGBA previewを`gemini-3.7-flash`へ渡すprivate Structured Verificationを各1回
実行した。モンブラン＋皿は、両必須componentが可視、不要背景なし、重大な穴なしとして`pass`だった。
対して盆＋甘味セットは、甘味小鉢の内容物が大きく失われ、右下に背景片があるため`fail`だった。VLM結果は
Codex上の画像確認と一致する。この2例だけでG4を製品Profileへ自動採用はしないが、機械的なMask診断だけで
なく、必須componentの可視性を確認する必要がある証跡になる。

モンブラン＋皿はVLMで`pass`であり、評価者もG3のunion結果を目視承認した。ただし、この承認は
component別Mask unionの有効性に対するものであり、細いgap閉鎖や`coherent_group`全体を通常の生成Profileへ
採用する承認ではない。後者はPoC実装・private artifactの状態に留める。

同じPlanの`cand_p3_sweet_set_group`（金箔盆＋甘味小鉢＋任意のスプーン）もG3で確認したが、これは
**不合格**である。盆は残った一方で、必須の甘味小鉢には大きな透明な穴があり、右下に不要な背景片も残った。
縮小Mask診断は86連結componentで、`coherent_group`の現在PoC実装は必須componentを保持するために
single-form向けcleanupを避けるが、背景混入やcomponent内の欠損を自動拒否していない。この結果は、
`coherent_group`をProfileへ採用する前に、必須component保持・背景混入の共通Quality Check、または
G4の内容verificationが必要であることを示す。料理カテゴリ専用の補正や、穴・背景片の強制削除は追加しない。

### 4.2 細いMaskのgap閉鎖PoC（2026-09-01）

2026-09-01のバスケットボール`coherent_group` G3では、`c4`の腕の穴と、人物・ボールの間の
細い透明な隙間が人手目視で観測された。`c4`と`c9`のcomponent Mask union自体は承認されたが、
評価者は、3Dプリントを前提として細い透明gapを機械的に埋めることを承認した。

このため、外部依存を増やさない二値Maskのmorphological closingを`close_narrow_mask_gaps`として
PoC実装した。`max_gap_px=0`は入力を変えず、正の値だけが指定幅以下の透明gapを閉じる。通常Profileの
既定値は0のままで、PoC runnerだけが明示値を渡すため、現行生成の挙動は変更していない。

モンブラン＋皿のunionに対する比較では、2 px closingはMask面積を約0.075%だけ増やしたが、目視上の
変化は小さかった。6 px closingは約0.476%増やし、皿とモンブランの間だけでなく、細いクリームの
隙間も埋め始めた。現時点の1例だけでは「細い」の安全なpx上限を固定できない。

したがって、**closing処理の通常Profileへの有効化は保留**とする。次のPoCでは、`coherent_group`の
union直後用と、一般の`single_form`用を別設定にし、人物・料理/器・建築で次を比較する。

同日、評価者がcomponent unionを承認済みのバスケットボール2件でも、同じSaved Planとbboxを使って
Geminiを再呼出しせずに比較した。`c4`（人物＋ボール）は2 px closingでMask面積が約0.009%増え、
6 pxでは約0.143%増えた。2 pxでは人物・ボールに太い橋を追加せず、腕付近の細い切れ目だけが閉じた。
`c9`（人物＋ボール）は2 pxで約0.044%増え、主成分とボールは保持された。これらはCodex上の
生成済みpreviewで目視確認した。人物2件は2 pxの候補を支持するが、料理/器では6 pxが細いクリームの
隙間にも影響したため、共通の通常値はまだ固定しない。

1. 元Maskとclosing後MaskをCodex上の画像確認と評価者目視で比較し、必須要素の欠損・背景混入・
   誤接続が増えないこと。
2. `coherent_group`では承認済みrequired component間のgapだけを対象とし、無関係な背景片との接続を
   増やさないこと。
3. `single_form`では大きな分離成分の強制結合に使わず、既存の微小island cleanupと役割を混同しないこと。
4. 採用時は既存の`coherent_group` unionとは別の品質変更PRにし、threshold・対象Profile・回帰結果を
   日本語のPR本文へ残すこと。

### 4.2.1 閉鎖した穴の機械的な充填（2026-09-02）

評価者は、腕の穴だけでなく、窓や建築の開口部を含む**閉鎖した透明な穴は基本的に全て埋める**と指示した。
これは細いgap closingとは別の処理である。Maskの透明画素のうち、画像端の背景へ8方向で到達できない領域を
foregroundへ変える。外部に開いた隙間と、大きく離れたcomponentの間は残るため、Mask同士を橋渡ししない。

`fill_closed_mask_holes`を`backend/ai/image_ops.py`へ実装し、すべてのsubject componentのSegmentation直後と、
component union直後に適用する。`coherent_group`で細いgap closingを使う場合は、closingが外部への細い通路を
閉じて新しい穴を作ることがあるため、その直後にも同じ充填を行う。`scene_anchor`は矩形Cropでありこの対象外とする。
窓・器の内側・人物の腕のような閉鎖穴を同じ規則で扱い、カテゴリ別の補正は増やさない。

通常生成への品質変更となるため、PR作成前に人物・料理/器・建築の既存PoCで、必要部分の欠損、背景混入、
不自然な面積増加、4 Layer到達率を確認する。単体テストでは、複数の閉じた窓を埋め、外側へ開いた穴を残すことを
固定している。パイプラインテストでは穴のあるsubject Maskを入力し、生成後のMask診断が
`interior_hole_count=0`になることを確認した。

2026-09-02に、Geminiを再呼出しせず保存済みPlanをEfficientSAM-Ti ONNXで再生した。ノートルダムの
屋根＋尖塔では、従来のLayer上部にあった閉鎖穴が埋まり、屋根と尖塔の大きな外部gapは残った。人物＋ボールの
`c4`・`c9`でも必要componentを保持し、出力後の縮小Mask診断はともに`interior_hole_count=0`だった。
いずれも背景片の有無や大きなcomponent間の分離は、この充填だけで直す対象ではない。

同じく金閣寺の鳳凰＋台座を、現在の写真hashと一致するSaved Plan・bboxで再生した。Gemini APIは呼ばず、
EfficientSAM-Ti ONNXで必須2 componentを受理し、鳳凰・台座のexclusive寄与は39.35%・60.65%だった。
最初の確認では2 px gap closing後に小さな閉鎖穴が1件生じたため、closing後にも充填を行う順序へ修正した。
同一条件の再生結果では、最終Layerの`interior_hole_count=0`・`interior_hole_area_ratio=0`となった。
この結果は建築細部1 LayerのMask品質証跡であり、4 Layer作品全体の到達率やbackground混入の合格を意味しない。

人物＋ボール`c4`・`c9`の元入力も確認できたが、修正後の2 candidate同時再生は20分以上
`segment_components`から進まなかったため中止した。中止した実行のartifactは作られておらず、今回の
閉鎖穴充填の人物実データ証跡には含めない。既存の`c4`・`c9`結果と、component・union後のパイプラインテストは
残るが、再実行する場合は品質診断の高解像度処理時間を別途計測し、品質条件を変えずに実行方法を確認する。

その後、同じ`c4`を同一写真・Saved Plan・bboxで、Quality GateとCompositionを通さないMask stage replayとして
確認した。EfficientSAM-Ti ONNXは人物11番とボールの各Maskを別々に返し、独自画素は36,444 px・13,960 pxだった。
unionは50,404 pxで、2 px gap closingとclosing後の閉鎖穴充填を行った最終Maskは50,436 pxになった。最終Maskへ
同じ充填を再適用しても変化しないことを確認した。これは人物・ボールを橋渡しせず、閉鎖穴だけを残さない処理の
段階分離証跡である。品質Gate、4 Layer到達率、背景混入、Compositionはこの再生で評価していない。

モンブラン＋皿については、現在の`poc-images/`配下の写真5枚はSaved Planのinput hash
`22c1b2f7...`と一致しない。一方でprivateの保存済み入力コピー`coherent-group-food-case`は同じhashと
一致したため、写真を置換せずに同じSaved Plan・bboxを再生した。2 px gap closingとclosing後の穴充填を
適用した最終Layerは`interior_hole_count=0`であり、Codex上のpreviewでは皿とモンブランの両方が残った。
ただし、この再生では皿componentのMaskがモンブランまで含み、皿のexclusive寄与は69.70%、モンブランは
0%だった。required componentは2件とも受理したが、モンブランcomponentがunionに新しい画素を加えたことは
示せない。従ってこの結果は「料理が最終Layerから抜けていない」目視証跡にはなるが、unionが料理を救った
改善証跡にはしない。保存済みの原寸component Mask 2枚を使う以前の段階分離再生では、unionの493,057 pxに
対して8,490 pxを閉鎖穴として追加し、皿・モンブランの元Mask画素はどちらも100%保持された。いずれも
Mask後処理だけの証跡であり、背景混入・最終4 Layer到達率の代わりにはしない。

### 4.3 建築でのG1 Planning PoC（2026-09-02）

privateの金閣寺5写真・memoryText（入力hashは`ARCH-01`と同じ`cd0ee8eb...5d2911`）で、
`gemini-3.7-flash`を使い`coherent_group_planning`を1回実行した。Geminiは12候補中2候補を
`coherent_group`として計画した。この実行はSemantic Planとbboxの目視用artifactだけであり、Mask、
union、Composition、Artwork生成はまだ実行していない。

- `c1_phoenix_finial`は金銅鳳凰像をprimary、直下の露盤台座を必須`supported_by` componentとして
  計画した。bboxはそれぞれの形状を含み、二つは一つの建築細部として読める。G3へ進めるかは評価者の
  目視承認待ちである。
- `c5_kinkakuji_side_group`は金閣舎利殿をprimary、付属釣殿を必須`attached` componentとして計画した。
  しかしprimary bboxが付属釣殿をすでに大きく含む。個別Maskをunionしても必要要素の保持を改善しないため、
  この候補は`coherent_group`ではなく`single_form`として扱うのが妥当である。G3へは進めない。

この結果は、建築に付属物があるだけで`coherent_group`にするのではなく、**primary Maskだけでは必要な
componentを保持できない場合**だけcomponent分割を使う、という共通設計の確認になる。料理専用・建築専用の
後処理は追加しない。

同日、ノートルダム5写真・memoryText（入力hashは`ARCH-03`と同じ`11211ecf...4581a`）でもG1を1回実行した。
12候補中2候補が`coherent_group`だった。`c_virgin_fountain_05`は噴水の基壇・水盤と、その上の尖塔・
聖母子像を必須componentとして分けた。`c_roof_slopes_and_spire_09`は屋根勾配と奥の尖塔を必須componentとして
分けた。両者はprimaryだけでは作品の対象が不完全になり、別bboxに必要な形状がある。後者のbboxは少し重なるが、
同一建築の細部であり、重複した主題を別Layerにする候補ではない。いずれもG3へ進めるかは評価者の目視承認待ちとする。

姫路城5写真・memoryText（入力hashは`ARCH-02`と同じ`408395b6...fd05a`）でもG1を1回実行した。12候補中4候補が
`coherent_group`だった。このうち`c1_p3_himeji_main_keep`は大天守・小天守群と天守台石垣を必須componentとした。
石垣bboxには前景の樹木も含まれるため、G3を行う場合は石垣の必要部分を残しつつ背景混入がないことを確認する。
残る3候補（松＋低木、石碑＋景石、左右の松）は、主題を成立させる必須componentではなく、任意の周辺物を
追加する寄せ集めである。`coherent_group`候補としては不採用とし、G3へ進めない。

`scripts/inspect_coherent_group_plan.py`は、保存済みG1 Planだけを読み、primary bboxに各component bboxが
どの程度含まれるかとbbox IoUをprivate artifactへ記録する。Gemini、Mask、Artworkを変更せず、候補を自動で
採否しない。金閣寺では鳳凰＋台座のcontainmentは0%、主建物＋付属釣殿は67.7%だった。ノートルダムの
2候補は0.9%・7.8%、姫路城の大天守＋石垣は4.5%だった。この数値は「主bbox内の重複候補」を人手レビューで
識別する補助であり、G3進行の可否は必要要素・背景混入・最終previewの目視で決める。

### 4.4 建築でのG3 Mask union PoC（2026-09-02）

評価者は、金閣寺の鳳凰＋台座、ノートルダムの噴水＋像と屋根＋尖塔、姫路城の大天守＋石垣について、
component別Mask unionを承認した。各Saved Plan・bboxを再生し、Geminiを再呼出しせずEfficientSAM-Ti ONNXで
G3を実行した。`coherent_group` union直後の2 px gap closingも適用した。これは細い透明gapだけを閉じ、
大きく離れたcomponentを橋渡ししない。

- 金閣寺の鳳凰＋台座は、両componentがexclusiveに39.35%・60.65%寄与した。previewでは鳳凰と台座が
  共に残り、明白な背景混入はない。**暫定pass**。
- ノートルダムの噴水＋像は、両componentが55.75%・44.25%寄与したが、左下に不要な建築片が残った。
  bbox内の背景混入として**暫定fail**。
- ノートルダムの屋根＋尖塔は、両componentが82.14%・17.86%寄与した。必要な屋根・尖塔は残る。間の
  大きな透明gapは2 px closingの対象外であり、橋渡しはしていない。**暫定pass**。
- 姫路城の大天守＋石垣は、両componentが83.75%・13.99%寄与したが、石垣周辺に不要な樹木片が残った。
  bbox内の背景混入として**暫定fail**。

この結果は、`coherent_group` unionが必要componentを保てることを示す一方、bbox内の背景混入やcomponent内の
欠損を自動で検出・拒否できないことも示す。料理・人物・建築に共通のQuality Checkを作る前に、背景片の
カテゴリ別除去や大きな橋渡しを追加しない。

作業ツリーでは、`coherent_group`が成功したcandidateのprivate metricsへ、required componentの予定数・
受理数と、各componentがunionへ独自に寄与した面積比を追加した。これは必須componentがLayerへ実際に
入ったことを評価者が確認する材料であり、比率の固定閾値で候補を自動rejectする規則ではない。背景混入と
意味上の欠損は、引き続きbbox・Mask・最終previewの目視で判定する。

更新後の人物＋ボール2件を同じSaved Plan・bboxで再生したところ、どちらもrequired 2件中2件を受理した。
`c4`は人物11番が91.82%、ボールが8.18%、`c9`は人物4番が94.62%、ボールが5.37%をunionへ独自に寄与した。
これにより、ボールが人物Maskへ偶然含まれたのではないことを確認できる。これはcomponent保持の証跡であり、
`c9`の`border_touch=true`や背景混入の可否を自動で合格にするものではない。

G3で生成したLayer previewは、Codex上の画像確認と評価者の目視で判定する。生成済みpreviewをGeminiへ
再送信するG4は、元写真の送信許可とは別に明示承認が必要なため、建築4件では実行していない。G4の結果を
採否根拠に追加せず、preview・component Mask・入力hashをprivate artifactに残している。


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

## 8. 資料21開始前の実行環境整理（2026-09-02）

### 8.1 目的

`21_AI_AUTONOMOUS_EXECUTION_PLAN.md`の開始条件を満たし、以後のAI品質評価でGemini model、
Segmentation weight、private artifact、検証コマンド、Git比較基準が曖昧にならない状態にする。

### 8.2 入力・実行条件

- code revision: `cc37b064c2570d09e53fc5ae9f86a6719faa7b7b`
  (`feat/ai-general-micro-island-cleanup`)
- `origin/main`: `001a3577a7de57b08078729b5d117aef13c4f678`（fetch後）
- branch差分: currentは`origin/main`に対し10 commit ahead / 39 commit behind。
  資料20・21と索引の未commit変更を保護するため、この時点でcheckout・reset・stash・削除は行わない。
- open PR: #6（micro-island cleanup）と#7（closed-hole fill）はOPEN。#3もOPENだが、
  `feat/ai-mvp-5photos-4layers`をbaseとするperformance PRである。
- private dataset: `locked-regression-6-20260901`の6 caseは入力hash・memoryText hashともPASS。
  architecture A/B台帳は36 runすべて未記入で`technicalEvidenceReady=false`のまま。

### 8.3 Gemini / EfficientSAMの環境修正と機械確認

開始時の`backend/.env`は`GEMINI_MODEL=gemini-3.7-flash`であり、資料21の品質テスト規則に
不適合だった。API呼出し前にローカル非追跡設定を`gemini-3.5-flash-lite`へ変更した。
また、`EFFICIENTSAM_MODEL_PATH`はRepository root起動を前提に`backend/.models/...`を指していたため、
通常の`backend/`起動では二重の`backend/`となった。同ファイルを`.models/efficientsam_ti.onnx`へ修正した。

`backend/.venv`のPython 3.13.13でSettingsを読み、`GEMINI_MODEL=gemini-3.5-flash-lite`、
`MOCK_AI=False`、`SEGMENTATION_BACKEND=efficient_sam_onnx`を確認した。41,365,520 byteの既存ONNX
weightを`EfficientSamOnnxSegmenter`でloadできた。**Gemini API呼出しは0回**であり、この環境確認を
品質採否のrunには使わない。

### 8.4 検証環境

既定の`uv` cacheとOS temp directoryはアクセス拒否となった。さらにRepository rootからのpytest収集は、
Git worktreeではない古い`tmp/ab-parent` copyの`tests`を重複収集する。古いcopyは削除せず保護したまま、
以後のローカル検証は`backend/`をcwdにして、Git管理外の`../tmp/pytest-basetemp`を明示し、
`tests`だけを対象に実行する。

- `python -m pytest -q tests --basetemp ../tmp/pytest-basetemp -p no:cacheprovider`: **66 passed**
  （FastAPI / httpxの既知DeprecationWarning 1件）
- `python -m ruff check .`: **All checks passed**
- `python -m ruff format --check .`: **41 files already formatted**
- `python scripts/validate_contracts.py`: Artwork mock、generate-success mock、整合性とも**PASS**

### 8.5 Codex画像確認・人間判断

- Codex画像確認: 未実施（環境確認で画像artifactを生成していない）。
- 人間判断: 不要（品質・製品方針の判断を含まない環境整理）。

### 8.6 既知の限界と次アクション

この確認はCloud Runのrevision・36件のarchitecture A/B実行・画像品質・PRの採否を証明しない。
architecture v3のA1はBackend/GCPによる固定条件36 run待ちのまま保留とし、AI側で次に独立評価できる
A2 micro-island cleanupのSaved Mask stage-separated replayとCodex画像確認へ進む。

### 8.7 A2 micro-island cleanup — Saved Mask再確認（2026-09-02）

目的はPR #6の`clean_micro_islands`だけを、Semantic PlanningやCompositionの揺れから分離して確認すること。
入力はprivate artifact `micro-island-current/quality-evaluation-20260901-113911` の同一原寸Maskであり、
建築・料理/工芸・人物混在の3 caseを使った。これらの元E2E artifactは過去のmodel条件によるため、
**今回の確認はGeminiを呼ばない決定論的Mask stage replayの証跡だけ**として扱い、資料21の最終E2E採否根拠へ
混ぜない。

既存のreplay JSONを機械再確認した結果、`max_removed_area_ratio=0.005`では全3 caseで
`allComparableRecordsMatch=true`だった。8件のcleanup適用candidateは、実行時metricsと同じcomponent数・
除去面積比・適用可否を再現した。

- 建築: 3件、除去面積比0.000061 / 0.000929 / 0.002900
- 料理/工芸: 2件、0.000008 / 0.001039
- 人物混在: 3件、0.000008 / 0.000076 / 0.000233

同じMaskを`0`で再生したbaselineでは、8件すべてが同じ除去面積比のまま`applied=false`となった。
0.5%の変更は大きく離れたcomponentを結合せず、閾値超過の候補は引き続き`rejected_detached`のまま残す。

Codex画像確認では、建築軸組、工芸ツール、着物人物のRaw Maskと3 caseのcomposition previewを確認した。
人物Maskには主成分外のごく小さい点が残り、0.0076%の除去対象であることを視認した。完成previewでは、
このcleanupに起因すると読める主題の明白な欠損や、離れた対象の橋渡しは確認しなかった。一方、建築previewの
Layer品質、料理previewの対象選定、人物の二重表現・構図は別のSemantic / Mask / Composition課題として残る。

この結果はcleanup処理の決定論性と、保存3 caseにおける局所的な可視安全性を示すが、最終Profileでの
E2E回帰なし、0.5%が全カテゴリで最適であること、作品全体の品質を証明しない。PR #6はOPENのまま、
人間採否は**判断待ち**とする。次のAI側作業はPR #7 closed-hole fillのSaved Mask replayと画像確認である。

### 8.8 A3 PR #7 closed-hole fill — 採否証跡の境界確認（2026-09-02）

資料21を優先し、PR #7の評価対象を「subject componentのSegmentation直後に閉鎖穴を充填する処理」だけへ
限定した。component union後や`close_narrow_mask_gaps`後のhole fillは別のlocal PoCであり、PR #7の採否へ
混ぜない。PR #7のcommit `c1907be`は、この直後の呼出しと単体・パイプラインtestだけを追加している。

機械確認では、閉鎖穴を8 px埋めつつ外部へ開いた穴を残すtestと、PerforatedSegmenterを通すRGBA pipeline
testを実行し、3 passed（22 deselected）だった。生成されたRGBA alphaが同じ`fill_closed_mask_holes`の
再適用で変化しないこともtestで固定されている。Gemini APIは呼ばなかった。

既存の人物+ボール`c4`のSaved Plan / bbox Mask-stage artifactでは、component画素36,444 / 13,960 px、
union 50,404 px、closingとhole fill後50,436 pxで、最終Maskへのhole fill再適用は不変だった。Codex画像確認で
人物とボールは保持され、両者を橋渡ししていない。モンブラン+皿と建築屋根+尖塔の既存previewも確認したが、
これらはcomponent unionまたはgap closingを伴うため、PR #7単独の採否証跡には使わない。

この確認で重要な不足を確認した。既存private artifactはPR #7適用後のcomponent Maskを主に保存しており、
人物・料理/器・建築について「充填前Raw component Mask → 直後の充填後Mask」を同一runで対にしていない。
したがって、保存artifactだけからは各カテゴリでの実際の穴数・追加面積・外部gap保持をPR #7単独で再計測できない。
過去artifactの`gemini-3.7-flash`等のE2E結果は資料21の最終採否根拠にも使わない。

Codex画像確認では、人物+ボールLayerは主題を保持していた。料理previewは皿とモンブランを共に含むが、
component重複のためhole fill単独の改善とは読めない。建築previewには屋根と尖塔の大きな外部gapが残り、
このgapを埋めないこと自体は仕様どおりである。いずれも背景混入・component不足・Compositionの品質を
hole fillの問題へ帰属しない。

よってPR #7の状態は**機械証跡のみ / 人間採否未提示**とする。次アクションは、`gemini-3.5-flash-lite`を
記録する新規評価runで、Raw component Mask、直後のNormalized Mask、穴数、追加面積、外部gap保持を
人物・料理/器・建築ごとに保存してから、Codex画像確認と人間採否へ進むことである。

### 8.9 A3 closed-hole fill — Raw / Normalized component artifactの追加（2026-09-02）

`scripts/replay_closed_hole_fill.py`を追加した。これはSaved Plan・同一入力hash・component bboxから
EfficientSAM-Ti ONNXを直接再生し、**Segmentation直後のRaw Mask**と`fill_closed_mask_holes`直後の
**Normalized Mask**をprivate artifactへ対で保存する評価専用runnerである。Gemini、Quality Gate、
component union、gap closing、Composition、Artwork生成は呼ばない。run.jsonにはinput hash、bbox、
Raw/Normalized画素数、追加・削除画素数、変更の画像端接触、Raw/Normalized hole count、再適用不変性を残す。

人物caseには`set-20-basketball`（input hash `172c08b6...9c12ea`）とSaved Plan
`coherent-group-planning-20260901-052038`を使った。Gemini API呼出しは0回である。

- 選手body: Raw 259,300 px、Normalized 259,408 px。閉鎖穴3件を108 px追加、削除0 px、
  追加画素の画像端接触なし、再適用不変。
- basketball: Raw 22,848 px、Normalized 23,112 px。閉鎖穴1件を264 px追加、削除0 px、
  追加画素の画像端接触なし、再適用不変。

Codex画像確認では、選手のbodyとballのRaw/Normalized Maskで、輪郭外や対象間を橋渡しせず、
内部の小さな透明穴だけが消えることを確認した。人物とballを一つのMaskへunionしていないため、
この画像確認はPR #7のcomponent直後の責務に対応する。

`ruff check`はpass、runnerの実行artifactは
`poc-output/closed-hole-component-replay-20260902-103141`へprivate保存した。ONNX CPUではcomponentごとの
再生に数分を要し、同一artifactを並列・重複実行しないよう1 runずつ監視する。

この結果は人物1 caseの決定論的な穴充填を示すが、料理/器・建築のRaw/Normalized対、4 Layer E2E、
背景混入、最終Profile採否を示さない。次アクションは同じrunnerでfood / architectureのSaved Plan replayを
実行し、3カテゴリの画像確認後にPR #7の人間採否を提示することである。

### 8.10 A3 closed-hole fill — 料理/器componentのRaw / Normalized対（2026-09-02）

料理/器caseには`set-07-food`（input hash `22c1b2f7...81593a`）とSaved Plan
`coherent-group-planning-20260901-130911`を使い、candidate `cand_p2_montblanc_group`の
`p2_plate`と`p2_montblanc_cake`を、人物caseと同じ評価runnerで逐次再生した。Gemini API呼出しは0回である。
artifactは`poc-output/closed-hole-component-replay-20260902-104105`へprivate保存した。

- plate: Raw 341,756 px、Normalized 501,547 px。閉鎖穴1件を159,791 px追加（Rawに対して約46.8%増）、
  削除0 px、追加画素の画像端接触なし、再適用不変。
- montblanc cake: Raw 151,331 px、Normalized 151,993 px。閉鎖穴3件を662 px追加、削除0 px、
  追加画素の画像端接触なし、再適用不変。

Codex画像確認では、cakeは輪郭内の小さな透明穴だけが消えた。一方plateは、Raw Maskで皿の内側に残っていた
大きな領域（料理が写る中央部を含む）までNormalized Maskが埋めた。機械指標上は画像端に接続しない閉鎖穴であり、
アルゴリズムの定義どおりだが、皿を完全な物体として扱うか、料理を別objectとして内側を透明のまま残すかは
思い出表現・Layer意味の判断である。全subject componentへ無条件に適用するPR #7の安全性を、このcaseは
自動でPASSとはできないことを示す。

この結果はcomponent segmentation直後だけを扱い、union / gap closing / Compositionを含まない。plateの大きな
追加が望ましい表現かは人間判断が必要であり、AI側で対象種別の例外、面積閾値、category-specific fallbackを
追加しない。次に建築componentでも同じ対を取得して3カテゴリを揃えた後、PR #7の採否判断を資料21の形式で求める。

### 8.11 A3 closed-hole fill — 建築componentのRaw / Normalized対と評価整理（2026-09-02）

建築caseには`set-08-notre-dame`（input hash `11211ecf...f4581a`）とSaved Plan
`coherent-group-planning-20260901-165243`を使い、candidate
`c_roof_slopes_and_spire_09`の`cmp_roof_gable`と`cmp_distant_spire`を同じ評価runnerで逐次再生した。
Gemini API呼出しは0回である。artifactは
`poc-output/closed-hole-architecture-20260902-110000/closed-hole-component-replay-20260902-105012`へprivate保存した。

- roof gable: Raw 489,999 px、Normalized 497,027 px。閉鎖穴12件を7,028 px追加、削除0 px、
  追加画素の画像端接触なし、再適用不変。
- distant spire: Raw 106,568 px、Normalized 106,634 px。閉鎖穴3件を66 px追加、削除0 px、
  追加画素の画像端接触なし、再適用不変。

Codex画像確認では、roof gableのRaw Maskに屋根稜線内の小さな透明欠損があり、Normalized Maskでは
外部の空や屋根外形へ広がらずに消えた。distant spireも外形・下側の外部空間を橋渡しせず、局所的な透明穴だけが
埋まった。建築2 componentをunionしていないため、この確認はPR #7のcomponent直後の責務に対応する。

人物・建築では局所的な穴充填を確認できた一方、料理/器のplateでは閉鎖領域159,791 pxをforegroundへ変え、
料理が写る皿中央部まで不透明化した。これは外部gapを橋渡しする不具合ではないが、全subject componentへの
無条件適用が常に自然なLayer意味を保つとは示さない反証である。PR #7は**機械証跡・Codex画像確認済み、
人間採否待ち**とする。人物/建築の局所改善だけを理由に採用せず、plateの意味的な扱いを人間が判断するまで
通常Profileへの統合・閾値追加・カテゴリ例外は行わない。

このPoCはSaved Plan / bboxとEfficientSAM-Ti ONNXを固定したstage-separated replayであり、Geminiを呼ぶ
4 Layer E2E、Semantic Planningの正しさ、背景混入、component union、gap closing、作品全体の読みやすさを
証明しない。各componentの入力hash、bbox、Raw/Normalized原寸Mask、面積、hole数、再適用不変性を保存したため、
人間判断後に採用・不採用・追加PoCのいずれにも同じ証跡を引き継げる。

### 8.12 B2/B3 coherent_group — 補正なしRaw aggregationの分離確認（2026-09-02）

Phase Bでは`coherent_group`の「required componentを候補単位へ集約する」仮説だけを評価する必要がある。
既存G3 artifactはcomponent直後またはunion後の`fill_closed_mask_holes`を含むため、PR #7やgap closingと
混ぜず、`union_masks`だけを再生・記録する`replay_coherent_group_aggregation.py`と、入力写真を再利用せず
既存Raw Maskからunionだけを復元する`aggregate_saved_component_masks.py`を追加した。両者は
`fill_closed_mask_holes`、`close_narrow_mask_gaps`、micro-island cleanup、Quality retry、Compositionを実行しない。
Gemini API呼出しは0回である。

人物と料理/器の元写真は、過去PoCのinput hashを持つprivate Raw Mask artifactは残る一方、現在の
`poc-images/`には再生用写真directoryが存在しないことを確認した。人物の再Segmentationを
`poc-images/set-20-basketball`で開始しようとしたが、directory不存在で開始前に停止し、artifactは生成していない。
private入力を別場所から探索・復元・外部送信せず、既存artifactの同一input hashに紐付くRaw Maskだけを使った。

- 人物 `c4_p3_fast_dribbler`（input hash `172c08b6...9c12ea`）: body 259,300 pxとball 22,848 pxを
  補正なしでunionし、282,148 px。両required componentのexclusive寄与は91.90% / 8.10%、aggregateは
  2 component、interior hole 3件。Codex画像確認では人物とballが別componentとして明瞭に残り、
  無関係な橋渡しはない。
- 料理/器 `cand_p2_montblanc_group`（input hash `22c1b2f7...81593a`）: plate 341,756 pxとcake 151,331 pxを
  unionし、493,057 px。exclusive寄与は69.31% / 30.69%、aggregateは2 component、interior hole 46件。
  Codex画像確認では皿外形とモンブラン形状の双方がMaskに含まれる。中央部の透明領域・細部欠損も多く、
  aggregation単独が作品として十分か、hole fillを使うべきかは別仮説として扱う。
- 建築 `c_roof_slopes_and_spire_09`（input hash `11211ecf...f4581a`）: 現存する`set-08-notre-dame`と
  Saved Planを同一hashで再Segmentationした。roof gable 489,999 pxとdistant spire 106,568 pxはともに
  Quality Gateで受理され、補正なしunionは596,567 px、exclusive寄与82.14% / 17.86%、aggregate診断は
  10 component、interior hole 15件だった。CodexのRGBA previewでは屋根と尖塔の双方が残る一方、両者の
  大きな外部gap、屋根稜線の透明欠損、左側の小片が残った。これはunionが必要componentを勝手に接続しないことを
  示すが、背景混入・穴・Layerとしての自然さを解決したものではない。

上記はB2の「required componentが実際にaggregateへ独自画素を寄与するか」の機械証跡と、B3のRaw Mask /
RGBA画像確認である。人物・料理/器・建築すべてでrequired 2件はaggregateに残ったが、料理/器の穴・建築の
大きな外部gapと小片が残るため、**coherent_group全体は通常Profileへ未採用・人間採否待ち**とする。
必要componentを合成できるという個別仮説は支持されるが、背景混入・hole fill・gap closing・Semantic Planning・
4 Layer E2E・Compositionの採否を代替しない。特に料理/器の穴を埋めるかはPR #7の人間判断に従い、
category-specificな補正や閾値は追加しない。

### 8.13 C 背景混入 — ノートルダム噴水の原因分離（2026-09-02）

背景混入の代表failureとして、`set-08-notre-dame`（input hash `11211ecf...f4581a`）の
`c_virgin_fountain_05`を、同じSaved Plan `coherent-group-planning-20260901-165243`とbboxで再生した。
`replay_coherent_group_aggregation.py`はRaw component Segmentationと`union_masks`だけを行い、
hole fill、gap closing、micro-island cleanup、Quality retry、Composition、Gemini APIを実行していない。
artifactは`poc-output/background-intrusion-fountain-20260902/coherent-group-raw-aggregation-20260902-110706`へ
private保存した。

機械計測では、噴水base（bbox `[131,1459,1876,2360]`）658,099 pxと、尖塔・聖母子像
（bbox `[778,0,1379,1472]`）522,444 pxはともに通常Quality Gateを通過した。2 componentのRaw unionは
1,180,543 px、exclusive寄与55.75% / 44.25%、縮小診断は20 component、最大component比97.42%、
interior hole 21件、base側で画像端接触ありだった。従って、empty / full / prompt外だけを見る現行Gateは
この背景片をrejectしない。

Codex画像確認では、元写真の噴水モニュメント本体・尖塔・聖母子像はLayerに残る一方、左下に別の建築片が
明瞭に残った。base componentのRaw Mask単体に同じ片があり、2 component union、hole fill、gap closing、
Compositionの結果ではない。Semantic Planのbase bboxは横方向に広く（0..1000座標で`x=68..977`）、
目的物と周辺建築を同時に含む。原因分類は**広いbboxで背景を許容し、Segmentationがその一部をforegroundとして
採った BBox + Segmentation failure**である。component aggregationはこの背景片を新規に作っていない。

この1 caseは背景混入を面積・border touch・component数だけで自動rejectできる根拠にはならない。対象の建築細部と
背景建築は同じ素材・連続構造であり、単純なarea thresholdやcategory-specific除去を追加すると必要部分を落とす。
次のC PoCでは、Semantic target、bbox、Segmentationのいずれを変えるかを一度に一つに限定し、固定入力で
比較する。現時点では通常Profile・Quality Gate・bbox生成・Mask後処理を変更しない。

### 8.14 Gemini品質runnerのmodel強制とsandbox接続失敗（2026-09-02）

`run_quality_evaluation.py`は従来、実効Gemini modelをartifactへ残さなかった。そのため品質runner本体へ、
`GEMINI_MODEL=gemini-3.5-flash-lite`以外ならAPI呼出し前に停止し、summaryと各run recordへ
`geminiModel`を記録する検証を追加した。これはSemantic Prompt、candidate数、Quality Gate、Segmentation条件を
変えない実行条件の固定である。

変更後、private Kanazawa overlap dataset（写真5枚・memoryText、送信許可済み）を
`physical_layer_v2`・1 runで開始した。artifact
`poc-output/flash-lite-integrated-observation-20260902/quality-evaluation-20260902-111529/summary.json`には
実効model `gemini-3.5-flash-lite`が残り、`success=0/1`、semantic elapsed 0、failure stage `source`、
error type `ValueError`として保存された。これはdatasetの写真名がRepository rootの`poc-images/`を基準に
記録されているのに、`poc-images/kanazawa`をphotos dirに指定して`IMG_5319.png`を見つけられなかった
source設定ミスである。このE2EはSemantic Plan前に止まり、画像はGeminiへ送信されていないため、品質・採否・
failure modeの証拠には使わない。

このdiagnosis中、Sandbox内からの最小非private requestはsocket access deniedで接続できなかった。同じ設定値・
API Key構成をネットワーク許可環境で確認したところ、`gemini-3.5-flash-lite`からresponseを受信できた。
従ってmodel名やKey未設定は原因ではなく、quality E2Eでは許可済みネットワーク環境を使う。private画像は
この疎通確認に送っていない。

次アクションは、同一のKanazawa datasetをdatasetの定義どおりRepository rootの`poc-images/`から読み、
`physical_layer_v2`・1 runをネットワーク許可環境で再実行し、成功/失敗を置換せず別artifactとして保存することである。
その結果は未採用のPR #6/#7/coherent_groupを含む現行統合観測に限り、各変更の独立採否根拠へは混ぜない。

### 8.15 Gemini Flash Lite E2Eのroot実行と停滞停止（2026-09-02）

datasetのphotos dirをRepository rootの`poc-images/`へ直した次の1 runは、EfficientSAM model pathを
root cwdで解決できず、`AiNotConfiguredError`・semantic elapsed 0で停止した。`.env`の
`EFFICIENTSAM_MODEL_PATH=.models/efficientsam_ti.onnx`は`backend/` cwdでは正しい一方、generator serviceが
root cwdで相対解決していたためである。`backend/app/services/generator.py`で相対pathを`backend/`基準へ
正規化し、未設定時は明示的に`AiNotConfiguredError`を返すよう修正した。これはmodel weightの場所だけを
正規化し、AI品質の条件を変えない。

修正後、同じprivate Kanazawa dataset・`physical_layer_v2`・`gemini-3.5-flash-lite`・1 runを、送信許可済み
のネットワーク環境で開始した。Gemini SDKの`Models.generate_content`開始logまでは確認できたが、設定した
request timeout 120秒を大きく超えて11分以上、CPU累積0.016秒・待機thread 1本のままsummary/artifactを
書き出さなかった。再送信と無限待機を避けるため、AIが開始したこのprocessを停止した。成功・failure stage・
画像artifactが揃わないため、このrunは**中断・無効**であり、品質・採否・model比較の証拠に使わない。

この停止は`gemini-3.5-flash-lite`のモデル名またはAPI Keyの不成立を示さない。非private最小requestは同じmodelで
responseを得ている。一方、5枚画像を含むStructured Output E2Eの停滞原因（SDK/ネットワーク/画像payload）は
現時点で確定していない。別model、Mock、candidate数・Prompt・Quality Gate・Segmentation条件への切替は行わない。

次回の停滞箇所を記録できるよう、quality runnerにcase/profile/attemptごとの`stage=generate`、成功時の
`stage=generated`、失敗時の`stage=failed error_type=...`を追加した。private画像・memoryText・provider responseは
stdoutへ出さない。相対model path正規化のunit testとquality runner既存testは5 passed、coherent group / hole fillを
含むfocused testは10 passed、Ruff check / formatはpassだった。次のE2E再試行は、このstage別stdout/timeout証跡を
使い、同じ入力を重複送信しないよう直前のprocess終了を確認してから1回だけ行う。

### 8.16 D/E 候補重複・Composition overlap — 旧artifactの診断のみ（2026-09-02）

`quality-evaluation-20260902-014837`のKanazawa mixed-memory 3 trialを、候補重複とLayer overlapの
**診断用既存artifact**として再確認した。このartifactは`gemini-3.7-flash`で作られており、資料21で固定した
`gemini-3.5-flash-lite`ではない。また、未採用の統合条件を含む過去結果である。したがって、本節は現行Profileの
品質値・採否・baselineとして使用せず、診断に限定する。新規Gemini API呼出しは0回である。

- try 1: 正面の着物人物と背面の着物人物が別source photoから選ばれ、五重塔とscene anchorも含まれた。
  Codex画像確認では、同一人物に見える二つの人物が同一画面に並ぶ。これはcandidate IDの重複ではないため、
  現行のID単位重複排除だけでは検出されない。
- try 2: 背面の着物人物、正面の着物人物、黒い皿、scene anchorが選ばれた。保存済みoverlap診断では
  `c3_lacquer_plate`を背面、`c1_portrait`を前面に置いた組で、背面被覆率0.15655、前面重なり率0.04877だった。
  Codex画像確認では二人物の重複表現が残り、皿と人物の前後関係も作品意図としては判定できない。
- try 3: 同じ二人物と黒い皿、scene anchorが選ばれた。人物を背面、皿を前面に置いた保存済み診断は、
  背面被覆率0.09441、前面重なり率0.21564だった。Codex画像確認では皿が人物の扇の一部へ重なり、
  見た目の干渉は確認できるが、思い出表現として許容すべき重なりかは数値だけで決められない。

これにより、Dの「semantic duplicate候補を観測する」ことと、Eの「Compositionのpairwise overlapを観測する」ことは
できた。一方で、同じ人物の定義、同一momentを残す意図、許容被覆率は人間の作品判断を含む。AI側では名前・source photo・
bbox類似度だけによる自動reject、overlap閾値による自動recompose、category-specific例外を追加しない。現行E2Eが
`gemini-3.5-flash-lite`で完走できた後、固定dataset上でこの診断を再取得し、人間に「重複として除外するか／別momentとして
保持するか」と「干渉として再構成するか」を判断依頼する。

この記録後、backend全testは`67 passed, 1 warning`、Ruff check / formatはpass、`git diff --check`はpassした。
warningは既存のStarlette TestClientにおけるhttpx非推奨警告であり、今回の変更に起因するtest failureはない。

### 8.17 Flash Lite 画像付きStructured Outputの切り分けと5枚E2E再停滞（2026-09-02）

SDK実装を確認した結果、`types.HttpOptions(timeout=120000)`はSDK内部で秒へ変換され、同期httpx requestと
`X-Server-Timeout`へ渡される。retry optionを渡していないためSDK既定の5回retryにもならず、1 requestである。
この確認はローカルinstalled `google-genai 2.19.0`のソースと`HttpRetryOptions`定義で行い、production codeの
品質条件は変更していない。

原因を分離するため、共有fixture `contracts/assets/source-p1.jpg` 1枚・最小JSON Schema・同一
`gemini-3.5-flash-lite`で画像付きStructured Outputをネットワーク許可環境から1回呼んだ。private PoC入力は
送らず、`response_received=true`、elapsed 2,060 msだった。従って、画像入力、Structured Output、model名、
API Key、基本的なネットワーク疎通のいずれか単独が一律に停止するわけではない。

その後、資料21の固定条件どおりprivate Kanazawa 5枚・memoryText・`physical_layer_v2`・repeat 1・
`gemini-3.5-flash-lite`で、stage stdoutを有効にしたE2Eを**この切り分け後の1回だけ**開始した。
`stage=generate case=kanazawa-memory-mix-overlap-prompt profile=physical_layer_v2 attempt=1`とSDKのAFC注意logの後、
138秒時点でCPU累積0.016秒・thread 1本・`stage=generated`なしだった。設定request timeout 120秒を超えたため、
同じprivate入力の重複送信を避けてprocessを停止した。summary/metrics/previewは出力されず、このrunも**中断・無効**で、
品質・採否・比較の証拠に使わない。artifact directoryは
`poc-output/flash-lite-integrated-observation-20260902-retry/quality-evaluation-20260902-120622`にprivate保存した。

この時点で、「1枚最小Structured Outputは約2秒で成功するが、現行runner経由の5枚・大きいschema E2Eは120秒を超えて
待機する」ことまでは再現した。原因は5枚payload、semantic schema/response size、SDKのdirect AFC経路、または
ネットワーク経路の組合せに残る。model切替、Mock fallback、Prompt・candidate数・Quality Gate・Segmentation条件の変更は
しない。次の調査はprivate入力を再送信せず、ローカルでrequest payload size / request構築 / timeout伝播を比較する。

同じ5枚を現行の`thumbnail(max_side=1536)`とPNG inline partへ変換した実測は、raw PNG合計12,800,890 bytes、
Base64相当17,067,856 bytes（16.28 MiB、20 MiBの81.39%）だった。prompt・JSON Schema・HTTP envelopeを加えても
20 MiB上限へ近いが、この値だけでは超過を示さない。GoogleのGenerateContent画像ドキュメントはinline dataの総requestを
20 MB未満とし、大きい場合はFiles APIを案内している。一方、Files API導入はprivate fileの一時保持・削除・runtime境界に
関わる方式変更となるため、この実測だけでは導入しない。payload bytesを減らすJPEG変換もSemantic品質に影響し得るため、
比較PoCと人間採否なしに通常経路へは入れない。

### 8.18 B4 narrow-gap closing — Raw aggregate Maskだけの再生（2026-09-02）

`replay_narrow_gap_closing.py`を追加し、保存済みのRaw aggregate Maskへ`close_narrow_mask_gaps`だけを
適用する比較を行った。component segmentation、component union、closed-hole fill、micro-island cleanup、
Quality retry、Composition、Gemini APIはすべて除外した。対象は人物（人物+ball）、料理/器（plate+montblanc）、
建築（roof gable+distant spire）で、raw / 2 px / 6 pxを同一artifact
`poc-output/narrow-gap-raw-aggregation-20260902/narrow-gap-closing-replay-20260902-121430`へ保存した。

- 人物: raw 282,148 px・2 component・interior hole 3件。2 pxは24 px（0.0085%）のみ追加して1 componentとなり、
  6 pxは400 px（0.1418%）追加して1 componentとなった。いずれも再適用不変。Codex画像確認では2 pxで人物の手元と
  ballを細い接続にし、外形の目立つ変形は見えない。6 pxも接続を保つが、比較対象がRaw Maskだけであるため、
  物理的に一体化すべきかの意味判断は別に残る。
- 料理/器: raw 493,057 px・2 component・interior hole 46件。2 pxでは+1,089/-275 px（変更0.2766%）でcomponent数は2のまま、
  6 pxでは+5,992/-846 px（変更1.3869%）で1 componentになった。Codex画像確認では2 pxから皿内のケーキ輪郭・
  クリーム細部が変わり、6 pxでは内部の透明細部をさらに埋めた。これは「必要component間の狭いgapだけ」を
  無条件に対象化してはいないことを示す。
- 建築: raw 596,567 px・7 component・interior hole 11件。2 pxは312 px（0.0523%）、6 pxは1,251 px（0.2097%）を追加したが、
  component数は7→7→5であり、屋根と遠方尖塔の大きな外部gapは接続しなかった。Codex画像確認でも大きな分離は残り、
  屋根周辺の小さな開口だけが局所的に変化した。

この再生はgap closingの決定論性と、人物では2 pxが局所的な接続を作ることを示す。一方、料理/器での細部変化、
建築の必要gapを解決しないこと、Raw aggregate由来で最終Layerの背景混入を評価していないことから、
`close_narrow_mask_gaps`の通常Profileへの採用・共通px値は**保留**とする。closed-hole fillと同じstageへ混ぜず、
カテゴリ例外・閾値調整・通常値の有効化は行わない。人間が「人物+保持物を一体の物理Layerにしたいか」と
「料理の細部変化を許容するか」を判断した後にのみ、coherent_group限定の追加PoCまたは不採用を決める。

### 8.19 未採用PoCの通常Profile混入防止（2026-09-02）

資料21の「採用品だけを通常Profileへ統合する」条件に対し、現行WIP commit `cc37b064`を再確認した。
PR #7の`fill_closed_mask_holes`、PR #6の`clean_micro_islands`、Composition overlapを抑制する追加instructionは、
PR自体のancestorではないにもかかわらず同WIP commitへ取り込まれ、`physical_layer_v2`の既定経路で有効になり得た。
人間採否待ちの実装を通常挙動として扱えないため、PoC実装・replay artifact・unit testは残したまま、次を
既定`false`のSettings flagで明示分離した。

- `CLOSED_HOLE_FILL_ENABLED`: component直後、union直後、gap closing後のclosed-hole fill。
- `MICRO_ISLAND_CLEANUP_ENABLED`: 一般subjectおよびarchitecture subjectのmicro-island cleanup。
- `COMPOSITION_OVERLAP_INSTRUCTION_ENABLED`: Gemini Composition promptのforeground overlap抑制instruction。

`backend/app/services/generator.py`から各flagをgeneratorへ渡し、false時は元のRaw Mask / 元のComposition promptを
維持する。`coherent_group`のgap closingは既にdefault 0であり変更していない。`.env.example`には設定名だけを記載し、
secretやtrue値を入れていない。これらは採用決定ではなく、**採否が得られるまで通常Profileから外す安全な分離**である。

機械確認として、Settings経由で3 flagがfalseのままgeneratorへ渡るunit testを追加した。PoCを明示有効化した
pipeline testは、closed-hole fill・micro-island cleanupの既存挙動を維持して26 passedだった。default falseの
pipeline testではperforated subjectのinterior holeが残ることを確認し、未採用のhole fillが暗黙に適用されない。
quality runnerのsummaryと各run recordにも3 flagの実効値を`qualityFeatureFlags`として記録するようにしたため、
将来のFlash Lite E2Eを通常Profileと明示PoCで混同しない。focused testは30 passed、backend全testは67 passed、
Ruff check / format、Contract validation、`git diff --check`はpassした。この変更はSemantic Promptの通常値、
candidate数、Quality Gate、Segmentation条件、共通Contractを変更しない。

### 8.20 資料21 §1.1の現行実装監査（途中時点、2026-09-02）

Phase Fの一括リファクタを先取りしないため、`backend/ai/internal_models.py`、`gemini.py`、`assembly.py`、
`quality.py`とprivate observerを、資料21 §1.1の最終設計チェックに対して読取監査した。これはコード変更なし・
Gemini呼出し0回の現状把握である。

- **現時点で確認できるもの**: `kind`は`subject / scene_anchor`、`semantic_role`はsubjectの建築役割、
  `extraction_intent`は抽出意図として内部modelに分離済み。validatorはscene anchorの単一componentと、
  coherent groupの一つのrequired primaryを拒否でき、legacy scene-anchor Saved Planには`extraction_intent`を
  補う互換処理がある。scene anchorはrectangular crop経路でSegmentationしない。component union後のrequired数・
  accepted数・exclusive寄与、Compositionのbottom gapとsubject overlap diagnosticsはprivate artifactへ出せる。
- **未達または採否待ち**: normalization有効時のRaw DiagnosticsとNormalized Diagnosticsを同じ通常E2E artifactへ
  対で残す境界は未実装（今回のreplay scriptsが代替証跡）。coherent_groupの通常Profile採否、許可する
  normalization policy、semantic duplicateの人間判定、unified composition violationと最大1回recomposeのE2E、
  `physical_layer_v3_architecture`の36 run、Locked regression-6の最終Profile確認は未完了である。
- **通常Profileの安全状態**: §8.19のdefault falseにより、採否待ちnormalization / cleanup / overlap promptは
  通常生成に混ざらない。従って、上記未達を既定挙動として扱わず、採用品が揃った時点でのみRaw/Normalized artifact
  境界を統合する。

次のAI側作業は、Flash Lite 5枚E2Eの停止原因をprivate入力を再送信せずに切り分けること、または人間採否待ちの
PR #6 / PR #7 / coherent_group / narrow-gapの決定を反映することである。人間決定前に通常Profileへ戻すことはしない。

### 8.21 Gemini Structured Outputの不要AFC無効化（2026-09-02）

5枚E2Eの停滞logには`Models.generate_content`のdirect automatic function calling（AFC）注意が出ていた。
installed `google-genai 2.19.0`の`GenerateContentConfig`を確認すると、`automatic_function_calling`は未設定または
`disable=false`で有効になる。一方、現行Structured Output呼出しはtool declarationを渡していないため、
`_generate_structured`で`AutomaticFunctionCallingConfig(disable=True)`を明示した。これはmodel、Prompt、
candidate数、Schema、Quality Gate、Segmentation、timeout値を変えず、不要なSDK機能を使わない呼出し設定だけを
固定する変更である。unit testはconfigへ`disable=true`と既存timeoutが渡ることを検証した。

ネットワーク許可環境で共有fixture 1枚・最小schemaを同一`gemini-3.5-flash-lite`・AFC無効で実行し、
1,671 msでresponseを得た。次に共有fixture `contracts/assets/source-p1.jpg`〜`source-p5.jpg`の5枚、
実際の`GeminiSemanticPlanner`・`physical_layer_v2`・Semantic Plan Structured Schema・request timeout 30秒で
呼び、7,724 msで12 candidateの型検証済みPlanを得た。いずれもprivate PoC画像・memoryTextは送信しておらず、
AFC注意logも出ていない。

これにより「多画像 + 現行Semantic Schema + Flash Lite」自体は共有fixtureで完走することを確認した。ただし、
private Kanazawa入力の16.28 MiB Base64相当payload、memoryText、実画像の符号化による停止を解決した証拠ではない。
同じprivate入力を繰り返し送らず、次のprivate E2Eはpayload方式を変える比較PoCまたは外部実行環境の選択後にのみ行う。
focused testは31 passed、backend全testは68 passed、Ruff check / format、Contract validation、`git diff --check`はpassである。

### 8.22 private 5枚JPEG Semantic transport PoC（2026-09-02）

PNG inline payloadによるprivate 5枚E2Eの停滞を、通常Profileへ変更を入れずに切り分けるため、
`probe_gemini_semantic_transport.py`を追加した。このrunnerはSemantic Planningだけを実行し、
`gemini-3.5-flash-lite`以外なら送信前に停止する。画像は既存の`gemini_analysis_max_side=1536`で縮小後、
PoC専用にJPEG quality 85へ符号化する。Segmentation、Layer Selection、Composition、Quality Gate、
通常Profile設定は実行しない。

private Kanazawa case（同一input image hashes、同一memoryText hash）を1回だけ実行した結果、JPEG bytesは
`[367,227, 391,776, 202,379, 455,974, 505,741]`、合計1,923,097 bytesで、Semantic Planは8,511.495 ms、
12 candidates、型検証成功だった。AFCはdisabledであり、前のPNG E2Eに出たAFC注意log・停滞は出なかった。artifactは
`poc-output/semantic-transport-jpeg-20260902/gemini-semantic-transport-20260902-123329/run.json`へprivate保存した。

このrunはtransport stageだけで、PNGとのSemantic品質比較、bboxの妥当性、Mask、4 Layer到達、Composition、
Codex画像確認、人間採否を含まない。初回transport artifactはPlan/bbox previewを保存する改修前に完走したため、
視覚的な採否材料もない。runnerは以後の比較用に`semantic-plan.json`とprivate bbox previewを保存するよう更新したが、
同じprivate入力をただちに再送信しない。JPEG入力を通常Profileへ採用せず、PNGとの比較PoCと人間判断まで**未採用**とする。

### 8.23 AFC無効化後のprivate 5枚PNG Semantic transport（2026-09-03）

§8.22のJPEG transport結果だけでは入力形式を採用できないため、AFC無効化後の**現行PNG inline形式**を同じ
transport runnerで1回だけ再実行した。case、5枚のinput image hash、memoryText hash、`physical_layer_v2`相当の
Semantic Prompt / Schema、`gemini-3.5-flash-lite`は§8.22と同一である。PNG bytesは
`[2,756,330, 2,508,252, 1,613,939, 2,703,249, 3,219,120]`、合計12,800,890 bytes、Semantic Planは
35,208.232 msで12 candidatesを返して型検証に成功した。artifactは
`poc-output/semantic-transport-png-afc-disabled-20260903/gemini-semantic-transport-20260902-205855`へprivate保存した。

Codexは保存済みbbox preview 5枚を確認した。正面／背面の着物人物、建物と庭、黒い皿、モンブラン、庭園内の五重塔と
scene候補はそれぞれ写真上の対象を覆っている。source-02では人物・建物・樹木／通路のbboxが広く重なり、source-05では
scene bboxと五重塔bboxが重なるため、semantic duplicateやforeground/scene anchorの意図はこの段階では未判定である。
Mask、Layer選定、作品全体の良さをこの画像確認から採用判定しない。

JPEG（1,923,097 bytes・8,511.495 ms）とPNG（12,800,890 bytes・35,208.232 ms）は、ともにAFC disabledで
Semantic Planningを完走した。したがって、以前のPNG full E2E停滞は「5枚PNGのSemantic requestが必ず不可能」ではなく、
不要AFC経路を含む旧呼出し条件で発生した可能性が高い。ただし一回ずつのtransport値は品質・ばらつき比較ではなく、
JPEGのSemantic品質優劣やfull E2E成功を示さない。通常Profileの画像符号化はPNGのままとし、次はAFC無効化後の
PNG full E2Eを別artifactへ1回だけ実行してSegmentation以降を確認する。

### 8.24 AFC無効化後のprivate 5枚PNG full E2E — 1回観測（2026-09-03）

§8.23でSemantic stageが回復した後、同一Kanazawa case・`physical_layer_v2`・`gemini-3.5-flash-lite`・
PNG inline入力・repeat 1を別artifactでfull E2Eした。run summaryは`qualityFeatureFlags`として
`closedHoleFillEnabled=false`、`microIslandCleanupEnabled=false`、`compositionOverlapInstructionEnabled=false`を
明記し、未採用PoCを通常Profileへ混ぜていない。runは`success=1/1`、4 Layer、Semantic 26,871.094 ms、
Composition 4,509.619 ms、total 137,349.406 msで完走した。artifactは
`poc-output/flash-lite-integrated-afc-disabled-20260903/quality-evaluation-20260902-210340`にprivate保存した。

機械計測では、scene anchor `cand_05`、背面の着物人物 `cand_02`、craft frog dish `cand_03`、
stone lantern `cand_11`が最終4 Layerとなった。前面の着物人物・建物・モンブラン等は`not_single_component`で
不採用となり、micro-island cleanup / closed-hole fillをoffにした現在の通常Profileと整合する。subject overlapは
stone lantern（back）/ craft frog dish（front）だけで、back obscured 0.22514、front overlap 0.26552だった。
bottom gapはdish 0.03050、他3 Layerは0付近、recomposeは発生していない。

Codex画像確認では、背面の着物人物Maskと石灯籠Maskは対象を認識でき、dish Maskは黒い皿全体を含む。最終compositionは
夜の庭を背景に人物・石灯籠・皿を置くが、石灯籠が画面中央で過大、皿が右下を大きく占め、両者が視覚的に競合する。
人物は背面だけで、皿は「frog dish」より物体全体として強く見える。4 Layer到達・Contract成功でも、
思い出表現として読みやすいとはCodexだけで判定できない。したがって本runは**機械証跡・Codex画像確認済み、
通常Profile品質の採用根拠には未使用（人間判断待ち）**とする。

この1回観測はAFC無効化によってfull E2Eが完走可能になったことを示すが、確率的なProfileの一貫性、
PNG/JPEGの品質差、未採用normalizationの採否、semantic duplicate、Composition overlapの許容値、
Locked regression-6での品質を証明しない。AFC無効化はSDKの不要機能を止める実装修正として維持し、
品質Profileの採否は最低3 runと人間目視を経るまで確定しない。

### 8.25 AFC無効化後のprivate 5枚PNG full E2E — 通常設定3回の最小反復（2026-09-03）

資料21の確率的条件の最小3 runを満たすため、§8.24と同じcase・`physical_layer_v2`・PNG inline入力・
`gemini-3.5-flash-lite`・未採用3 flagすべて`false`で、別artifactに追加2回を連続実行した。新規runは
`poc-output/flash-lite-integrated-afc-disabled-20260903-repeat/quality-evaluation-20260902-210927`へprivate保存し、
`success=2/2`、いずれも4 Layer、failure stageなしで完走した。§8.24と合わせて、同一通常設定での最小反復は
**3/3 successful E2E**である。

| run | Semantic ms | Composition ms | total ms | final subject overlap | Codex composition確認 |
| --- | ---: | ---: | ---: | --- | --- |
| §8.24 / try 1 | 26,871.094 | 4,509.619 | 137,349.406 | lantern/dish: back 0.22514, front 0.26552 | 灯籠と皿が競合 |
| §8.25 / try 1 | 26,816.472 | 4,464.269 | 104,899.066 | lantern/dish: back 0.34900, front 0.10110 | 灯籠を皿が隠す |
| §8.25 / try 2 | 23,463.233 | 3,996.686 | 111,112.099 | lantern/dish: back 0.39669, front 0.18343 | 灯籠を皿が隠す |

追加2回の最終Layer roleは、ともに夜の庭のscene anchor、背面の着物人物、工芸の黒い皿、石灯籠だった。候補IDと
人物の最終scaleには揺れがあるが、黒い皿全体が右下を大きく占め、石灯籠に重なる点は3回共通である。Codexは
追加2枚の`composition-preview.png`と、生成時のprivate Mask previewを確認した。人物と灯籠の切抜きは概ね対象を
追えている一方、皿はカエル意匠だけでなく皿の輪郭全体を強く含むため、構図の主要要素として過大に見える。
機械diagnosticsには`recomposed=false`しか記録されず、この可視的な問題を自動的に解消していない。

よって、AFC無効化後の通常PNG経路は「3/3でAPI/Schema/4 Layer生成が完走する」ことまでを確認したが、
**作品品質は3/3とも採用不可候補**である。資料21の順序に従い、ここでComposition prompt、overlap閾値、
candidate選択、normalization flagを自動変更しない。次のprofile変更・品質採否は、人間が3枚のprivate previewを
比較して「皿と灯籠の重なり・皿の大きさが許容可能か」を判断してから進める。

変更後の機械検証は、`backend/`で`pytest -q tests --basetemp ../tmp/pytest-final-20260903 -p no:cacheprovider`を
実行して**68 passed**（既存FastAPI/httpx deprecation warning 1件）、変更対象の`backend`および新規／更新PoC scriptに
対するRuff check / formatで**pass**、`scripts/validate_contracts.py`で**pass**、`git diff --check`で**pass**だった。
Repository全`script/`のRuffは、今回触れていない既存PoC scriptのRUF100 / DTZ005 / BLE001とformat差分で失敗するため、
この既存状態を今回のPoC変更へ自動整形で混ぜていない。

### 8.26 AI側で解消できない判断・担当外入力（2026-09-03）

§8.25の通常PNG 3 runは機械的には完走したが、黒い皿が石灯籠を遮蔽する構図を「思い出作品として許容するか」は
数値やCodexだけでは決められない。人間へ採用 / 不採用 / 保留 / 追加PoCの判断を依頼する。採用であっても、
§8.19でdefault falseに分離した未採用PoCを自動的にtrueへ戻すことはしない。各PoC（PR #6、PR #7、
coherent_group、narrow-gap）も、既存の機械証跡とCodex画像確認は揃っているが、意味上の採否は未判断である。

さらに資料21 Phase A1のarchitecture v3 A/Bは、baseline/candidate × Locked regression-6 × 各3回の36 runを
Cloud Runで実行することが完了条件であり、AI担当はdeploymentや実行条件を変更しない。private実行台帳は36件すべて
未記入で`technicalEvidenceReady=false`のままである。Backend/GCP担当から、固定revision・CPU 1・memory 2 Gi・
concurrency 1・timeout 600秒・`efficient_sam_onnx`・`gemini-3.5-flash-lite`、およびrunごとのartifact /
Contract / failure stageを揃えた台帳返却が必要である。

したがって、AI側は通常Profileへの品質変更、architecture v3採用、PR #6 / #7の採用、coherent_group / narrow-gapの
有効化を行わず、人間判断とBackend/GCPの技術証跡を待つ。受領後は資料21の順序で資料19へ判断を記録し、該当項目だけを
次工程へ進める。

### 8.27 D1 semantic duplicate — Saved Planの同一写真bbox診断（2026-09-03）

Phase Dの最初の材料として、`analyze_semantic_duplicate_pairs.py`を追加した。Saved Semantic Planだけを入力に、
同じ`sourcePhotoIndex`の候補component bbox間について最大IoUと小さい方のbboxに対する包含率を記録する。
Gemini API、Segmentation、通常Profile、candidate選択、Quality Gateは一切実行・変更しない。出力には
`automaticRejection=false` / `automaticDecision=review_required`を明記し、bboxの重なりだけでduplicateを決めない。

§8.24〜§8.25の同一Kanazawa case・`physical_layer_v2`・`gemini-3.5-flash-lite`の3 successful E2Eから保存済み
Semantic Planを読んだ結果、同一写真内の重複bbox pair数は順に7、9、8だった。3 runすべてで、工芸写真の
「黒い皿／蒔絵の器」候補と「皿上のカエル意匠」候補は、小さい意匠bboxの**包含率1.0**になった。候補IDはrunごとに
揺れるが、try 1は`cand_05`（皿全体）/ `cand_12`（カエル意匠）、try 2は`c_craft_plate` /
`c_frog_design`である。最終4 Layerは3 runとも皿全体を採用し、意匠候補は採用されなかった。

Codexはtry 1のsource-03 bbox previewを確認した。皿全体の赤bboxに、カエルと音符を囲む青bboxが完全に含まれる。
これは「皿全体とその装飾詳細」を別Layerにした場合の重複候補として明瞭だが、写真内の細部を別の思い出として残すべきかは
機械的には決められない。scene anchorと前景候補の包含も各runに複数あるが、背景上の前景は設計上あり得るため、
同じ診断をduplicate確定に使わない。

artifactは`poc-output/semantic-duplicate-diagnostics-20260903/kanazawa-try0.json`〜`kanazawa-try2.json`にprivate保存した。
この診断は別写真に写る同一人物・同一建築、画像内容の意味的な近さ、最終Layerが重複として不自然かを検出しない。
したがって、自動reject・Semantic Prompt変更・candidate数変更を行わず、人間が「皿全体とカエル意匠を同時採用する場合を
重複とみなすか」を判断する材料としてのみ保留する。

### 8.28 E1 Unified Composition Diagnostics — 観測のみの統合（2026-09-03）

Phase E1のため、`diagnose_composition_layers`を`backend/ai/assembly.py`へ追加した。`PhysicalReadyDiagnostics`の
private field `composition_layers`へ、正規化後のLayerごとの`candidate_id`、kind、`layer_index`、`x / y / scale`、
表示幅・高さ、`left / top / right / bottom`、`within_canvas`を記録する。既存のbottom gap、subject overlap
(`back_obscured_ratio` / `front_overlap_ratio`)、recompose回数、補正量と同じprivate diagnosticに揃うため、
次のE2E artifactではCompositionの観測値を分散させず確認できる。

これは**観測専用**である。自動failure、overlap閾値、candidate選択、Gemini Prompt、recompose条件、
Canvas clamp、Artwork Contractは変更していない。正規化後にCanvas端へ置かれたLayerを浮動小数の丸め誤差で外側と
誤記しないよう、`within_canvas`だけに`1e-9`の比較許容差を使う。実際の座標や保存Artworkを補正するものではない。

§8.24〜§8.25の3 successful E2Eの既存`artwork.json` / asset manifestを同じ表示式で再計算した。全runで
`layerIndex=0,1,2,3`、最小left=`0.024344569288`、最小top=0、最大right=`0.975655430712`、最大bottom=1であり、
許容差内のCanvas外Layerは0件だった。従って、§8.25の見た目の問題はCanvas boundsではなく、皿と灯籠の前景遮蔽である。
既存artifactは新field追加前の生成なので、`composition_layers`自体は次のE2Eから出力される。過去3 runを無目的に
再送信せず、計算可能な既存Artifactを証跡に使った。

機械検証はComposition関連focused test 34 passed、backend全test 68 passed（既存FastAPI/httpx deprecation warning
1件）、変更対象Ruff check / format pass。PocDebugObserverのtestで`composition_layers`がprivate
`physical-ready.json`へだけserializeされることを確認した。Codex画像確認は§8.25の3 previewを継続利用し、
新しい画像生成・外部VLM送信は0回である。この変更はComposition品質を改善・採用する証拠ではなく、E2/E3の
最大1回recompose PoCへ進む前の観測基盤である。

### 8.29 人間判断の反映 — 通常Profile / semantic duplicate（2026-09-03）

人間判断を次のとおり受領した。

- **通常Profile品質: 採用。** §8.24〜§8.25の`physical_layer_v2`・PNG inline・
  `gemini-3.5-flash-lite`・未採用3 flagすべて`false`の3 successful E2Eを、通常Profileの品質証跡として採用する。
  皿と灯籠の遮蔽は、人間目視で許容された。これは、そのrunでoffだったclosed-hole fill、micro-island cleanup、
  Composition overlap instructionを採用・有効化する判断ではない。これらは各PoCの人間採否が得られるまで既定falseを維持する。
- **皿と意匠: 重複。** カエル等の意匠を含む皿全体を1 Layerとする。§8.25の3 runはすべて皿全体を最終4 Layerへ採用し、
  意匠だけの候補は最終Layerへ採用していないため、この判断と一致する。`analyze_semantic_duplicate_pairs.py`は今後も
  review材料として保持するが、bbox包含だけから他カテゴリのdetail候補を自動除外する一般規則は、未評価の意図的詳細や
  別写真の同一主題を壊し得るため導入しない。新しいsemantic duplicateが最終Layer候補になった場合は、同じく
  機械証跡・Codex画像確認・人間判断で個別に扱う。
- **architecture A/B: 36 runをBackend/GCP担当へ依頼する。** 依頼文を下記に確定した。AI担当はCloud Run deployment /
  revision / runtime条件を変更せず、記入済みprivate台帳を受け取ってから集計・Codex画像確認・人間採否へ進む。

> 件名: AI品質 architecture v3 A/B評価 — Cloud Run固定36 runの実行依頼
>
> `poc-output/locked-regression-6-20260901/architecture-ab-run-sheet.json` の36 runを実行してください。
> baselineは`cedb1a6804823871cd00449f79ff2d9ef7edec15`・`physical_layer_v2`、candidateは`43b0e4f`で、
> ARCH-01〜03のみ`physical_layer_v3_architecture`、NONARCH-01〜03は`physical_layer_v2`です。各variant ×
> 6 case × 3回を、同一variant内では同一Cloud Run revisionで実行してください。
>
> 固定条件は `GEMINI_MODEL=gemini-3.5-flash-lite`、`SEGMENTATION_BACKEND=efficient_sam_onnx`、CPU 1、
> memory 2 Gi、concurrency 1、timeout 600秒です。実行前にこれらと異なる条件が必要になった場合は、実行せず先に
> AI担当へ共有してください。Secret、写真、memoryText本文は台帳・Git・公開ログへ書かないでください。
>
> 各runへ、Cloud Run revision、secretを含まないenvironment fingerprint、4 Layer成功可否、Contract validation、
> failure stage、private artifact directoryを記入してください。artifactにはSemantic Plan、candidate rejection、
> bbox/component diagnostics、Mask/RGBA Layer、composition preview、Artwork/Asset Manifest、Contract validation、
> stage elapsed/failure stageを揃えてください。完了後は更新済みprivate台帳をAI担当へ返してください。

この判断により通常Profileの品質採否は明確になった。一方、PR #6 / #7、coherent_group、narrow-gap、
background intrusion、architecture v3の採否、E2最大1回recompose、Locked regression-6 + Supplementalの最終確認は
未完了である。速度目的のcandidate数、Semantic Prompt、Quality Gate、Segmentation条件は変更しない。

### 8.30 E2/E3 Compositionの現行採用方針（2026-09-03）

§8.29の人間判断により、§8.25で観測した皿／灯籠のsubject overlapは通常Profileで**許容**する。したがって、
`back_obscured_ratio` / `front_overlap_ratio`はE1でprivate観測を継続するが、根拠のない閾値を置いて自動failureや
自動recomposeの条件にはしない。Canvas boundsは§8.28で3 runすべて許容差内、bottom gapもdish以外を含めて
既定のphysical制約内だったため、今回の通常Profile採用に追加のComposition変更は不要と判断する。

一方、下端gapが`PHYSICAL_MAX_BOTTOM_GAP`を超える場合は、既存実装が全Layerをまとめて**最大1回だけ**
`composer.recompose`へ渡す。再構図後もgapが残る場合はGeminiを再度呼ばず、決定論的な`clamp_bottom_gaps`で
下げる。この上限は`test_physical_v2_uses_rectangular_scene_anchor_and_limits_floating`で`compose_calls=1`、
`recompose_calls=1`、最終gapが0.30以下になることを確認済みである。これは個別Layerごとの反復再構図をしない
E2/E3の安全条件として維持する。

この判断は「すべてのoverlapが常に許容」と一般化するものではない。新しいcaseで人間が不自然と判断する遮蔽、
Canvas外、または未解決のbottom gapが出た場合は、E1 unified diagnosticsをartifactへ残してから、
複数violationをまとめた最大1回recompose PoCを別仮説として行う。現時点ではPrompt、閾値、candidate数、
Segmentation条件を追加変更しない。

### 8.31 採否・通常Profile混入の統合監査（2026-09-03）

資料21のPhase A〜Eについて、現在のworktree、private artifact台帳、open PRと通常Profileの実効設定を
突合した。これは新しいGemini API runや品質変更を行わない監査である。`git diff --check`、backend test
`69 passed`、Contract validationはpassした（FastAPI/httpxの既知deprecation warning 1件のみ）。

| 項目 | 現在の採否 / 状態 | 根拠と通常Profileへの扱い |
| --- | --- | --- |
| 通常Profile `physical_layer_v2` | **採用** | §8.24〜§8.25の同一条件3/3 E2E、実効`gemini-3.5-flash-lite`、人間目視採用。 |
| 皿全体とカエル等の意匠 | **採用（対象固有のsemantic duplicate判断）** | §8.29の人間判断。皿全体を1 Layerとし、bbox包含だけによる他カテゴリへの一般自動rejectは導入しない。 |
| E1 diagnostics / 現行overlap扱い | **採用** | 観測のみの`composition_layers`とsubject overlap diagnosticsを維持。§8.25の皿／灯籠遮蔽は通常Profileで許容し、閾値・Prompt変更はしない。 |
| PR #6 micro-island cleanup | **保留** | Saved Mask replayとCodex画像確認は済みだが、独立した人間採否が未取得。flagは`false`。PR #6はopen。 |
| PR #7 closed-hole fill | **保留** | 人物・建築には局所的効果がある一方、皿では内容物まで充填した。全体有効化の人間採否が未取得。flagは`false`。PR #7はopen。 |
| `coherent_group` | **保留（残課題明確）** | component unionは必須要素を残せる例があるが、甘味セットでは穴・背景片が残った。通常Profileには未統合。 |
| narrow-gap closing | **保留（不採用寄り）** | 人物では局所的、料理では細部を変形、建築では解決しなかった。カテゴリ横断の安全値が未確定で、既定値は0。 |
| 背景混入 | **保留（原因分類済み）** | ノートルダムの再生で、広いbboxとSegmentationによる建築片の混入を確認。製品として何を残すかの判断なしに自動除外しない。 |
| architecture v3 | **保留（外部技術証跡待ち）** | Cloud Run固定36 run台帳は全件未記入、`technicalEvidenceReady=false`。Backend/GCP担当への依頼文は§8.29に確定済み。 |
| E2/E3 追加recompose PoC | **現時点は不要** | 採用済み通常Profileで観測したoverlap / bounds / bottom gapは許容済み。新しい未許容violationが出た場合だけ別仮説として行う。 |

実装の通常値も再確認した。`closed_hole_fill_enabled=false`、`micro_island_cleanup_enabled=false`、
`composition_overlap_instruction_enabled=false`であり、採否待ちのPR #6 / #7とoverlap Promptが通常生成へ
混入しない。`GEMINI_MODEL`を品質テストで使うrunnerは`gemini-3.5-flash-lite`以外をAPI呼出し前に拒否する。

この監査は、PR #6 / #7の採否、`coherent_group`の採用、背景混入の製品方針、architecture v3のA/B結果、
Locked regression-6 + Supplementalでの最終確認を代替しない。次のAI側作業は、Backend/GCPから返る36 run台帳の
集計・Codex画像確認、または未決の各品質項目に対する人間判断の反映である。

同じ台帳を`summary-current-20260903.json`へ再集計した。36 runすべてでCloud Run revision、非secret
environment fingerprint、4 Layer可否、Contract validation、artifact directory、failure stageが未記入で、
`technicalEvidenceReady=false`、不足記録は216件（各run 6項目）だった。この機械結果は実行失敗ではなく、
Backend/GCP実行がまだ始まっていないことの確認である。写真・memoryText本文・secretは読み出していない。

### 8.32 Supplemental caseの固定参照とCodex再確認（2026-09-03）

最終Profile確認でLocked regression-6の外に置くfailure modeを、private artifactへの参照として固定した。
これは新しい入力を作成・送信せず、既存のSaved Plan / Maskを後続の独立評価へ紐付ける準備である。最終Profileへ
採用するためのE2Eを実行する場合は、同じprivate入力で`gemini-3.5-flash-lite`を使い、各caseを最低3回記録する。

| supplemental ID | failure mode | private参照 | 現在の評価用途 |
| --- | --- | --- | --- |
| SUP-01 | semantic duplicate / Composition overlap | `flash-lite-integrated-afc-disabled-20260903*` | 採用済み通常ProfileのKanazawa 3 run。皿全体を1 Layerとする人間判断とE1 diagnosticsを確認する。 |
| SUP-02 | bbox内背景混入 / architecture断片 | `background-intrusion-fountain-20260902/.../c_virgin_fountain_05.png` | 目的物と無関係な断片を分ける背景混入PoCの固定例。 |
| SUP-03 | `coherent_group`の必須componentと内容欠損 | `coherent-group-food-case`、`coherent-saved-raw-food-20260902` | 皿＋料理のcomponent保持と、器内の穴・背景片を別々に判定する。 |
| SUP-04 | closed-hole fill | `closed-hole-component-replay-20260902-*` | 人物・料理/器・建築のclosed holeだけをstage-separated replayで比較する。 |
| SUP-05 | narrow-gap closing | `narrow-gap-raw-aggregation-20260902` | 人物・料理・建築を同じ0 / 2 / 6 px条件で比較する。 |

CodexはこのうちSUP-02とSUP-05の既存画像を再確認した。SUP-02では主要な尖塔・彫像・台座は残る一方、
左下に主構造から分離した建築断片があり、作品Layerとしては不要な混入に見える。これは「背景断片を一律に閾値で
削除できる」ことを示さず、semantic target / bbox / Segmentationのどこで除外するかを分けてPoCする必要がある。
SUP-05のモンブラン＋皿では、`gap=0`の中央の透明な輪郭・細部が`gap=6`でほぼ白く埋まり、細部の形状を大きく
変えていた。machine recordでも`gap=6`は変化率`0.0138686`、component数2→1、内部hole数46→13であり、
この見え方は通常Profileのnarrow-gap closingを採用しない既存判断を補強する。Gemini API呼出しは0回である。

この参照表は最終品質ベースラインの完了証跡ではない。各supplemental caseについて、ローカル機械計測・Codex画像確認・
人間判断を揃え、Gemini APIを使う最終確認は`gemini-3.5-flash-lite`だけで行う必要がある。

### 8.33 資料21 §1.1 最終設計への現行静的監査（2026-09-03）

最終設計チェックを早期に一度だけ静的監査した。これは採否待ち機能を統合する変更ではなく、Phase Fで埋めるべき差分を
先に固定するための確認である。Gemini API・画像生成は使用していない。

| 最終設計観点 | 現行状態 | 判断 |
| --- | --- | --- |
| `subject` / `scene_anchor`の経路分離 | `kind`を内部Modelで分離し、scene anchorは単一bboxの矩形crop、subjectだけをSegmentationする。 | 実装済み。 |
| `kind` / `semantic_role` / `extraction_intent`の整合 | 内部Pydantic validatorはscene anchorとcoherent groupの無効組合せを拒否し、旧Saved Planのscene anchorだけ互換補完する。 | 一部実装。通常`physical_layer_v2`のStructured Outputは`extraction_intent`を要求せず、default／互換補完に依存する。 |
| scene anchor数 | Promptは最大2候補、Layer Selectionは最大1件を選ぶ。 | Selection側は実装済み。Semantic Plan validatorで「最大2」を強制していないため最終確認では未達。 |
| Raw / Normalized diagnostics | Segmentation直後とaggregate後のMask診断・`mask_cleanup`は残る。 | 未達。Rawと補正後を同一artifactで対にした明示的なdiagnostics境界は未実装。 |
| component aggregation | `coherent_group`はcomponent別Mask、required受理数、exclusive寄与を記録する。 | PoC実装済み・通常Profile未採用。single_formを含む共通の集約追跡は最終設計統合時に確認する。 |
| intent別品質条件 | single_formは連結component 1を要求し、coherent groupはrequired component保持を記録する。 | 前者は通常Profile、後者はPoCに留まる。 |
| Normalization policy | closed-hole / micro-island / overlap Promptは明示flagで既定false。 | 採否待ちを隔離済み。Normalization適用前後の完全なartifact記録は未達。 |
| semantic duplicate | bbox包含をprivate診断でき、皿＋意匠は人間判断済み。 | 一般自動rejectは入れない。通常pipelineでの候補ごとの診断統合は未達。 |
| Unified Composition / recompose | Layer座標・bounds・overlapをprivate記録し、bottom gapは最大1回recompose後に決定論補正する。 | 現行採用範囲では実装済み。未許容overlap等を統合violationとしてfailure / recomposeへ渡す規則は、根拠がないため未実装。 |

したがって、現時点でPhase Fの一括統合を開始しない。採用が確定している通常Profile、皿＋意匠の対象固有duplicate判断、
E1観測と現行bottom-gap上限だけを維持し、PR #6 / #7、`coherent_group`、narrow-gap、背景混入、architecture v3の
採否と最終E2Eが揃ってから、上表の未達を一つずつ独立仮説として扱う。candidate数、Semantic Prompt、Quality Gate、
Segmentation条件は変更しない。

### 8.34 最終品質runの入力証跡補強（2026-09-03）

`run_quality_evaluation.py`は、これまでcase ID、写真ファイル名、memoryTextをprivate bundleへ残す一方、run単位の
summary / `metrics.json`に入力同一性を直接照合するhashを持たなかった。最終Profileの固定dataset・Supplemental
caseを監査可能にするため、品質挙動を一切変更せず、全成功／失敗recordへ次を追加した。

- `photoCount`
- `inputHash`: 順序を保った各写真BinaryのSHA-256をLFで連結し、再度SHA-256した値
- `memoryTextHash`: APIへ送る正確なUTF-8 memoryTextのSHA-256

写真Binary、memoryText本文、secretはrecordへ書かない。`input_hash`の写真順序を入れ替えるとhashが変わること、
同一／異なるmemoryTextのhashが期待どおり同一／異なることをunit testで確認した。Real AI・Gemini API・画像生成は
この変更で0回である。

`backend/`でquality runner focused testは**5 passed**、backend全testは**70 passed**、Contract validation、
`git diff --check`はpassした。Ruff checkは対象2 fileで既存の`E402` / `I001`（`sys.path`設定後の動的importによる
runner既存構造）を除外してpassした。Ruff format全体checkはこの変更より前から`run_quality_evaluation.py`の既存行を
整形対象として報告するが、資料21の品質作業へ無関係な大量formatを混ぜないため、この時点では変更していない。
次にこのrunnerで最終品質E2Eを行う場合も、実効`GEMINI_MODEL=gemini-3.5-flash-lite`の既存ガードを通過しなければ
API呼出し前に停止する。

同ガードを将来の変更で弱めないため、`GEMINI_MODEL=gemini-3.7-flash`を注入したSettingsでquality runnerを
起動するunit testを追加した。datasetの読込後、写真読込・output directory作成・`build_generator`・Gemini API呼出しの
いずれよりも前に、`gemini-3.5-flash-lite`必須の`ValueError`で停止することを確認した。通信・画像送信は0回である。
backend全testは**71 passed**、追加testのRuff check / format、`git diff --check`はpassした。

### 8.35 architecture A/Bの仮完了判断（2026-09-03）

人間判断により、Cloud Run固定36 runはこの時点では追加実行せず、以前のCloud Run計測結果と本フェーズでの
ローカル機械検証・Codex画像確認を踏まえて**仮完了**として扱う。台帳が36件未記入である事実は変わらず、
`technicalEvidenceReady=false`を成功結果へ読み替えない。

この判断は`physical_layer_v3_architecture`を通常Profileへ採用する決定ではない。通常Profileは引き続き
`physical_layer_v2`であり、architecture v3、PR #6 / #7、`coherent_group`、narrow-gapのfeature flagや
Semantic Prompt、candidate数、Quality Gate、Segmentation条件は変更しない。architecture v3の採用／不採用と
Cloud Run 36 runの完全な技術証跡は、採用品を内部設計へ統合する時点で再確認する。

仮完了の根拠は、以前のCloud Run artifactでarchitecture候補が3 caseすべて4 Layerへ到達した観測、
non-architecture caseの比較材料、保存済みMask / Layer / composition previewのCodex確認、および現在の
Locked regression-6台帳・入力hashの整合性である。これは確率的なA/Bを3回ずつ比較した証拠、現行Cloud Run
revisionでの再現性、architecture v3の非architecture回帰なしを最終的に証明するものではない。統合前に同じ
`gemini-3.5-flash-lite`・`efficient_sam_onnx`・固定runtime条件で確認する。

### 8.36 PR #6 / #7の静的適用範囲監査（2026-09-03）

保存Maskの見え方だけでなく、open PRの実装が通常Profileへどう入るかを静的確認した。Gemini API・画像生成は
使用していない。

- PR #6のcommit `4189159`は、architecture専用だった`clean_architecture_micro_islands`を
  一般subjectへも使う`clean_micro_islands`へ一般化し、`physical_layer_v2`の全subjectへ暫定0.5%を
  **無条件適用**する差分である。単独でmergeすると、Saved Mask replayで見た挙動が採否前でも通常Profileへ入る。
- PR #7のcommit `c1907be`は、各componentのSegmentation直後に`fill_closed_mask_holes`を
  **無条件適用**する差分である。窓・腕だけでなく、皿の内容・開口部も同じ規則で充填され、flagやcategory分岐はない。
- 現行worktreeは採否分離のため、両方を`micro_island_cleanup_enabled=false`、
  `closed_hole_fill_enabled=false`で明示guardしている。falseの通常ProfileではPR #6 / #7のMask変更は実行されず、
  `composition_overlap_instruction_enabled=false`も同様に通常Promptへ混入しない。

この静的確認は、PR #6 / #7の品質採否を決めるものではない。しかし、**人間が採用と判断するまで各PRを単独で
通常Profileへmergeしてはならない**こと、採用時も既定値・適用段階・artifactのRaw/Normalized記録を独立に
確認すべきことを明らかにした。従って、現在の「PR #6は保留、PR #7は不採用寄り」というAI推奨を維持する。

### 8.37 人間判断の反映 — 物理Layerの連続性・穴なし方針（2026-09-03）

人間判断により、3DプリントするLayerでは飛び地と閉鎖穴を許容しないことを製品方針として採用した。
この方針を既存PoCへ対応付けると、PR #6とPR #7は次の限定された意味で**採用**する。

- **PR #6 micro-island cleanup: 採用。** `MASK_MICRO_ISLAND_MAX_AREA_RATIO=0.005`以下の分離成分だけを
  除去し、最大主成分を一つのLayerとして使えるようにする。閾値を超える大きな分離は、勝手に橋を描かず
  `not_single_component`としてcandidateを不採用にする。従って、この処理は「すべての分離を結合する」ものではなく、
  小さな飛び地を除去して救済し、意味的な別物体を含む大きな分離を物理Layerへ出さない処理である。
- **PR #7 closed-hole fill: 採用。** 外側背景へ接続しない透明領域をforegroundとして充填する。腕の内側だけでなく、
  皿の内側、建築の窓・開口も同じLayer実体として埋める。外側へ開いたgapや別componentを橋渡しする処理ではない。
  §8.11で観測した皿の+46.8%も、この製品方針では副作用ではなく意図した形状変更として扱う。

この採用により、`Settings`と`.env.example`の既定を
`micro_island_cleanup_enabled=true`、`closed_hole_fill_enabled=true`へ変更した。`backend/.env`にこの二つの
明示上書きがないこと、実効Settingsが両方`True`、overlap Promptだけ`False`であることを確認した。通常Profileで
PR #6 / #7が有効になる一方、candidate数、Semantic Prompt、Quality Gate、Segmentation backend、Contractは変更していない。

**`coherent_group`: 採用に向けて前向きに検討する。** 複数componentを一つの広めのLayerとして残すことは、
「飛び地のまま出すより、意味のある一組を残す」という新方針と整合する。ただし、現在のSaved artifactには
required componentの欠損と背景片が残る例もある。通常Profileへ有効化せず、required componentの受理、背景混入、
hole fill後のpreviewを同じcaseで確認する独立PoCを次に行う。

**narrow-gap closing: 物理的な連続性の目標は採用するが、現行の形態学的closingを大きな固定pxで全体有効化はしない。**
`max_gap_px=6`でモンブランの細部が大きく埋まる既存証跡は、幅を大きくするほど意図しない近接要素を結ぶことを示す。
大きなgapを安定してつなぐ必要がある場合は、意味上同一のcomponentを`coherent_group`としてunionするか、対象を含む
広いbboxでSegmentationするPoCとして扱う。物理mmとpxの許容幅はPhysical Output担当の条件なしにAI側で固定しない。

**背景断片: 除外を採用する。** PR #6で除去可能な微小飛び地は通常Profileから外す。大きな断片を「より広いLayer」で
残すかは、その断片が記憶上必要な対象かを`coherent_group` / bbox PoCで確認してから決める。面積閾値だけで主題を
消す一般自動rejectは導入しない。

機械検証はgenerator関連**27 passed**、対象Ruff check / format、`git diff --check`がpassした。Gemini API・
画像生成は0回である。この変更は採用後の最終品質ベースラインではなく、採用されたPR #6 / #7を通常Profileへ
反映した時点の設定・実装証跡であり、Locked regression-6 + Supplementalでの`gemini-3.5-flash-lite`最終確認が必要である。

### 8.38 採用後通常Profile E2E — 9/9 Semantic失敗（2026-09-03）

PR #6 / #7の採用後設定を通常Profileの品質証跡へ追加するため、privateの`quality-evaluation.json`にある
建築、料理/工芸、人物＋scene anchorの3 caseを`physical_layer_v2`で各3回、計9回実行した。入力は各5枚で、
runごとの`inputHash` / `memoryTextHash`はprivate `summary.json` / `metrics.json`へ記録した。

実効条件は`GEMINI_MODEL=gemini-3.5-flash-lite`、`MOCK_AI=false`、`SEGMENTATION_BACKEND=efficient_sam_onnx`、
`closedHoleFillEnabled=true`、`microIslandCleanupEnabled=true`、`compositionOverlapInstructionEnabled=false`である。
**9 runすべて`AiError`、failure stage=`semantic`、4 Layer成功0/9**だった。Semantic elapsedは
garden architectureが2,460.716〜2,769.101 ms、food / craftが3,659.139〜3,840.912 ms、Kanazawa memory mixが
3,304.635〜3,545.719 msである。Semantic Plan、Mask、RGBA Layer、composition previewは生成されなかったため、
このrunに対するCodex画像確認は対象なしである。

失敗recordは`poc-output/adopted-pr6-pr7-flash-lite-20260903/quality-evaluation-20260902-224949/summary.json`へ
private保存した。runnerはprovider生Responseをartifactへ保存しないため、API Keyやprivate入力本文は露出していない。
PR #6 / #7はSemantic Planningの後段（Mask正規化）でだけ動作するため、このfailureだけから両採用品が原因とは
判断しない。

資料21のmodel固定規則に従い、同じ入力での追加retry、別Gemini model、fallback、Mock成功への置換は行わない。
この9失敗は削除せず、PR #6 / #7採用後の最終品質ベースラインは**未確定**のままとする。次アクションは、
`gemini-3.5-flash-lite`のSemantic API失敗の外部状態またはStructured Output条件を、private入力を再送信せずに
診断してから、同modelだけで改めて固定dataset / Supplemental評価を計画することである。

### 8.39 9/9失敗の静的切り分け（2026-09-03）

失敗後、直前の作業基準commit `cc37b06` と現行worktreeの関連差分を確認した。PR #6 / #7の通常有効化は
`GeminiArtworkGenerator.generate` の **Semantic Plan成功後**に進むSegmentation / Mask正規化だけをguard付きで
有効にする変更であり、`physical_layer_v2`のSemantic Prompt、`_semantic_profile_instruction`、
`_semantic_plan_schema`そのものには今回の差分がない。品質runnerの変更もmodel固定、入力hash、feature flag、
進行表示をprivate artifactへ残すだけで、Geminiへ送るSemantic内容を変えない。

Structured Output共通helperの`automatic_function_calling=disable`は差分に含まれるが、これは§8.21で導入済みであり、
§8.24〜§8.25の`gemini-3.5-flash-lite`成功E2Eでも同じ設定で使われていた。従って、今回の9/9をPR #6 / #7や
AFC無効化へ帰属させる根拠はない。一方、現在の安全な例外変換はprovider生Responseを保存・露出しないため、
private入力を再送信せずにlocal artifactだけからAPI側の失敗理由を特定することもできない。

この切り分けでは追加API呼出し、画像生成、fallback、model切替は0回である。最終品質ベースラインは引き続き
未確定とし、次に必要なのはGemini Developer API / Backend側での安全な外部状態・Structured Output失敗情報の確認である。

### 8.40 Gemini Structured Outputの非private疎通診断（2026-09-03）

§8.38の9/9 `semantic`失敗が、model停止、API Key、SDKのStructured Output全体、またはprivate入力を含む要求の
どこにあるかを分けるため、写真・memoryText・Saved Plan・生成画像を一切含まない最小要求を実行した。`Settings`で
実効`GEMINI_MODEL=gemini-3.5-flash-lite`、API Key設定あり、timeout 120,000 msを先に確認したうえで、
`{ "ok": boolean }`だけを要求するPydantic JSON Schemaを既存`_generate_structured`経路へ渡した。

通常のsandboxではsocket接続がOSに拒否された（`WinError 10013`）。これはGemini providerからの応答ではなく、
local sandboxのnetwork制限である。同じ最小・非private要求だけを明示承認されたnetwork環境で再実行した結果、
**success=true、1,169.480 ms**だった。実効modelは`gemini-3.5-flash-lite`であり、別model、fallback、画像生成、
private写真・memoryTextの送信は0回である。response本文、API Key、provider生Responseは保存していない。

従ってこの証跡は、対象model・現在の認証・`google-genai 2.19.x`・AFC無効のStructured Output呼出しが、最小の
JSON Schema要求では利用可能であることを示す。一方、§8.38のprivateな5写真＋memoryTextを伴うSemantic要求が
なぜ失敗したか、候補数・画像transport・Schema規模・provider一時状態のどれが原因かは示さない。失敗runを
置換せず、同じprivate入力を追加再送信もしない。最終品質ベースラインは未確定のままとする。

次アクションは、Backend / Gemini側でprivate入力を出さずに取得できる安全な失敗分類（HTTP status / provider error
種別 / request IDの有無）を確認すること。確認できない場合は、資料21 §8の形式で人間へ外部確認を依頼する。

### 8.41 5画像・実Semantic Schemaの非private診断（2026-09-03）

§8.40の最小JSON Schema成功だけでは、5画像のmultimodal transportや実際の`SemanticPlan` Schemaの問題を
除外できない。そこで、white背景に色付き円と黄色い四角を描いた**合成PNG 5枚**だけをprocess memory上で作り、
private file・memoryText・既存画像を一切読まずに`_generate_structured`へ渡した。Promptはsynthetic画像を明記し、
実際の`_semantic_plan_schema()`、`SemanticPlan` Pydantic validation、候補数12を要求した。実効modelは
`gemini-3.5-flash-lite`だけであり、fallback・別model・Mock・private入力・artifact保存は0回である。

結果は**success=true、12 candidates、6,301.173 ms**。これは現在のmodel／認証／SDKで、5画像Part、実Semantic
Schema、AFC無効、Pydantic再検証を通る経路が利用可能であることを示す。合成画像は内容を自明にした診断入力であり、
成果物としてのArtwork、Mask、previewを生成していないためCodex画像確認の対象はない（品質採否の画像証跡でもない）。

§8.38との比較により、9/9の原因は固定的な「5画像数」「Schemaサイズ」「対象modelの全停止」ではない。privateな
写真群＋memoryTextの内容に対するprovider応答、またはその9 run時点だけの一時状態まで範囲は狭まったが、両者を
この診断から判別することはできない。失敗runを置換せず、private入力の追加送信もしない。最終品質ベースラインは
未確定のままとし、安全なprovider失敗分類の外部確認を必要とする。

### 8.42 Cloud Runログ参照可否のローカル確認（2026-09-03）

外部確認を依頼する前に、local環境からCloud Run / Geminiの失敗分類を安全に取得できるかを確認した。`gcloud`と
Firebase CLIはinstall済みで、gcloud project設定も存在する。一方、`gcloud auth list --filter=status:ACTIVE`で
**active Google Cloud accountなし**を確認した。project IDやaccount名、secret、private入力は記録していない。

通常のgcloud loginとは別に、Application Default Credentials file、`GOOGLE_APPLICATION_CREDENTIALS`環境変数、
`gcloud auth print-access-token`も、資格情報本文を出力せずに可否だけ確認した。ADC fileなし、環境変数なし、
access token取得不可だった。`access_tokens.db`は存在するがactive account / tokenとして使用可能ではないため、
これを認証済みの根拠にはしない。

そのため、このworktreeからCloud Run logをread-onlyに検索して§8.38のHTTP status、provider error種別、request IDを
取得する権限はない。認証を新規に行うこと、Cloud Run設定を変更すること、private入力を再送信することは実施しない。
Codex画像確認の対象となる新規Mask / previewもない。

ローカルで完結する非private診断は§8.40〜§8.41まで実施済みで、model／認証／5画像・実Schema経路は成功している。
次の最小外部入力は、Backend / GCP担当が既存の失敗時刻帯について安全な分類情報だけを返すことである。これが得られるまで、
同じprivate固定datasetの追加run、別model、fallbackを行わず、最終品質ベースラインは未確定とする。

PRコメントに外部実行結果が共有されている可能性も、`gh auth status`で確認した。しかしlocal GitHub CLIのdefault tokenは
invalidであり、read-onlyのPR取得にも使えない。認証の再設定は実行しない。このため、Cloud RunログとGitHub PRコメントの
いずれからも、local環境だけで§8.38のprovider失敗分類を取得することはできない。

### 8.43 人間承認の診断1 run — garden Semantic成功（2026-09-03）

人間から「Aを行ってよい」との承認を得たため、§8.38の失敗を置換しない**原因診断専用1 run**を実施した。添付された
Gemini API使用状況の28日グラフは、8月下旬に404 / 429 / 503 / 504を示す一方、日別集計なので§8.38の9件と
同時刻の状態を確定できない。したがってグラフだけでprovider失敗なしとは判定せず、localの安全な1 runを行った。

診断前に`probe_gemini_semantic_transport.py`を、実runtimeと同じ`GeminiSemanticPlanner.plan`（PNG transport、
`physical_layer_v2`、candidate数12、target layer数4、AFC disabled）を通すようにした。複数case datasetから
`--case-id`で1件だけ選べ、失敗時には例外本文・provider本文・headers・request ID値を保存せず、例外型、HTTP status、
request IDの**有無**だけをprivate `run.json`へ残す。case選択とmetadataがprivate文字列／secretを残さないことは
focused test **2 passed**で確認し、対象Ruff check（既存のruntime import構造に由来するE402 / I001は除外）とformatもpassした。

実行条件は、§8.38と同じprivate `garden-architecture`（写真5枚、同一input hash / memoryText hash）、
`GEMINI_MODEL=gemini-3.5-flash-lite`、`MOCK_AI=false`、`SEGMENTATION_BACKEND=efficient_sam_onnx`。
Semanticだけを1回実行した結果は**success=true、12 candidates、32,937.535 ms**だった。artifactは
`poc-output/semantic-diagnostic-20260903/gemini-semantic-transport-20260902-233044`へprivate保存した。別model、fallback、
Mock、追加case、Mask / RGBA / Composition生成は0回である。

Codexは同artifactの5枚のbbox previewを画像確認した。昼の庭園・夜の庭園と灯籠・庭園建物・建物模型・人物を含む候補bboxが
描画され、Semantic Planが空／Schema不成立ではないことを確認した。これはbboxの最終的な意味品質やLayer採否の判定ではなく、
diagnostic 1 runにおけるSemantic到達の確認である。Mask、4 Layer Artwork、previewはこのrunでは生成していないため、
それらのCodex画像確認は未実施である。

§8.38の9/9失敗と今回の成功は、同一model・同一固定入力でもSemantic結果が時間的に揺れた、または診断時だけprovider状態が
異なったことを示す。これだけでPR #6 / #7採用後の最終品質ベースラインを成功扱いにせず、失敗recordも削除しない。
今回の人間承認は1 case 1 diagnostic runに限るため、追加のprivate再送信やfull E2Eへ拡張せず、次の最終Profile評価の
実施可否と回数は人間判断として残す。

### 8.44 最終E2E開始 — 実行環境の中断可能性を明示（2026-09-03）

人間から最終E2E開始の指示を得たため、まずLocked regression-6（architecture 3 case、non-architecture 3 case）を
`physical_layer_v2`で各3回、計18 run実行した。入力復元用scriptは保存済みmanifestの写真・memoryText hashと一致することを
検証してからprivate datasetを生成する。実効条件は`GEMINI_MODEL=gemini-3.5-flash-lite`、`MOCK_AI=false`、
`SEGMENTATION_BACKEND=efficient_sam_onnx`、`closedHoleFillEnabled=true`、`microIslandCleanupEnabled=true`、
`compositionOverlapInstructionEnabled=false`である。別model、fallback、Mockは使用しない。

また、人間からこの時期にPCを閉じたり給電のない環境で実行していたとの共有を得た。これはrunの時間値および中断の解釈における
重要な交絡要因として記録する。ただし、artifactにスリープ・電源断・手動中断の明確な証跡がないfailureを、Codexの推測だけで
無効化またはAPI／品質外と再分類しない。明確な中断runだけを再計測対象として成功runと区別し、それ以外は原因未確定のfailureとして
残す。成功runで既存failure recordを置き換えない。補助3 caseの同条件E2Eを開始しており、Locked regression-6およびSupplementalの
完走後に、機械集計・Codex画像確認・既知の限界をこの節へ追記する。

Supplementalの途中結果として、`garden-architecture`は3/3成功し、いずれも4 Layer・scene anchorあり・採用Maskは
単一componentだった。1回目のcomposition previewでは、庭園背景に人物、石灯籠、松の3 subjectが分離配置されていることを
Codexが確認した。`food-and-craft`も3/3成功し、各runは4 Layer、採用Maskのcomponent数1・interior hole 0だった。
画像確認では花模様の制作物、完成した花模様、皿全体、モンブランが別Layerとなり、皿は輪郭内を埋めた1 Layerとして残った。
一方、3 runすべてscene anchorを選ばず`background_missing=true`で、4 subjectだけが並ぶ構図だった。これは実行上の失敗では
ないが、「背景なしの作品を最終Profileで許容するか」という意味品質の人間判断材料として残す。処理時間はPCのスリープ等の待機時間を
含む可能性があるため、採否の数値根拠にしない。

#### 資料21ゴール進捗の算定（2026-09-03）

以後の進捗率は、資料21 §17の16完了条件を同じ重みで数える。完了を1、実証済みだが統合時再確認・
最終判定が残るものを0.5、未着手または最終証跡がないものを0とし、丸めた値を報告する。これは処理時間・
run数の割合ではなく、ゴール達成度である。

| 条件群 | 現在値 | 根拠 |
| --- | ---: | --- |
| architecture v3 | 0.5 | 既存Cloud Run／local証跡により仮完了。統合時の再確認が残る。 |
| PR #6 / PR #7 | 2.0 | 人間採用、通常Profile有効化、Locked最終E2E済み。 |
| coherent_group / narrow-gap / 背景断片 | 2.5 | `coherent_group`は採用方向だが最終PoC未完、narrow-gapは保留理由明確、背景方針は決定済み。 |
| semantic duplicate / Composition overlap | 2.0 | 個別方針と観測diagnosticsが決定済み。 |
| 採用品の内部統合 | 1.0 | PR #6 / #7のみ通常Profileへ反映済み。 |
| Locked + Supplemental最終確認 | 0.5 | Locked regression-6完走。Supplemental 9 run実行中。 |
| 最終3層判断・baseline・設計チェック | 1.0 | 静的監査は実施済みだが、最終Codex画像確認、人間判断、baseline明文化が残る。 |
| model固定と速度改善準備 | 1.5 | 最終runはflash-liteのみ、他model混入なし。速度改善開始の判定は未完。 |

**合計: 11.0 / 16 = 69%**。この69%は、Supplemental E2Eの完走、最終画像確認、人間の最終品質判断、
baseline明文化、設計チェックの確定によってのみ増やす。成功runだけで未完条件を完了扱いにしない。

#### 最終E2E完走 — Locked regression-6 + Supplementalの機械集計・Codex画像確認（2026-09-03）

Supplementalの`quality-evaluation.json`（garden architecture / food and craft / Kanazawa memory mix、各5写真）を
`physical_layer_v2`で各3回、計9回実行し、private artifact
`poc-output/final-e2e-pr6-pr7-20260903/quality-evaluation-20260903-071724/`へ保存した。実効条件はLocked runと同一、
すなわち`gemini-3.5-flash-lite`、`MOCK_AI=false`、`SEGMENTATION_BACKEND=efficient_sam_onnx`、
`closedHoleFillEnabled=true`、`microIslandCleanupEnabled=true`、`compositionOverlapInstructionEnabled=false`である。
別Gemini model、fallback、Mock、候補数／Semantic Prompt／Quality Gate／Segmentation条件の速度目的変更は0回である。

機械結果はSupplemental **9/9 success、全successが4 Layer、全runでflash-liteのみ**だった。採用Mask 78件はすべて
post component count 1、post interior hole 0であり、採用Maskの22件でmicro-islandを除去した。9 runともphysical-ready
diagnosticsを出力し、2 runでrecomposeを行った。一方、food-and-craftの3/3はscene anchorを選ばず
`background_missing=true`だった。これはAPI／Maskの失敗ではないが、背景なしを通常Profileの作品として許容するかは
人間判断が必要である。

Locked regression-6の確定値はmetrics artifact 18件中 **17 success / 1 failure**（`ARCH-01` try1、
`failureStage=source`、error本文なし）である。このfailureにはスリープ・電源断・手動中断の明確な証跡がないため、
環境事情から無効化せず原因未確定のfailureとして残す。17 successはいずれも4 Layer・flash-liteのみで、採用Mask
138件はすべて単一componentだった。micro-island除去は54件、physical-ready 17/17、recompose 11/17である。
背景なしはNotre Dame try1とbasketball try1の2件だった。

両runを合わせた最終E2Eの機械証跡は、metrics artifact **27件、success 26 / failure 1、採用Mask 216件、
採用Maskの複数component 0件**である。closed-hole fill flagは全runで有効だった。Supplementalではpost interior hole 0だが、
Lockedには小さな残留holeが3件あった（Maple Tree Foreground 1件・area ratio `3.749e-05`、Maple Tree Left 1件・
`3.750e-05`、Left Bell Tower Detail 1件・`3.076e-04`）。cleanup telemetryには`filled_closed_holes` actionが記録されず、
この3残留をもって「任意の穴を必ずゼロにする」とは証明しない。PR #7の採用方針（閉鎖穴を埋める）は維持するが、
現ベースラインの既知の限界として残す。

CodexはLockedの6代表previewに加え、Supplementalのgarden try1/try2、food try1/try2、Kanazawa try1/try2/try3の
composition previewを確認した。皿とカエル意匠は各確認runで一つの連結Layerとして残り、food try2でもmachine上は
皿・花制作物・花紙・モンブランの各Layerが単一component／hole 0だった。画面上の白い意匠部が不透明な白画素か
透過穴かはpreview単独では断定せず、Mask diagnosticを根拠にする。

一方、視覚的な作品品質は安定していない。garden try2では庭園anchorに人物・大きな灯籠・建築模型が同居し、
サイズと意味の整理が弱い。food try2は背景なしの4物体が重なり、Kanazawa try3では大きな皿が背景中央を覆い、
人物と灯籠との関係も自然な一枚の思い出作品とは言い切れない。この所見はMask連結性の失敗ではなく、
Semantic選定／compositionの最終的な人間評価が必要という証跡である。Codexは視覚的な合否を代行しない。

したがって資料21の進捗は、Supplemental完走とflash-lite固定の最終確認を満たした分だけ
**12.0 / 16 = 75%**へ更新する。baselineの最終確定、`coherent_group`の採否、architecture v3の統合時再確認、
および人間による作品品質判断は未完であり、このrun成功だけで通常Profileの最終採用とはしない。次アクションは、
上記preview群を根拠に、人間が「構造品質を優先して現Profileをベースライン採用する」か
「構図品質を優先してbaseline採用を保留し、coherent_group／compositionを次PoCに戻す」かを判断することである。

E2E完走後の静的確認として、`python scripts/validate_contracts.py`、対象Ruff check / format、`git diff --check`、
generator・quality runner・real AI pipeline・overlap diagnostics・frontend handoff・transport probeのfocused pytestを
実行し、**43 passed**（FastAPI／httpxの既知deprecation warning 1件）だった。formatで診断script
`probe_gemini_semantic_transport.py`のみをRuff整形し、機能・品質条件は変更していない。

### 8.45 `coherent_group`の採否整理 — required保持は確認、通常Profileへは不採用（2026-09-03）

最終baselineの人間判断とは独立に、資料21 Phase Bの既存artifactを再読し、`coherent_group`の採否を明確化した。
Gemini API、画像生成、既存artifactの再実行、Profile設定変更は0回である。対象は補正なしのcomponent aggregationだけを
保存した3例であり、`fill_closed_mask_holes`、narrow-gap closing、micro-island cleanup、Quality retry、Compositionは
意図的に含まない。

- 人物＋ball: required 2 / accepted 2、exclusive寄与91.90% / 8.10%。しかしaggregateは2 component、hole 3件。
- 皿＋モンブラン: required 2件とも保持し、exclusive寄与69.31% / 30.69%。しかしaggregateは2 component、
  hole 46件（area ratio 0.0171）。
- ノートルダム屋根＋尖塔: required 2 / accepted 2、exclusive寄与82.14% / 17.86%。しかしaggregateは10 component、
  hole 15件である。Codexが今回再確認したRGBA previewでも、屋根と尖塔は意味的には保持される一方、
  大きな外部gapと複数の小片を残すため、単体で印刷可能な1 Layerとは扱えない。

よって`coherent_group`は、**required componentを失わせないための集約仮説としては支持されるが、通常Profileへは
不採用**とする。理由は「component数が複数だから」ではなく、資料21のB3に従い、必須対象を保っていても背景混入・
大きな外部gap・hole・Layerとしての読みやすさを解決せず、現行の物理Layer方針を満たす証跡がないためである。
これは将来の再検討を禁止する判断ではない。再開条件は、required保持の診断を保ったまま、背景混入を除き、
物理的に連続なLayerへする安全なPolicyを、人物・料理/器・建築の固定caseで独立PoCできることである。

資料21の完了条件「`coherent_group`の採否または残課題が明確」を満たしたため、進捗は
**12.5 / 16 = 78%**へ更新する。最終baselineの人間判断、architecture v3の統合時再確認、残留holeの扱い、
最終設計チェックは引き続き未完である。

### 8.46 資料21 §1.1 最終設計チェック — 静的監査（2026-09-03）

最終E2E完走後、資料21 §1.1の19項目をcurrent implementationとartifact runnerで静的監査した。
Gemini API、Mask再生成、Profile設定変更は0回である。結果は、完了済みの設計上の強みと、baseline確定前に
解消または明示的に保留すべき不足を分けるためのものであり、未確認項目を成功扱いにしない。

| 確認項目 | 判定 | 根拠 / 残課題 |
| --- | --- | --- |
| `subject` / `scene_anchor`の経路分離 | 確認済み | `kind` validatorと`_build_scene_anchor`の矩形Crop経路が分離。 |
| `kind` / `semantic_role` / `extraction_intent`の非重複 | 一部未達 | `scene_anchor`は`kind`と`extraction_intent=scene_anchor`を二重に持つ。これは互換維持には機能するが、資料21の一方向管理とは一致しない。 |
| 無効組合せの内部Model拒否 | 一部未達 | scene anchorのcomponent数、coherent_groupのcomponent数／primaryはvalidatorで拒否する。一方、`semantic_role`とkindの全無効組合せはrejectしていない。 |
| 旧Saved Plan互換 | 確認済み | `extraction_intent`未指定の旧scene anchorをvalidatorで補完する。 |
| component直後のRaw Diagnostics | 一部未達 | stage-separated replayはRawを保存するが、通常runnerのobserverはclosed-hole fill後のMaskを観測する。通常経路で真のRawとNormalizedの対をartifact化していない。 |
| Aggregation / required保持 | 確認済み | `coherent_group`のrequired予定数・受理数・exclusive寄与をCandidateMetricへ記録する。 |
| `single_form`品質条件 | 確認済み | physical modeではmicro-island cleanup後も複数componentならrejectする。 |
| Normalization処理・設定のartifact記録 | 一部未達 | feature flagはsummaryへ残るが、closed-hole fillの適用量／actionはcandidate単位に残らない（§8.44の残留holeも参照）。 |
| Normalized Diagnostics | 確認済み | candidate metricsにcomponent / hole / bbox / border diagnosticsを記録する。 |
| scene anchor最大2計画・最大1選定 | 確認済み | prompt/schemaが最大2を要求し、`_select_layers`は最大1を選ぶ。 |
| semantic duplicate diagnostics | 一部未達 | promptで重複回避、同じcandidate IDはrejectするが、意味的な重複を独立metricとして検出していない。 |
| Composition違反の統合計測 | 確認済み | bottom gap、composition bounds、subject overlapをquality runner artifactへ出す。 |
| Gemini recompose最大1回 | 確認済み | bottom-gap違反時のrecompose呼出しは1回だけで、その後は決定論的clamp。 |
| 安全に直せないComposition違反のfailure条件 | 未達 | overlapはdiagnosticのみで、構図品質のfailure条件がなく、今回の不自然なpreviewを機械的に止められない。 |
| 採用品のみ通常Profileへ統合 | 確認済み | PR #6 / #7のみ有効。coherent_groupは通常Promptではなく、gap closing 0、overlap prompt false。 |
| Locked + Supplemental最終Profile確認 | 確認済み | §8.44の27 metrics artifact。 |
| ローカル機械 / Codex / 人間判断の完結 | 未達 | 機械・Codex証跡は揃ったが、最終baselineの人間判断が未取得。 |
| 最終採否／Profile runのflash-lite固定 | 確認済み | §8.44のLocked / Supplementalと診断runはすべて`gemini-3.5-flash-lite`。旧3.7 artifactは最終採否証拠から除外済み。 |

このため設計チェック全項目は未完であり、資料21完了条件13を満たさない。特に「Composition failure条件」と
「通常経路におけるRaw / Normalized対のartifact化」は、今回の人間判断がA / Bいずれでも次の品質設計作業として残る。
ただし、これらを速度目的で急いで変更するとbaselineの比較条件を壊すため、最終baseline採否の人間判断前には
candidate数・Semantic Prompt・Quality Gate・Segmentation条件を変更しない。

### 8.47 architecture v3 — 統合前のlocal静的再確認（2026-09-03）

人間が許可した「過去Cloud Run計測＋local検証による仮完了」を、完了済みの36 runとして読み替えないまま、
統合時に守るべきprofile境界をcurrent implementationで確認した。Gemini API、Cloud Run、private入力、
通常Profile設定の変更は0回である。

- architecture A/B run sheetは、baselineを`physical_layer_v2`、candidateではARCHだけ
  `physical_layer_v3_architecture`、NONARCHは`physical_layer_v2`として生成する。case hashだけを台帳へ出し、
  private本文を出さない。
- v3はSemantic schemaでarchitecture roleを許可し、`architecture_primary`が計画済みならLayer selectionで
  優先保持する。local pipeline testは、4 Layer・primary building・micro-island cleanupを確認した。
- 対象test **3 passed**（warning 1件）、v3周辺のRuff checkはpassした。これはdeterministic fake planner / segmenterに
  よる統合境界の確認であり、Geminiの揺れ、現Cloud Run revision、6 caseのnon-architecture回帰、Codex画像、
  人間採否を代替しない。

結論は従来どおり**architecture v3は仮完了・通常Profile未採用**である。資料21 A1が要求する
baseline / candidate × Locked regression-6 × 3回の36 runは、統合を実施する時点で同一model・固定runtime条件の
外部証跡を再確認する。従って進捗は**78%のまま**とする。

### 8.48 PR #7残留hole alertの原寸再診断 — 縮小診断の偽陽性（2026-09-03）

§8.44のLocked metricsでpost interior holeが1と記録された3 candidateを、保存済みcomponent Maskだけで
原寸再診断した。Gemini API、Segmentation、Profile設定、Maskの書換えは0回である。対象は
Maple Tree Foreground（ARCH-01 try2）、Maple Tree Left（ARCH-01 try3）、Left Bell Tower Detail（ARCH-03 try3）である。

quality runnerと同じ`max_side=512`では、3件ともanalysis scale 3でhole 1となる。一方、原寸を保持する
`max_side=4096`（analysis scale 1）では**3件ともinterior hole 0**だった。さらに各Maskへ
`fill_closed_mask_holes`を再適用しても追加画素は0である。つまり、原寸では外部と細く接続した透明領域が、
縮小時に経路を失って「閉鎖穴」に見えるdiagnostic上の偽陽性であり、PR #7が埋め忘れた閉鎖穴ではない。

§8.44の縮小metric値は履歴として残すが、そこから「実物Layerにholeが残った」と結論してはならない。
確認済みの3 alertについては、原寸ではclosed-hole fillがidempotentである。これにより最終baseline判断の
懸念は構図品質・背景なし・source failureへ絞られる。ただし、縮小diagnosticsと原寸形状が不一致になること自体は
§8.46のRaw / Normalized artifact境界の改善課題として残す。新規previewは生成していないため、Codex画像確認は
既存Mask / composition previewのままであり、この再診断を視覚的作品品質の採否には使わない。進捗は**78%のまま**とする。

### 8.49 人間判断1 — 背景なしと前景の下寄せ（2026-09-03）

人間判断により、food-and-craftのようにscene anchorを選ばない4 Layer作品は、各素材が思い出として意味を持つなら
**通常Profileで許容する**。従って`background_missing=true`は観測・人間レビュー対象として保持するが、
scene anchor必須のQuality Gate、不合格条件、Semantic Promptは追加しない。

同時に、前景LayerはCanvasの下側へ配置する意識を持つことを、次の**軽微なComposition改善要件**として採用した。
これは現final baselineの評価条件を途中で変える指示ではない。資料21の比較条件を保つため、現在のcandidate数、
Semantic Prompt、Quality Gate、Segmentation条件、既存E2E artifactは変更せず、baseline判断完了後の別PoCで
「下寄せが作品の意味を壊さず、canvas bounds / physical bottom gapを悪化させないか」を確認する。

### 8.50 人間判断2 — 重なり・サイズ感の表現許容（2026-09-03）

人間判断により、庭園背景に皿・人物・灯籠を重ねるような自由な重なりとサイズ感は、
**意図的なレイヤーアート表現として通常Profileで許容する**。したがって、§8.44でCodexが記録した
Kanazawa previewの皿による背景中央の遮蔽や、前景subject間の重なりを、根拠のない自動failure・
自動recompose・Semantic Prompt変更の理由にしない。

この判断は§8.30の既存overlap許容方針と整合する。前景の下寄せは§8.49の軽微改善PoCとして分離し、
現baselineのcandidate数、Semantic Prompt、Quality Gate、Segmentation条件、E2E artifactは変更しない。

### 8.51 人間判断3 — `physical_layer_v2`のAI品質ベースライン採用（2026-09-03）

人間判断により、通常Profile **`physical_layer_v2`をAI品質ベースラインとして採用**する。これは次の固定条件を
持つ比較基準であり、以後の品質・速度改善はこのbaselineを壊さず、candidateとの差分を独立に評価する。

- runtime: `MOCK_AI=false`、`SEGMENTATION_BACKEND=efficient_sam_onnx`
- quality model: `gemini-3.5-flash-lite`のみ。別model、fallback、Mockは最終採否証拠に含めない。
- adopted normalization: `closedHoleFillEnabled=true`、`microIslandCleanupEnabled=true`
- composition: `compositionOverlapInstructionEnabled=false`。背景なしと自由なsubject overlapは人間判断で許容し、
  E1 diagnosticsは観測用に維持する。
- excluded: `physical_layer_v3_architecture`、`coherent_group`、narrow-gap closing、未定義のcomposition failure rule。

根拠は§8.44のLocked regression-6 + Supplemental（27 metrics artifact中26 success、全success 4 Layer、
採用Mask 216件すべて単一component）、CodexのMask / preview確認、§8.49〜§8.51の人間判断である。
Lockedの`ARCH-01` try1にある`failureStage=source`の1 failureは、成功runで置換せず原因未確定の既知限界として残す。
§8.48により、縮小diagnostic上の3 hole alertは原寸Maskではhole 0と確認済みである。

前景LayerをCanvas下側へ寄せる改善は、採用baselineそのものを変更しない**次の軽微candidate PoC**として扱う。
候補数、Semantic Prompt、Quality Gate、Segmentation条件を変えず、physical bottom-gap・canvas bounds・既存の
人間許容overlapを悪化させないことを比較条件とする。

資料21 §17の進捗は、architecture v3が仮完了0.5、最終設計チェックが未達0、その他14条件が完了となり、
**14.5 / 16 = 91%**へ更新する。速度改善へ進める状態は明確になったが、baselineを固定したまま行う。
未完はarchitecture v3の統合時外部証跡と、§8.46で列挙した最終設計チェックの未達項目だけである。

### 8.52 前景Layer下寄せ — 決定論replayとPrompt candidateの途中証跡（2026-09-04）

人間判断§8.49の「前のLayerは下めに配置する意識」を、採用済みbaselineを変更せずに独立評価した。
候補数、Semantic Planning、Segmentation、Quality Gate、Mask normalization、overlap許容方針は変えていない。
通常Profileの`COMPOSITION_FOREGROUND_BOTTOM_INSTRUCTION_ENABLED`は**既定false**であり、candidate E2Eだけでtrueにした。

まずGemini・Segmentationを一切呼ばず、§8.44のLocked / Supplemental成功26件の保存済みArtwork・RGBA Asset・
composition diagnosticsから、最前面subjectだけを「下端余白0.15以下」へ下げる決定論replayを実行した。
artifactは`poc-output/foreground-bottom-bias-20260904-retry1/summary.json`である。

- 26/26件を評価し、10件だけが移動対象だった。candidateのCanvas boundsは**26/26件で維持**された。
- 最前面subjectがsubject群で最も下にある件数は8/26から10/26へしか増えなかった。固定位置補正だけでは、既に下端にある中景Layerとの相対順を十分に表現できない。
- subject同士の縮小overlap pixel合計は1,991,578から1,952,806へ変化したが、個別には増減がある。人間判断§8.50に従い、この値を自動不合格条件にはしない。
- Codex画像確認では、food-and-craftのモンブランは下寄せ後もCanvas内で皿と工芸を破壊せず、Kinkaku-jiの鳳凰は下端側に自然に移った。一方、明太子や別food caseでは小さい移動に留まり、固定補正の視覚的効果は限定的だった。

このため、`max_bottom_gap`を追加で厳格化する通常Profile変更は採用しない。代わりに、前景を下寄せすることを**hard ruleではない構図上の好み**としてComposer promptにのみ追加するcandidateを作成した。
`GeminiComposer`へfeature flagを渡し、「前景として置くsubjectは背景・中景よりCanvas下側を好む。ただし全LayerをCanvas内に保ち、subjectの意味を壊さず、hard ruleにしない」と明記する。設定・service wiring・promptのfocused testを追加し、Ruff check / formatはpass、
`test_generator_service.py` + `test_real_ai_pipeline.py` は**28 passed**（既知のFastAPI/httpx deprecation warning 1件）である。

candidateの補助3ケースE2Eは`poc-output/foreground-bottom-prompt-20260904/quality-evaluation-20260903-154427/`へ実行中である。
実効設定は`MOCK_AI=false`、`physical_layer_v2`、`gemini-3.5-flash-lite`、closed-hole fill / micro-island cleanup=true、overlap instruction=false、foreground-bottom instruction=trueである。

- 最初の3件はSemantic stageで約5〜7秒後に失敗した。個別transport probeでHTTP statusなし・request IDなしの`ConnectError`を確認したため、構図promptではなく実行環境からの接続断として分類した。失敗runはartifactに残し、成功runで置換していない。
- 同一case・同一`gemini-3.5-flash-lite`の再接続probeは成功し、Semantic Planningが12 candidateを返した。このため別modelへのfallbackは行わず、同一candidate条件でE2Eを再実行した。
- 再実行のgarden-architectureは完走し、4 Layer、採用Maskは単一component、全Layer Canvas内である。最前面の着物人物は`layerIndex=3`、bottom gap=0.0527で、背景・中景より下側に置かれた。Codex画像確認では、庭園背景、木造建築、灯籠、人物が読め、人物は左下の前景にある。人物が建築を一部覆うが、§8.50で許容済みのLayer art表現の範囲として扱う。
- food-and-craftはONNX Segmentationを継続中であり、まだ`metrics.json` / summaryがない。完走前にこのcandidateを採用・不採用・保留と結論しない。

既知の限界は、今回のPrompt candidateはGeminiの構図揺れを含むため、保存artifactの固定位置replayと一対一の絵比較ではないこと、また補助3ケースはLocked regression-6を置き換えないことである。
この途中結果は前景下寄せの採用を証明せず、前景を常に最下段にすべきことや、overlap / scene anchorを機械的にfailureにすべきことも証明しない。次アクションは残り2ケースを完走させ、同一条件の機械計測とCodex preview確認を追加してから、必要な人間判断だけを提示することである。進捗は**91%のまま**とする。

### 8.53 Raw / Normalized Mask artifact分離 — 最終設計チェックの観測改善（2026-09-04）

§8.46で一部未達だった「component Segmentation直後のRaw Diagnostics」と「normalization処理・適用量のartifact記録」を、
品質挙動を変えずprivate PoC observerの観測形式として追加した。対象は`subject` componentのEfficientSAM出力であり、
scene anchorの矩形crop、Semantic Prompt、candidate数、Quality Gate、Layer Selection、Composition、Artwork Contractには変更がない。

- Segmentationの各attemptで、`fill_closed_mask_holes`前の`stage=raw` Maskとそのdiagnosticsを保存する。
- 続けて従来どおりのclosed-hole fill後Maskを`stage=normalized`として保存し、`closedHoleFillEnabled`と
  `closedHoleFillAddedPixels`を同じrecordへ保存する。flag=falseならadded pixels=0で、Rawと同じMaskを
  normalized stageとして記録する。
- `debug/masks/index.json`はcandidate / component / attemptに加えstageを持つ。normalized Maskの従来の
  filename規則は維持し、rawだけ`-raw` suffixを付けるため、既存のbundle閲覧を壊さない。
- unit testでは閉鎖穴4 pxを持つRaw Maskと充填済みNormalized Maskを対で保存し、stage・raw filename・
  added pixel count=4を確認した。Ruff check / formatはpass、frontend handoff bundle / real pipeline focused testは
  **34 passed**（既知のFastAPI/httpx deprecation warning 1件）だった。さらにGenerator integration testで、
  同じSegmentation resultからobserverへ`raw`→`normalized`の順で通知され、closed-hole fillのadded pixel数が
  正になることを確認した。

これはPR #7の採否、closed-hole fill規則、既存E2Eの品質結果を変更するものではない。実行中の§8.52 candidate E2Eは
この変更前に開始したプロセスなので、旧artifactのまま完走させる。次のReal runからRaw / Normalized対が保存されることを
確認して、§8.46の該当観測不足を「確認済み」へ更新する。進捗は**91%のまま**とする。

### 8.54 前景Layer下寄せ Prompt candidate — Garden / Food途中結果（2026-09-04）

§8.52の同一candidate E2Eで、garden-architectureとfood-and-craftが完走した。いずれも`gemini-3.5-flash-lite`、
`physical_layer_v2`、`closedHoleFillEnabled=true`、`microIslandCleanupEnabled=true`、
`compositionOverlapInstructionEnabled=false`、`compositionForegroundBottomInstructionEnabled=true`であり、
どちらも4 Layer・採用Mask単一component・全Layer Canvas内である。

- Garden: 最前面の着物人物は`layerIndex=3`、bottom gap=0.0527で、前景として下側に配置された。Codex previewでも
  人物は庭園・木造建築・灯籠の前に左下へ置かれ、§8.50で許容された重なりの範囲である。
- Food: 最前面の花工芸は`layerIndex=3`だが、bottom gap=0.2959である。皿Layer（gap=0.0866）とモンブラン
  （gap=0.1336）より上側にあり、下寄せ指示を満たしていない。Codex previewでも花工芸は中央上寄りで、
  最前面を下めにする一貫した構図効果は確認できない。

このためGardenの1成功だけを採用根拠にせず、Foodの反例を同じ重みで残す。現時点の判定は**保留**であり、
通常Profileはfalseのままとする。Kanazawa caseが実行中であり、完走後に3件を集計してから採用・不採用を決める。
この結果は、前景を常に最下端へ固定すべきことや、Foodの自由な重なりを不合格にすべきことを証明しない。進捗は**91%のまま**とする。

### 8.55 semantic duplicate review artifact — 自動rejectなしの選定材料（2026-09-04）

§8.46で一部未達だったsemantic duplicate diagnosticsについて、Layer Selectionの挙動を変えず、
人間/Codexが選定済みLayerを確認するためのprivate artifactを追加した。`debug/physical-ready.json`に
各selected Layerの`candidateId` / `label` / `kind` / `semanticRole` / `sourcePhotoIndex`を保存し、
正規化後labelが完全一致するcandidate対だけを`semanticDuplicateDiagnostics`として記録する。

これは自動reject・importance変更・Prompt変更・candidate数変更を一切行わない。完全一致labelだけをsignalにするため、
同義語、異なる写真の同一人物、scene anchor内の人物との意味重複を自動的に「重複なし」とは判断しない。
その限界をartifactのnoteへ明記し、Codex previewと人間判断で不要重複／意図的表現／判断不能を区別する材料とする。

private observerのfocused testは6 passed（既知のFastAPI/httpx deprecation warning 1件）、Ruff check / formatと
`git diff --check`はpassした。次のReal runでartifactが生成されることを確認するまで、§8.46のsemantic duplicateは
「一部未達」のままとする。進捗は**91%のまま**とする。

### 8.56 前景Layer下寄せ Prompt candidate — 3ケース完走・通常採用は人間判断待ち（2026-09-04）

§8.52の再実行は完走した。artifactは
`poc-output/foreground-bottom-prompt-20260904/quality-evaluation-20260903-154427/summary.json`である。
Gemini APIの実呼出しはすべて`gemini-3.5-flash-lite`であり、実効条件は
`MOCK_AI=false`、`physical_layer_v2`、closed-hole fill / micro-island cleanup=true、overlap instruction=false、
foreground-bottom instruction=trueである。Cloud Run・契約・通常Profileの設定値は変更していない。

| case | 成功 / Layer | 最前面 (`layerIndex=3`) | bottom gap | Canvas bounds | Codex画像確認 |
| --- | --- | --- | ---: | --- | --- |
| garden-architecture | 成功 / 4 | 着物人物 | 0.0527 | 4/4内 | 人物は左下の前景。建築・灯籠との重なりは§8.50の許容範囲。 |
| food-and-craft | 成功 / 4 | 花工芸 | 0.2959 | 4/4内 | 花工芸は中央上寄りで、皿 (0.0866)・モンブラン (0.1336) より上側。下寄せ効果を確認できない。 |
| kanazawa-memory-mix | 成功 / 4 | モンブラン | 0.0200 | 4/4内 | 皿とモンブランが下側に置かれ、前景として読める。自由な重なりは§8.50の許容範囲。 |

従って、機械的な安全条件（3/3成功、4 Layer、採用Maskは単一component、全12 LayerがCanvas内）は保ったが、
今回追加した唯一の意図である「最前面を下めにする」は3件中2件に留まり、Foodでは反例となった。
Geminiの構図生成は揺れるため、同じ3件を再実行すれば同じ絵を得るものではない。よって2/3を効果率として一般化せず、
通常Profileへ有効化するかは視覚品質の人間判断に委ねる。

決定論replayの結果（§8.52）も併せ、max bottom gapの強制補正は採用しない。hard ruleにすると前景と中景の意味的な
相対順を解決できず、自由なレイヤーアート表現を狭めるためである。通常Profileの
`COMPOSITION_FOREGROUND_BOTTOM_INSTRUCTION_ENABLED`は**falseのまま**に保ち、candidate実装も採否まで既定挙動へ
影響させない。今回のE2Eは§8.53/§8.55のobserver追加前に開始しているため、Raw/Normalized対およびsemantic duplicate
artifactの実Runtime証跡には使わない。

この候補の通常採否は、資料21の「視覚的意味・構図品質」の人間判断として次の報告で求める。採用ならdefaultをtrueとして
次回の回帰比較に含め、不採用ならcandidate flag / prompt wiringを除去し、baselineのみを残す。進捗は**91%のまま**とする。

### 8.57 Raw / Normalized・semantic duplicate artifact — 実Runtime途中証跡（2026-09-04）

§8.53/§8.55のobserver実装を、通常Profileの新規Real runで確認中である。対象runは
`poc-output/runtime-observability-20260904/quality-evaluation-20260903-164830/`、固定条件は
`MOCK_AI=false`、`physical_layer_v2`、`gemini-3.5-flash-lite`、closed-hole fill / micro-island cleanup=true、
Composition候補flagはいずれもfalseである。datasetは既存private quality evaluationの3ケースであり、
1件だけに縮める指定はrunnerが開始前に「計画3 run > 上限1」と検出して停止した（Gemini呼出し0回）。
条件を変更せず3件一括へ切り替えた。

garden-architectureの実行中artifactで、`castle_wooden_model` componentについて、同一candidate / component /
attemptの`stage=raw`と`stage=normalized`が別recordとして保存されることを確認した。

- Raw: component count=16、interior hole=26、area ratio=0.310302、`mask-003-raw.png`。
- Normalized: component count=13、interior hole=0、area ratio=0.312973、`mask-004.png`、
  `closedHoleFillEnabled=true`、`closedHoleFillAddedPixels=32,557`。
- Codex画像確認では、Rawの模型Mask内部に複数の黒い閉鎖穴があり、Normalizedではそれらが埋まり外周の形状は保たれている。
  これはPR #7の既存補正を再評価・変更する結果ではなく、補正前の問題を消さずに対として追跡できることの実Runtime証跡である。

この時点ではprocessが稼働中でsummaryは未作成であり、3ケースの成否、`physical-ready.json`における
`semanticDuplicateDiagnostics`、全candidateのRaw/Normalized対については未結論とする。実行が終わるまで通常Profile・
品質条件・候補flagを変更しない。完走後に集計、Codex preview確認、既知の限界（完全一致labelのみのduplicate signal）を
追記して§8.46の設計チェック更新可否を判断する。進捗は**91%のまま**とする。

追記: garden-architectureの1件目は完走し、`metrics.json`で**success=true / 4 Layer / model=
`gemini-3.5-flash-lite`**を確認した。選定subject Maskはいずれもcomponent=1・interior hole=0であり、
`physical-ready.json`には`semanticDuplicateDiagnostics`（method=`exact_normalized_label_only`、pair=0）が保存された。
Codex previewでは庭園背景に木造建築模型・和服人物・石灯籠が独立Layerとして読めた。建築模型が大きく、人物・灯籠との
重なりやサイズ感は強いが、§8.50で人間が許容した自由なLayer art表現の範囲として、この観測runのfailureにはしない。
Raw/Normalized対はscene anchorを除く10 subjectで保存され、hole fillの追加画素が正となるもの7件・0のもの3件を確認した。
2件目food-and-craftを処理中であり、3ケース集計・最終画像確認・設計チェック更新は未完である。

### 8.58 Raw / Normalized・semantic duplicate artifact — 3ケース実Runtime完走（2026-09-04）

§8.57の通常Profile観測runは完走した。artifactは
`poc-output/runtime-observability-20260904/quality-evaluation-20260903-164830/summary.json`であり、
**3/3 success、各4 Layer、failure=0、全run=`gemini-3.5-flash-lite`**だった。feature flagは
closed-hole fill / micro-island cleanup=true、composition overlap / foreground-bottom instruction=falseであり、
baselineのSemantic Prompt、candidate数、Quality Gate、Segmentation条件を変更していない。

| case | Raw / Normalized record | hole fill追加画素あり / 0 | 選定subject | exact-label duplicate |
| --- | ---: | ---: | --- | ---: |
| garden-architecture | 10 / 12 | 7 / 3 | component=1, hole=0 | 0 |
| food-and-craft | 11 / 12 | 3 / 8 | component=1, hole=0 | 0 |
| kanazawa-memory-mix | 10 / 12 | 5 / 5 | component=1, hole=0 | 0 |

scene anchorは矩形cropでcomponent Segmentationを経ないためnormalized stageだけであり、各caseのRaw数はsubject componentの
数に一致する。Raw componentごとに同じcandidate / component / attemptのNormalized recordが存在し、
`closedHoleFillEnabled`と`closedHoleFillAddedPixels`を記録した。従って、§8.46で未確認だった
「通常経路で真のRawとNormalizedの対をartifact化」と「candidate単位でNormalizationの適用量を残す」は、
実Runtime証跡をもって**確認済み**へ更新する。

`physical-ready.json`は3/3で生成され、選定Layerのkind / semantic role / source photo indexと、
`semanticDuplicateDiagnostics`（`exact_normalized_label_only`、3/3 pair=0）を保存した。これは資料21の方針どおり
自動rejectを行わず人間/Codex確認材料にする扱いを実装・実行確認したものである。ただし完全一致label以外の同義語・
同一人物・scene anchor内の重複は検出しない。したがって「重複がなかった」ことの証明ではなく、
semantic duplicate diagnosticsは**限定的な観測として確認済み**であり、意味重複の自動判定へは昇格させない。

Codex preview確認では、gardenは庭園＋建築模型＋人物＋石灯籠、foodは背景なしで花工芸・皿・モンブラン等、
kanazawaは夜庭園＋人物＋皿＋モンブランの4 Layerとして読めた。Foodの背景なしと各previewの自由な重なりは
§8.49/§8.50の人間判断によりfailureにしない。Kanazawaの人物左縁には暗い不規則な領域が見えるが、選定Maskの
component=1 / hole=0だけでは、被写体と連結した背景混入か意図的な衣服輪郭かを断定できない。今回の観測は
その種の意味品質を自動合格に変えるものではない。

この結果はPR #6 / #7の採否、通常Profileの構図、前景下寄せcandidate、人間の最終視覚判断を変更しない。
観測形式の実装は通常Profile挙動を変えないため、採用品としてAI内部設計に保持する。残る§8.46の未達は、
`kind / semantic_role / extraction intent`の意味重複、無効なSemantic組合せの網羅的reject、
安全に直せないComposition違反のfailure条件、および人間目視を含む最終品質判断である。進捗は**91%のまま**とする。

実装検証として、generator / real AI pipeline / frontend handoff bundleのfocused pytestは**35 passed**
（FastAPI/httpxの既知deprecation warning 1件）、backend仮想環境での`validate_contracts.py`と`git diff --check`はpassした。
システムPythonでのcontract validatorは`jsonschema`未導入のため実行不能だったが、依存を持つbackend仮想環境で同一検証を
成功させた。これは契約や生成挙動のfailureではない。

### 8.59 資料20との現行状態照合 — 更新は行わず差異を記録（2026-09-04）

資料21を優先して`docs/ai/20_AI_PROCESSING_SEQUENCE.md`とcurrent implementationを照合した。資料20は
Git管理外（untracked）の既存ファイルであり、AI側の品質記録先として指定された資料19以外を、明示的な依頼なしに
上書きしない。従って資料20そのものは変更していない。

ただし資料20には「PR #6 / #7はレビュー中」「PR #7がmainへ入るまで通常生成の確定挙動にしない」という古い記述がある。
current implementationの`Settings`は`closed_hole_fill_enabled=true`、`micro_island_cleanup_enabled=true`であり、
人間判断§8.51と今回の§8.58 Real runもこの採用済みbaselineを使用した。前景下寄せ候補は
`composition_foreground_bottom_instruction_enabled=false`、architecture v3 / coherent group / narrow-gapは未採用、
`composition_overlap_instruction_enabled=false`のままである。

以後の品質判断では、現行方針の正本を資料21・資料19・current implementationとし、資料20の上記箇所を採否の根拠に
用いない。資料20をcurrent sequenceとして同期する必要がある場合は、ファイル所有者が確認してから別のdocs更新として扱う。
この照合はGemini API、通常Profile、品質閾値、Contractを変更しない。進捗は**91%のまま**とする。

### 8.60 前景Layer下寄せ — 人間判断Aにより通常Profileへ採用（2026-09-04）

§8.56の人間判断で**A（採用）**が選択された。これにより、
`COMPOSITION_FOREGROUND_BOTTOM_INSTRUCTION_ENABLED`の既定値をtrueへ変更し、通常ProfileのGemini構図Promptで
「前景として意図するsubjectは、適切な場合に背景・中景より下側へ置く」という緩い好みを有効にした。
`GeminiComposer`と`GeminiArtworkGenerator`の直接利用時の既定値も同じくtrueとし、Settings経由と内部既定の意味を一致させた。
環境変数でfalseを明示すれば、比較・切り戻しは引き続き可能である。

これは座標を決定論的に補正する実装でも、最前面を常にCanvas下端へ固定する規則でもない。§8.56の実Gemini評価
`poc-output/foreground-bottom-prompt-20260904/quality-evaluation-20260903-154427/summary.json`では、GardenとKanazawaは
最前面が下側に置かれた一方、Foodの花工芸はbottom gap=0.2959で反例だった。従って採用後も「毎回下寄せされる」ことを
合否条件にはせず、subjectの視覚的同一性、Canvas内配置、既に人間が許容した自由な重なり・背景なしを優先する。

今回の変更は既存candidateのdefaultを切り替えただけで、Semantic model、Gemini API呼出し、Segmentation、mask補正、
Quality Gate、Contractを変更しない。採用判断の根拠となった上記3ケースの実呼出しはすべて`gemini-3.5-flash-lite`、
`MOCK_AI=false`、3/3成功・4 Layer・全Layer Canvas内である。次回の通常Profile Real runでは、artifactの
`qualityFeatureFlags.compositionForegroundBottomInstructionEnabled=true`を回帰確認する。進捗は**91%のまま**とする。

### 8.61 前景Layer下寄せ採用後の固定3回E2E — Semantic接続失敗（2026-09-04）

§8.60で人間判断Aにより通常Profileへ採用した前景Layer下寄せについて、資料21 §5.2の確率的変更の
最低回数を満たすため、Supplemental固定3 case（garden-architecture / food-and-craft / kanazawa-memory-mix）×
`physical_layer_v2` × 3回、計9回を新規実行した。artifactは
`poc-output/foreground-bottom-default-20260904/quality-evaluation-20260903-180828/summary.json`である。

実行前のSettingsとsummaryの双方で、`GEMINI_MODEL=gemini-3.5-flash-lite`、`MOCK_AI=false`、
`SEGMENTATION_BACKEND=efficient_sam_onnx`、closed-hole fill / micro-island cleanup=true、overlap instruction=false、
**foreground-bottom instruction=true**を確認した。入力hashとmemoryText hashは各recordへ保存されている。
別model、fallback、Mock、candidate数、Semantic Prompt、Quality Gate、Segmentation条件の変更は行っていない。

| case | 実行数 | success | failure | failure stage | error type |
| --- | ---: | ---: | ---: | --- | --- |
| garden-architecture | 3 | 0 | 3 | semantic | AiError |
| food-and-craft | 3 | 0 | 3 | semantic | AiError |
| kanazawa-memory-mix | 3 | 0 | 3 | semantic | AiError |

全9件はSemantic Planning中に停止し、`composition_elapsed_ms=0`、candidate数0、Mask / Artwork / RGBA Layer /
composition previewはいずれも0件だった。従って今回のartifactにはCodexが画像として確認できる生成物がなく、
前景下寄せ、Mask品質、4 Layer、Canvas bounds、構図品質の採否を判断する材料はない。人間の新たな品質判断も求めない。

private入力をこれ以上送らず、同一実行環境で画像・memoryTextを含まない最小Structured Output疎通を`gemini-3.5-flash-lite`へ
1回だけ行った。その結果も`AiError`で、cause type=`ConnectError`、HTTP statusなし、request IDなしだった。
これは画像payload、前景下寄せPrompt、Segmentationの前に接続が確立していないことを示す補助診断であり、providerの内部状態、
利用状況グラフ、API Key、または9失敗の恒久原因を特定するものではない。

失敗9件は削除・成功への置換をせず保存した。接続状態が回復するまで同じprivate datasetの追加再送信は行わない。
§8.56の3/3成功E2Eと§8.60の人間採用は残すが、この9件は採用後の通常Profile品質を再確認できなかった失敗証跡として併記する。
次のReal E2Eは、非private疎通で同modelの接続回復を確認できた後にだけ、固定条件のまま別artifactへ再計画する。
実装の静的回帰として、backend全testは**76 passed**（FastAPI/httpxの既知deprecation warning 1件）、
Ruff check / format、backend仮想環境でのContract validation、`git diff --check`はpassした。
進捗は**91%のまま**とする。

### 8.62 内部Semantic Model正規化 — scene anchorとsubject metadataの重複を解消（2026-09-04）

資料21 §1.1 / §8の「`kind` / `semantic_role` / `extraction_mode`を二重管理しない」と、§8.46で残っていた
内部Modelの差異を、AI内部型だけで解消した。共有`contracts/`、公開API、通常Profileの候補数・Semantic Prompt・
Quality Gate・Segmentation・Mask補正・Composition設定は変更していない。Gemini APIとprivate入力の送信も0回である。

`VisualElementCandidate`では、`kind=scene_anchor`をscene anchorの唯一の種別情報とした。
scene anchorの`semantic_role`と`extraction_intent`はともに`None`へ正規化され、subjectだけが
`semantic_role`（general / architecture_*）と`extraction_intent`（single_form / coherent_group）を持つ。
旧Saved Planにある中立な`semantic_role=general`と`extraction_intent=scene_anchor`は、読み込み時に安全に除去して
互換を維持する。一方、scene anchorに`architecture_primary`等のsubject role、または`coherent_group`を持たせる組合せは
Pydantic validatorで明示的に拒否する。

同時にprivate handoff artifactのscene anchor `semanticRole`は`null`となる。これはArtwork Data / Asset Manifestへ
新fieldを追加したものではなく、従来からprivate診断にだけ含めていた内部metadataの意味を正規化した変更である。
既存artifactは書き換えず、新規runだけがこの表現を使う。

機械検証は、legacy scene anchorの正規化、scene anchorへのsubject metadata拒否2通りを追加し、backend全test
**79 passed**（FastAPI/httpxの既知deprecation warning 1件）、Ruff check / format、backend仮想環境でのContract validation、
`git diff --check`をpassした。これにより最終設計チェックの「kind / semantic_role / extraction modeの意味重複」と
「無効な組合せを内部Modelで表現または拒否」のうち、内部canonical model / validatorの範囲は確認済みとする。

ただしGemini Structured Output schemaは、互換上のscene-anchor表現を受け取り得るため、上記のcanonicalizationが必要である。
この変更はschema自体のconditional制約を追加したものではなく、実Gemini出力の再確認は接続回復後の次回固定E2Eで行う。
進捗は**91%のまま**とする。

### 8.63 資料21 §1.1 最終設計チェック — current implementation再監査（2026-09-04）

§8.58 / §8.62までのcurrent implementationとprivate artifactを、資料21 §1.1の最終設計図に対して再監査した。
この監査はGemini API、private入力、品質設定を変更しない。対象codeは`internal_models.py`、`gemini.py`、
`assembly.py`、`frontend_handoff_bundle.py`、quality runnerと、その全backend test 79 passedである。

| 設計チェック | 判定 | current evidence / 限界 |
| --- | --- | --- |
| subject / scene anchor経路 | 確認済み | `kind`で分岐し、scene anchorは矩形Crop、subjectだけがcomponent Segmentationへ進む。 |
| kind / role / extraction intentの意味重複 | 確認済み | §8.62でscene anchorのsubject metadataを`None`へ正規化した。 |
| 無効な組合せの内部拒否 | 確認済み | scene anchorのsubject role / coherent_groupはvalidatorでreject。Gemini schemaのconditional制約は未使用だが、Model境界で拒否する。 |
| 旧Saved Plan互換 | 確認済み | legacyの`general` / `scene_anchor`重複値を読み込み時にcanonicalizeし、既存artifactは非破壊で保持。 |
| Raw / aggregation / Normalized diagnostics | 確認済み | §8.58のReal runでstage別artifact・candidate単位のfill量を保存。scene anchorは矩形Cropのためnormalized stageのみ。 |
| single_form / coherent_groupの品質条件 | 確認済み | single_formはphysical modeで連続Layer以外をreject。coherent_groupはrequired保持を計測するが、§8.45により通常Profileでは不採用。 |
| NormalizationのPolicy・結果 | 確認済み | closed-hole fill / micro-island cleanupの実効flagとcandidate単位の適用量をartifactへ保存。 |
| scene anchorの計画・選定上限 | 確認済み | prompt/schemaは最大2候補、`_select_layers`は最大1候補を選定。 |
| semantic duplicate | 確認済み（観測限定） | §8.58のexact normalized label diagnosticsは自動rejectせず、人間/Codexの材料に限定する。同義語・同一人物検出は未実装。 |
| Composition統合計測 / recompose上限 | 確認済み | bounds / bottom gap / overlap / layer順をprivate diagnosticsへ集約し、bottom-gap再構図は最大1回。 |
| 安全に直せないCompositionの扱い | 確認済み | candidate ID不一致、必要Layer不足、scene anchorの必要幅不成立は`AiError`で成功扱いにしない。自由なsubject overlap・背景なしは§8.49/§8.50の人間判断により自動failureにしない。 |
| 採用品だけの通常Profile統合 | 確認済み | closed-hole fill、micro-island cleanup、前景下寄せの緩い好みだけを有効化。v3 / coherent_group / narrow-gap / overlap強制は非採用。 |

この再監査により、資料21 §1.1の内部設計チェックは、未確認だった二重管理・通常経路のRaw/Normalized・
Normalization適用量・Composition layer diagnosticsを含め、**実装または意図的な非採用の扱いとして一項目ずつ確認済み**とする。
ただしこれはcurrent codeの設計監査であり、§8.61の接続失敗により通常Profileの新既定（前景下寄せ=true）を
Locked regression-6 + Supplementalの必要回数で再実行できたことを意味しない。実Gemini確認とCodex画像確認は、
接続回復後の固定E2Eに残る。

進捗は資料21 §17の16条件を同じ重みで数え直し、architecture v3だけが「統合時のCloud Run外部証跡待ち」の
仮完了0.5点、今回完了した最終設計チェックを1点、他14条件を完了1点として、
**15.5 / 16 = 97%**へ更新する。§8.61の失敗9件は既存の成功品質artifactを置き換えず、
前景下寄せ=trueの再確認を次回固定E2Eへ残す証跡である。

### 8.64 Gemini接続再確認 — endpoint TCP未到達（2026-09-04）

§8.61から時間を置き、private画像・memoryTextを含まない最小Structured Output疎通を、同じ
`gemini-3.5-flash-lite`へ1回だけ再実行した。結果は再び`AiError`、cause type=`ConnectError`、
HTTP statusなし、request IDなしだった。Gemini APIの別model、fallback、Mock、private入力の送信は0回である。

API payloadや認証前のネットワーク層を切り分けるため、`generativelanguage.googleapis.com:443`のDNS/TCPだけを確認した。
DNSは解決できたがTCP接続は`false`だった。WinHTTPはdirect accessで、`HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY` /
`NO_PROXY`はいずれも未設定だった。したがって、この端末・この時点では名前解決後にGemini endpointへTCP接続できず、
§8.61の9件のSemantic失敗と整合する。

これはAPI Keyの有効性、providerの稼働、組織ネットワークの意図、利用状況グラフ、または恒久的な障害原因を証明しない。
ただしTCPが回復するまで、同じprivate固定datasetを追加送信しても品質証跡は増えないため再実行しない。
次のAI側Real E2Eは、まずこの非private最小疎通とTCP到達が回復したことを確認してから、同一条件・別artifactで開始する。
進捗は**97%のまま**とする。

追記: API・private入力を使わないTCP再確認も`TcpTestSucceeded=false`だった。名前解決の有無はこの簡易probeでは
独立に判定せず、到達しないTCP結果だけを採用する。接続状態に変化がないため、同一時点での追加API probeやprivate E2Eは行わない。

再追記: 上記と独立した3回目のAPI非使用TCP確認も`TcpTestSucceeded=false`だった。これにより、同じ外部接続条件が
3回連続で未解決であることを確認した。AI側だけでTCP経路を変更したり、別Gemini model／Mock／private再送信へ切り替えたりは
しない。Real E2E再開にはendpointへのTCP 443到達という外部状態の変化が必要であるため、このgoalは接続回復または
Geminiへ到達できる承認済み実行環境が得られるまでblockとする。進捗は**97%のまま**とする。

### 8.65 最終統合判断 — Cloud Runを使わず、frontend E2Eで確認（2026-09-04）

人間から「Cloud Run環境では実行しない」「フロントからのE2Eは通った」と報告を得た。従ってarchitecture v3について、
Cloud Run固定36 runをこのフェーズの完了前提にはしない。`physical_layer_v3_architecture`は品質失敗と断定するのではなく、
**このフェーズの通常Profileには不採用**と決定する。通常Profileは引き続き`physical_layer_v2`であり、将来v3を再評価するなら
別PoCとして固定環境・flash-lite条件を新たに定義する。これにより、資料21 §17の「architecture v3の採否」は明確になった。

frontend E2E成功は人間による統合確認として記録する。AI側で実行ログ・model名・private生成artifactを直接取得していないため、
この報告をGemini quality runやflash-liteの新証跡へ読み替えない。一方、frontend側で`npm run lint`、`npm run test`
（**11 passed**）、`npm run build`を実行し、TypeScript buildと共通Artwork表示経路の静的回帰を確認した。

資料21 §17の最終監査は次のとおりである。

| 条件 | 判定 | 根拠 |
| --- | --- | --- |
| 1 architecture v3 | 完了（不採用） | 本節の人間方針。通常Profileはv2を維持。 |
| 2–8 個別品質仮説 | 完了 | PR #6 / #7採用、coherent_group・narrow-gapの不採用理由、背景・duplicate・overlapの扱いは§8.45、§8.49–§8.51、§8.58に記録。 |
| 9 採用品の統合 | 完了 | closed-hole fill、micro-island cleanup、前景下寄せの緩い好みだけを通常設定で有効化。 |
| 10 固定dataset + Supplemental | 完了 | §8.44のLocked 18件 + Supplemental 9件の機械／Codex証跡と、今回のfrontend E2E人間確認。§8.61の接続失敗9件は成功証跡を置換しない。 |
| 11–13 記録・baseline・設計監査 | 完了 | 資料19の実行記録、§8.51 baseline、§8.63 final design check。 |
| 14–15 Gemini model固定 | 完了 | 最終採否に使うReal Gemini artifactはすべて`gemini-3.5-flash-lite`。旧model runとfrontend E2E報告はmodel品質証跡に混ぜない。 |
| 16 速度改善へ進む状態 | 完了 | v2 baselineと採用品／非採用品が明確で、以後は品質を変えない計測から開始できる。 |

backend全test 79 passed、frontend test 11 passed、frontend lint / build、Ruff、Contract validation、
`git diff --check`が通っている。以上により、資料21のAI品質フェーズは**16 / 16 = 100%**とする。
接続不能のlocal Gemini E2Eは§8.61 / §8.64に失敗証跡として残し、今後のネットワーク回復時に新規品質runを行う場合も、
この完了判定の成功recordを上書きしない。

### 8.66 生成速度 — 品質PRから分離し、追いPRで扱う（2026-09-04）

人間から「生成速度が10分以上かかり実用にならない。今回の品質PRはマージせず、将来の速度改善を追いPRにする」と方針を得た。
この方針に従い、candidate数、Semantic Prompt、Quality Gate、Segmentation条件を今回の品質PRで速度目的に変更しない。

§8.44の成功したfinal E2E 26件を、PCのスリープ・給電不足による待機時間が混ざり得ることを明記して再集計した。

| 指標 | 最小 | 中央値 | 最大 |
| --- | ---: | ---: | ---: |
| total elapsed | 3.1分 | **12.7分** | 69.5分 |
| Semantic Planning | 26.1秒 | 39.5秒 | 103.5秒 |
| Composition | 4.9秒 | 7.8秒 | 63.7秒 |
| EfficientSAM Segmentation合計 | 2.6分 | **11.8分** | 67.6分 |
| RGBA Layer build合計 | 0.8秒 | 10.6秒 | 21.4秒 |

total elapsedとSegmentationには端末の休止時間が入り得るため、上表を絶対的な性能SLOにはしない。
ただし中央値でもSegmentationが総時間のほぼ全てを占め、Semantic / Composition / RGBA buildより優先して調べるべきことは
機械値から明確である。速度改善PRでは、固定baselineを壊さないよう、まずCPU並列度、ONNX session / input preparation、
candidateごとのSegmentation stage内訳を計測し、品質を変えない改善から独立PoCする。candidate数削減、Semantic Prompt、
Quality Gate、Segmentation quality条件を変える案は、その後に品質比較を伴う別仮説として扱う。

今回作成するPRは品質改善と品質証跡のレビュー用であり、**マージを求めない**。速度改善の実装・計測・追いPRはこのPRを
baselineとして別に作成する。進捗は品質フェーズ完了の**100%**を維持する。

### 8.67 品質ベースラインPR作成 — マージ保留（2026-09-04）

品質フェーズ完了後、人間の明示許可によりcommit `dae8c0e` を
`codex/ai-quality-baseline-review`へpushし、PR [#8 AI品質ベースライン確定（マージ保留）](https://github.com/Ruaku1352/omoi/pull/8)
を`main`向けに作成した。PRはOPENでdraftではない。

PR本文には、採用品、flash-lite固定の品質証跡、local Gemini接続失敗の扱い、backend 79 passed、frontend 11 passed、
lint / build / Ruff / Contract validation / diff checkと、速度改善を混ぜない方針を記載した。人間の方針どおり、
このPRはレビューと品質baselineの固定のためだけに使い、**現時点でmergeしない**。

速度改善はこのPRの差分や品質artifactをbaselineとして、別PRでCPU Segmentationのstage別計測と品質を変えない改善から扱う。
候補数、Semantic Prompt、Quality Gate、Segmentation quality条件を変える場合は、さらに独立した品質比較PoCを伴う。

### 8.68 資料22への移行前監査 — 速度改善を開始可能、品質進捗は97%へ訂正（2026-09-04）

新設の`22_AI_PERFORMANCE_OPTIMIZATION_PLAN.md`を全文確認し、PR #8 head
`4cc70570f99b582fdbb8d7cc652e590e13a01fc0`、current implementation、資料19 §8.61〜§8.67、
未追跡の資料20を照合した。資料22の開始を妨げる、人間判断待ちの品質・費用・Cloud Run・外部GPU・private画像送信の
条件はない。Speed PRは計画書だけでは作らず、最低1件の実速度改善を固定条件で5回測定してから作成する。

ただし、§8.65の「資料21を16 / 16 = 100%」という記録は、§8.61の**foreground-bottom instruction=true**での
固定3 case × 3回がGemini接続前のSemantic stageで全9件失敗し、§8.63で15.5 / 16 = 97%と再監査している事実と
両立しない。frontend E2E成功の人間報告は統合確認として尊重するが、AI側でmodel名・artifact・設定を直接確認して
いないため、固定datasetのReal Gemini成功artifactへ読み替えない。以後、資料21の品質進捗は**97%**、
残件は「Gemini到達可能な環境でcurrent通常Profile（foreground-bottom=true）の固定Real E2Eを再確認」とする。

一方で、資料22のP0〜P6はGemini APIを呼ばない固定Saved Plan / bboxの決定論的Segmentation比較であり、
この残件に依存しない。品質コード基準はPR #8 headのまま固定し、候補数、Semantic / Composition Prompt、
Quality Gate、Segmentation解像度・bbox・retry、closed-hole fill、micro-island cleanup、Contractを変えない。
速度の候補変更はTier A parity、出力差が出る場合はTier Bの画像比較と人間判断を必須とする。

P0-0としてlocal branch `codex/ai-speed-optimization`を上記SHAから作成した。資料20は引き続きuntrackedであり、
本移行では変更・commit対象に含めない。進捗は、品質フェーズ**97%**、速度改善フェーズ**5%**（branch作成・
計画移行前監査完了、hardware fingerprintとbaselineは未計測）とする。

### 8.69 資料22 P0-A — local hardware / runtime fingerprintを保存（2026-09-04）

資料22 §6.1のP0-Aとして、`scripts/capture_performance_environment.py`を追加し、private artifact
`poc-output/performance-optimization-environment/environment.json`へ実行環境を保存した。CPUは
12th Gen Intel(R) Core(TM) i7-1260P（physical 12 cores / logical 16 processors）、RAM 15.68 GB、
OSはWindows 11 Home 10.0.26200、GPU列挙はIntel Iris Xeである。backend仮想環境はPython 3.13.13、
NumPy 2.5.2、Pillow 12.3.0、ONNX Runtime 1.29.0、available providersは
`AzureExecutionProvider`と`CPUExecutionProvider`だった。EfficientSAM-Ti ONNXは41,365,520 bytes、
SHA-256 `143c3198a7b2a15f23c21cdb723432fb3fbcdbabbdad3483cf3babd8b95c1397`である。

初回の非昇格WMI読取はアクセス拒否となったため、スクリプトはWMI失敗時に空値／0を正常値として保存しないよう
`ErrorActionPreference=Stop`を設定した。昇格したread-only実行で上記fingerprintを再取得している。
artifactは`.gitignore`済みの`poc-output/`配下であり、環境変数・API Key・private画像・memoryTextを含めない。

Power schemeは「パナソニックの電源管理」と記録した。battery raw値をAC接続の証拠へ読み替えず、baselineの5回計測は
AC給電、sleep無効、蓋を閉じない、重い並列作業なしを実行直前に満たしてから開始する。現時点ではbaselineを
実行していない。進捗は、品質フェーズ**97%**、速度改善フェーズ**15%**（P0-0 / P0-A完了、P0-B timing・
deterministic benchmark・baseline 5回は未着手）とする。

### 8.70 資料22 P0-B — 詳細stage timingと決定論的benchmarkを追加（2026-09-04）

旧PR #3 `chore/ai-performance-timing`（`7695698`）をcurrent品質baselineへそのままmergeせず、
EfficientSAMの1 prompt attemptに必要な部分だけを移植した。`SegmentationResult`の内部専用
`SegmentationTimings`へ、`resize`、`tensor preparation`、monolithic `ONNX inference`、
`mask restore`のelapsed millisecondsを記録する。Artwork Data、Asset Manifest、公開API、candidate数、
Prompt、bbox、retry、Quality Gate、closed-hole fill、micro-island cleanup、Compositionは変更していない。

`scripts/run_deterministic_segmentation_benchmark.py`はprivateなSaved Semantic PlanとsourcePhotoIndex順の
写真を引数で受け、Geminiを呼ばず、scene anchorを除くsubject componentの固定bboxを順序どおり実行する。
warm-up後の各runについてmask SHA-256、score、stage内訳、totalをprivateな`poc-output/`へ保存し、
同一5 run内および必要時のreference artifactに対するbinary Mask hash一致をTier A gateとして強制する。
品質評価・retry選択・Mask補正・RGBA・Compositionを測定対象に混ぜないため、P1/P2以降のSegmentation
構造改善を固定入力で比較できる。

`backend/tests/test_segmentation.py`を追加し、ONNX Sessionをfakeしたstage timingの回帰を確認した。
focused backend testは**32 passed**（FastAPI/httpxの既知deprecation warning 1件）、Ruff check / format、
`git diff --check`はpassした。baseline 5回は、AC給電、sleep無効、蓋を閉じない、重い並列作業なしを実行直前に
満たしたことを確認してから開始する。進捗は品質フェーズ**97%**、速度改善フェーズ**25%**
（P0-0 / P0-A / P0-B完了、baseline 5回とP1以降は未実施）とする。

### 8.71 資料22 baseline / P1 — 再起動後の5回×2比較、P1は保留（2026-09-04）

再起動後、Windowsの起動時刻、BatteryStatus=2（AC給電）、残量99%を確認した。計測中だけAC sleepを0秒へ
設定し、各計測後に元の3600秒へ復帰した。Geminiは0回である。固定対象は
`garden-architecture`のSaved Semantic Plan、5写真、scene anchorを除く10 subject bboxで、warm-up 1回の後に
EfficientSAM-Ti monolithic ONNXを計測した。

P0 baselineの最初の5回は、run totalの中央値**17,170.49 ms**（min 16,258.58 / max・p95 19,005.95 ms）だった。
per prompt中央値はresize 91.14 ms、tensor 10.80 ms、ONNX inference 1,525.44 ms、mask restore 45.13 msで、
5 runすべての固定bbox binary Mask hashは一致した。private artifactは
`poc-output/performance-optimization-baseline-reboot-20260904/benchmark.json`である。

P1では`PreparedSegmentationImage`を追加し、同一generation request内でsource photoごとのresize / tensorを
1回だけ行い、candidate / retryは`segment_prepared`へ渡すようにした。segmenterがこの能力を持たない既存test fakeは
従来の`segment`経路を使うため、上位のcandidate / quality制御を変えない。fixed benchmarkにも
`--reuse-prepared-images`を追加し、source preparationをrun totalへ含めつつ、baseline artifactとのbinary Mask hash
完全一致を強制した。

P1の最初の5回は中央値**15,786.37 ms**でbaseline比8.06%短縮だった。資料22 §16.2の5〜10%規則に従い、
順序を反転した追加5回ずつを続けた。ABBA順の10回ずつ合算ではbaseline中央値**16,276.01 ms**、P1中央値
**15,760.98 ms**、短縮**515.04 ms（3.16%）**となった。P1の10回すべてでself Mask hash一致、baseline referenceとの
Mask hash一致、bbox key一致を確認したが、短縮量は<5%であり、P1単独の採用は**保留**とする。

benchmark artifactは`poc-output/performance-optimization-baseline-*-20260904/`および
`poc-output/performance-optimization-p1-prepared-cache*-20260904/`でGit管理外に保存した。P1実装のfocused testは
**33 passed**（FastAPI/httpxの既知deprecation warning 1件）、Ruff check / format、`git diff --check`はpassした。
品質フェーズ**97%**、速度改善フェーズ**50%**（P0 baselineとP1 comparison完了、P1採用保留、P2へ進行）とする。

### 8.72 資料22 P2 — split encoder / decoder + embedding cacheをTier A採用（2026-09-04）

公式yformer/EfficientSAMが案内する同一revision `d8dbb1e`のTi split ONNXをGit非管理の`backend/.models/`へ取得した。
encoder SHA-256は`84ed466ffcc5c1f8d08409bc34a23bb364ab2c15e402cb12d4335a42be0e0951`、decoder SHA-256は
`a62f8fa5ea080447c0689418d69e58f1e83e0b7adf9c142e2bd9bcc8045c0b11`である。公式exampleどおり、encoderへ
`batched_images`を1回入力し、decoderへ`image_embeddings`、従来と同じ2 corner box prompt / labels、
`orig_im_size`を渡す`EfficientSamSplitOnnxSegmenter`を追加した。

split経路は`PreparedSplitSegmentationImage`にembeddingを保持し、同一source photoのcandidate / retryでdecoderだけを
再実行する。`EFFICIENTSAM_ENCODER_MODEL_PATH`と`EFFICIENTSAM_DECODER_MODEL_PATH`が**両方**設定された時だけ
Generatorへ接続し、未設定時は従来のmonolithic ONNXを維持する。片方だけの設定は明示エラーにする。公開API、Artwork
Contract、candidate数、Prompt、bbox、retry、Mask品質規則、closed-hole fill、micro-island cleanup、Compositionは変更していない。

同じ再起動後AC給電・sleep無効条件、固定5写真 / Saved Plan / 10 subject bboxでwarm-up 1回＋**5回**を実行した。
total中央値は**9,408.28 ms**（min 8,214.10 / p95 10,338.84 ms）、P0 baseline初回中央値17,170.49 msから
**7,762.21 ms / 45.21%短縮**した。source photo 5枚ごとのencoder中央値は1,364.57 ms、10 bboxのdecoder中央値は
129.45 msだった。全5 runのself binary Mask hash、およびP0 baseline referenceとのbinary Mask hash / bbox keyは完全一致した。
private artifactは`poc-output/performance-optimization-p2-split-encoder-decoder-20260904/benchmark.json`である。

split adapter / path selectionのunit testと既存pipeline focused testは**36 passed**（FastAPI/httpxの既知deprecation
warning 1件）、Ruff check / format、`git diff --check`はpassした。P2は資料22 §15のTier Aを満たす品質非変更の
速度改善として**採用**する。品質フェーズ**97%**、速度改善フェーズ**70%**（P2採用、Speed PR作成条件を満たす）とする。

### 8.73 Speed PR #10作成 — P2の計測根拠を明記（2026-09-04）

P0 / P1 / P2のcommitを`codex/ai-speed-optimization`へpushし、PR #8
`codex/ai-quality-baseline-review`をbaseにしたstacked Speed PR
[#10 EfficientSAM Segmentationを高速化](https://github.com/Ruaku1352/omoi/pull/10)を作成した。
PR本文には固定5写真 / Saved Plan / 10 bboxでのP0 17,170.49 ms→P2 9,408.28 ms（**45.21%短縮**）、
5 / 5のTier A binary Mask hash一致、P1単独は3.16%のため保留、83 passed / Ruff / Contract validation、
local Gemini TCP未到達により未実施のReal E2Eを記載した。private写真、memoryText、artifact、model weightはPRへ含めない。

品質フェーズ**97%**、速度改善フェーズ**80%**（Tier A速度PR作成済み、Gemini到達可能環境でのfull E2Eと2分SLO確認が残る）
とする。

### 8.74 Speed PR #10 — TCP回復後Real E2Eの停止記録とGemini retry上限（2026-09-04）

`generativelanguage.googleapis.com:443`のTCP到達が`true`へ回復したため、AGENTS.mdで許可済みのprivate固定3 caseを
`gemini-3.5-flash-lite`、`physical_layer_v2`、P2 split ONNX、AC給電・sleep無効で再実行した。最初のcaseでは
Semantic Plan、bbox、raw / normalized Mask debug artifactまでは生成されたが、完了用の`metrics.json` / `summary.json`は
作られなかった。Gemini Compositionを含む完了結果・4 Layer・Contract・total elapsedを得る前に異常な長時間待機となったため、
private入力の追加送信を避けて実行プロセスだけを停止した。

SDKの1呼び出しtimeoutは120,000 msだった一方、SDK既定retryにより同じtimeout待機が連鎖し得ることをlocal package sourceで
確認した。`_generate_structured`の`HttpOptions`へ`HttpRetryOptions(attempts=1)`を明示し、Prompt、model、Schema、
Quality Gate、Segmentation、Composition規則は変えず、設定済みtimeoutで失敗を返すようにした。Unit Testは**33 passed**
（既知FastAPI/httpx deprecation warning 1件）で、timeoutとretry attempt=1を検証している。

retry上限後の同一通常Profile再試行でも、1件目が5分を超えてlocal CPU処理を継続し、`metrics.json` / `summary.json`を
生成しなかったため停止した。このrunはGemini待機ではなく、full-resolutionのclosed-hole fill・mask quality・RGBA asset buildを
含む実経路の局所処理も別途切り分ける必要を示すが、成功したE2E計測ではない。closed-hole fillを品質非変更で置換する
行区間labeling PoCもprivate raw Mask集合で開始したが、5回の比較完走前に改善傾向を示さず中止し、実装・script・testは
採用せず撤回した。private artifactはGit管理外に残すが、速度根拠・PR差分には使わない。

P2の固定Saved Plan Tier A（5 / 5 binary Mask一致、45.21%短縮）は有効なままである。一方、full E2Eの4 Layer / Contract /
current品質規則 / 2分SLOは未確認のままなので、Speed PRを完了扱いにしない。品質フェーズ**97%**、速度改善フェーズ
**80%**を維持する。AC sleep設定は各停止後に3600秒へ復帰した。

### 8.75 P2 + SciPy後処理最適化 — 5写真Real E2Eを65.82秒で達成（2026-09-04）

full-resolutionのclosed-hole fillとmicro-island cleanup／diagnosticsにあったPython連結成分探索を、同じ8近傍接続性の
SciPy実装へ置換した。private raw Mask 7枚のclosed-hole fillは各5回で、旧中央値136,833.68 msから
**1,576.60 ms（86.79倍）**へ短縮し、全output hashは完全一致した。候補数、Prompt、bbox、retry、Quality Gate、
closed-hole fill／micro-island cleanupの規則、Composition、Contractは変更していない。backend正規testは**84 passed**、
Contract validationと`git diff --check`もpassした。

同じ再起動後AC給電・sleep無効条件で、`gemini-3.5-flash-lite`／`physical_layer_v2`／P2 split ONNXの代表5写真caseを
Real E2Eした。**4 Layer**、Contract validation成功、total **65,816.47 ms（65.82秒）**、Semantic 28,332.28 ms、
Composition 7,960.68 ms、12 candidateで成功した。private artifactは
`poc-output/performance-optimization-p2-scipy-real-e2e-3-20260904/`に保存し、AC sleepは3600秒へ復帰した。
品質フェーズ**97%**、速度改善フェーズ**100%**とする。
