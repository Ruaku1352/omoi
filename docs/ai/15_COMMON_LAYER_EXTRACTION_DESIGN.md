# 共通Layer抽出設計案 — 単体と関連要素群を同じ仕組みで扱う

## 状態

**【提案 / 未実装】**。この資料はAI・画像処理担当の設計・検証方針であり、Artwork Data、
API Contract、Frontend、Physical Outputの責務を変更しない。実装前に固定datasetで比較評価する。

## 1. 背景

現在の `physical_layer_v2` は、`scene_anchor` 以外のLayerを最終Maskが単一連結となるよう
扱う。これは人物や皿のような単体を安定してLayer化するには有効だが、「皿に載った料理」の
ように、意味として一つの思い出でありながら画素上では複数領域になり得る対象を扱えない。

金沢ケースでは、Geminiが「金箔盆に載った甘味セット」を一つのbboxとして計画した。
EfficientSAMはbbox内で最も大きく明瞭なトレーを前景として選び、器・甘味を背景穴として
落とした。候補全体の非主成分は 7.88% であり、微小飛び地除去の対象ではない。

ここで閾値を緩めたり、`food` 専用の画像処理を加えたりしてはならない。必要なのは、
**一つのLayerに何を残すか**を、被写体カテゴリではなく抽出意図と構成要素の関係として
計画・検証する仕組みである。

## 2. 設計目標

1. 建築・人物・料理・小物を、被写体名による分岐なしで処理する。
2. 「人物＋手持ちの物」「建物＋一体の門」「器＋料理」のような関連要素群を、一つのLayerとして
   指定できる。
3. 意味のない離れた背景片や、4層を埋めるためだけの寄せ集めを採用しない。
4. 既存の元写真 → Gemini bbox → EfficientSAM → RGBA PNG の経路を維持し、一枚絵の生成や
   セマンティックな画像合成を行わない。
5. AIが決めるのは画像上のLayer品質までに留め、支柱・接合・STL・実寸閾値はPhysical Output
   担当へ持ち込まない。

## 3. 共通の抽出意図

Semantic Planningは、候補を被写体カテゴリではなく、次の三つの `extraction_intent` に分類する。

| Intent | 例 | 抽出方法 |
| --- | --- | --- |
| `single_form` | 人物、建築本体、皿、置物 | 1つ以上のbboxから、最終的に一つの独立した形を得る。 |
| `coherent_group` | 器＋料理、人物＋手持ちの扇子、建物＋一体の門 | 関係する要素をcomponentごとに切り出し、unionして一つのLayerにする。 |
| `scene_anchor` | 庭、室内、風景 | 背景として機能する広い矩形範囲をLayerにする。 |

`architecture_primary` のような既存の意味上の優先度は、作品で建築本体を残すための**選定情報**
として維持してよい。一方で、SegmentationやCleanupの方式を「建築だから」「料理だから」と
分岐させない。

## 4. 内部Semantic Planの拡張案

これは `backend/ai/` 内部だけの提案であり、外部Schemaへ追加しない。正確なField名は実装時に
決めるが、少なくとも以下の意味をStructured Outputで受け取る。

```python
class VisualElementCandidate(BaseModel):
    candidate_id: str
    label: str
    source_photo_index: int
    importance: float
    kind: Literal["subject", "scene_anchor"]
    extraction_intent: Literal["single_form", "coherent_group", "scene_anchor"]
    components: list[SegmentationComponent]

class SegmentationComponent(BaseModel):
    component_id: str
    label: str
    box_2d: Box2D
    required: bool
    relation_to_primary: Literal["primary", "contained", "supported_by", "attached"]
```

例として「甘味セット」なら、トレーまたは器を `primary`、器に載る甘味を `contained` /
`supported_by` として、別bboxで返す。スプーンや無関係なテーブル面を含めるかは、候補の
`selection_reason` とmemoryTextに照らし、Semantic Planningが明示する。

