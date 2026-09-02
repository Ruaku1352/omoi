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