この情報は「複数componentを無条件に許す」ものではない。必須componentが一緒に存在することで
はじめて候補のidentityが成立する、という検証可能な宣言である。

## 5. 処理フロー

```text
Semantic Planning
  └─ 抽出意図・必須component・関係をStructured Outputで計画
       ↓
componentごとの bbox → EfficientSAM Mask
       ↓
candidate単位の Mask union
       ↓
共通Quality Check
  ├─ 単体: 微小な無関係islandだけ除去
  ├─ 関連要素群: 必須componentの保持、背景混入、関係の成立を確認
  └─ 背景: scene anchorとして範囲品質を確認
       ↓
必要時のみ、GeminiによるLayer内容のStructured Verification
       ↓
RGBA Layer → Layer Selection → Composition
```

### 5.1 Component Segmentationとunion

`coherent_group` は、候補全体を一つのbboxでsegmentしない。器、料理、手持ち物などのcomponentを
別々にsegmentし、既存のmask unionでLayerを作る。これにより、主物体だけを前景にして
必要な内容物を穴として落とす失敗を避ける。

union後も、離れたMask同士を大きく橋渡ししない。2026-09-02の評価者指示により、窓や建築の
開口部を含め、**画像端の背景とつながらない透明な穴は全て機械的に埋める**。これは意味理解を
追加せず、Mask形状だけで処理する。外側へ開いた透明領域は残るので、離れたcomponent間を結合する
処理ではない。

細い透明gapを閉じるmorphological closingは、承認済み`coherent_group`のunion直後だけで比較する
PoCとして別に維持する。人物＋ボールの2件では2 px closingを比較済みだが、建築での確認は未完了で
ある。物理的な支持方式・実寸の決定は引き続き対象外である。

### 5.2 共通Quality Check

Quality Checkは、被写体名ではなく抽出意図に基づく。

| Check | `single_form` | `coherent_group` | `scene_anchor` |
| --- | --- | --- | --- |
| Empty / full / prompt外 | reject | reject | reject |
| 閉鎖した透明な穴 | 機械的に埋める | componentとunionの双方で機械的に埋める | 対象外 |
| 微小飛び地 | 主成分外の合計が設定値以下なら除去 | **必須componentは除去しない**。無関係な微小islandだけ除去候補 | 対象外 |
| 必須対象の保持 | Layer全体で確認 | componentごとに確認 | 範囲として確認 |
| 背景混入 | Layer全体で確認 | component・union双方で確認 | sceneとして許容範囲を確認 |
| 大きな分離 | candidateをrejectまたは再計画 | 関係性を検証してから判断 | 対象外 |

現在の `MASK_MICRO_ISLAND_MAX_AREA_RATIO=0.005` は、`single_form` の無関係なノイズを除去する
暫定設定として扱う。料理・器のような必須componentをこの面積比だけで消すことはしない。

### 5.3 Semantic Verificationと限定Recovery

Maskの面積・scoreだけでは「トレーだけで甘味が落ちた」ことを検出できない。そのため、候補が
`coherent_group` の場合、元写真、component bbox、合成Mask/RGBA previewをGeminiへ渡し、次を
Structured Outputで判定する。

- 宣言した必須componentが視認できるか
- 不要な背景が主題を壊していないか
- 一つのLayerとして候補labelのidentityを保つか

失敗時は最大1回だけ、component bboxまたはcomponent構成を再計画する。Retryの上限・入力・
結果・時間はprivate debug logに保存する。成功を装うMock fallback、無限Retry、完成画像の
再Segmentationは行わない。

## 6. Layer SelectionとComposition

`coherent_group` は複数assetではなく、union済みの**1 Layer**として選定・構図化する。これにより
Artwork Dataの可変長 `layers[]`、Layer AssetのRGBA PNG、`layerIndex` の既存Contractを維持できる。

Layer Selectionは、個別componentのscoreではなく、候補全体の以下を比較する。

- memoryTextとの関連性と候補のimportance
- 必須component保持の検証結果
- 背景混入・不要分離の有無
- Layer単独での視認性
- 既採用Layerとの重複

構図は既存のComposition処理を使う。AI担当は正規化座標上で読みやすい配置と過度な浮遊の抑制を
扱うが、支柱や接続部の追加、物理的な成立閾値を決めない。

## 7. 検証計画

### 7.1 固定dataset

新しい方式に都合のよい料理写真だけで判断しない。privateな固定datasetに、少なくとも以下を
含める。

- 単純な単体（皿・小物）
- 人物＋手持ち物
- 遮蔽された建築、複雑な背景の建築、細部の多い建築
- 器＋料理、トレー＋複数器、反射やテーブル背景のある食事
- 動物、植物、夜景、細い構造

各ケースには、評価者が事前に「残す必須要素」「明確に除外すべき背景」を記録する。写真・
memoryText・Real AI出力は `poc-images/` と `poc-output/` のprivate領域にのみ置く。

### 7.2 A/B評価

同一入力・model・環境変数で、現行と提案方式を比較する。Gemini出力には揺れがあるため、
候補や評価表は匿名化して人手確認する。

| 観点 | 主な判定 |
| --- | --- |
| Semantic | 思い出として適切な対象/要素群を選んだか |
| Source / BBox | 必須対象を含み、不要物を広く巻き込まないか |
| Mask | 必須component保持、背景混入、欠損、不自然な分離 |
| Layer | 単独で候補labelを理解できるか |
| Composition | 4 Layer全体が作品として読めるか |
| Contract | 4 Layer到達、RGBA Asset、Artwork / Manifest整合 |

成功率だけでなく、必須component保持率、背景混入によるreject率、再計画率、総時間を保存する。
少数の成功例だけで閾値・Promptを固定しない。

### 7.3 採用条件

実装を採用するには、少なくとも次を満たす必要がある。

1. 料理/器の例で、皿だけ・料理だけへの欠損を減らす。
2. 建築・人物・小物で明確な回帰を起こさない。
3. `coherent_group` が無関係な物体の寄せ集めを増やさない。
4. 4 Layer生成と既存Contractを壊さない。
5. 既存test、lint、format、Contract validationが通る。

## 8. 段階的な実装案

1. **観測**: 現行出力にcomponent単位の採用・欠損・union診断をprivate logとして追加する。
2. **Planning PoC**: `extraction_intent` とcomponent関係を内部Structured Outputに追加し、
   固定datasetでSemantic Planだけをレビューする。
3. **Segmentation PoC**: `coherent_group` のcomponent別segment・unionを実装し、現行とのA/Bを行う。
4. **Verification PoC**: GeminiのLayer内容検証と最大1回の再計画を追加し、品質向上とlatencyを比較する。
5. **採否判断**: 人手評価・性能ログ・回帰結果に基づき、Profileへ組み込むか判断する。

各段階で不合格なら次段階へ進めず、前段のartifactを根拠に設計を見直す。

## 9. 未決定事項と責任境界

| 項目 | 状態 | 決める担当/場 |
| --- | --- | --- |
| 料理Layerにスプーン・紙・トレーのどこまでを含めるか | 【確認待ち】 | Product / Designと画像評価で決める |
| 視覚的に分離したcomponentを1 Layerと見なす条件 | 【PoC後FIX】 | AI品質評価。物理的支持の可否は含めない |
| 支柱・土台・STL・実寸・許容gap | AIの対象外 | Physical Output担当 |
| Artwork Data / API Contractの変更 | 提案しない | 共通仕様の公開合意が必要 |
| SAM 2.1等への切替 | 【PoC後FIX】 | bboxが妥当でもMaskが悪い複数例で比較後に判断 |

## 10. 非対象

- `food` / `person` / `architecture` ごとの専用Mask後処理
- マスクの大きな橋渡し、元写真にない対象画素の生成
- 完成した合成画像の再Segmentation
- Physical Outputの製造制約をAIのArtwork Dataへ書き込むこと
- 少数テスト画像だけに合わせた閾値・Prompt調整
