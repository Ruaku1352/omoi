# omoi 現況まとめ（9/3 時点）

橋内作成。統合作業の前提合わせ用。

---

## 1. 全体の状況

Real AI・非同期化・Frontend のポーリングまで、**コードはすべて main に入っている**。
残っているのは主に **GCP 側の Provisioning** と、そこに含まれる **Owner 権限が必要な作業**。

| 領域 | 状態 |
|---|---|
| Real AI（Gemini + EfficientSAM） | main 済み・Cloud Run 実測済み |
| 非同期 Job（Backend） | main 済み・**Cloud Run 未検証** |
| 非同期 Job（共通 Schema） | main 済み |
| ポーリング（Frontend） | main 済み・**未検証** |
| 物理出力 PoC | main 済み |
| Provisioning | **途中。Owner 権限待ちで停止中** |

---

## 2. Provisioning の途中経過

`docs/deploy.md` §3.1 / §6.3–6.6 に沿って進めている。

### 完了（Editor 権限でできた分）

- `firestore.googleapis.com` / `cloudtasks.googleapis.com` の有効化
- GCS バケット `omoi-506412-job-input` 作成（Job 入力写真の一時置き場）
- 同バケットに Lifecycle 設定（24 時間で自動削除）
- Cloud Tasks キュー `omoi-artwork-generate` 作成（max-attempts=5 / max-concurrent-dispatches=5）
- Secret `task-worker-token` 作成（Worker Endpoint 保護用の共有トークン）
- Service Account `omoi-task-invoker` 作成（Cloud Tasks が Worker を呼ぶ主体）

### 止まっているもの → もりかんさん（Owner）へお願いしたいこと

Editor 権限では実行できず、ここで止まっている。

```bash
# 1. Firestore データベース作成（Editor では権限エラーになった）
gcloud firestore databases create --location=asia-northeast1

# 2. Runtime Service Account へ Firestore 権限
gcloud projects add-iam-policy-binding omoi-506412 \
  --member="serviceAccount:161105379266-compute@developer.gserviceaccount.com" \
  --role="roles/datastore.user"

# 3. Runtime Service Account へ GCS 権限
gcloud storage buckets add-iam-policy-binding gs://omoi-506412-job-input \
  --member="serviceAccount:161105379266-compute@developer.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"

# 4. Cloud Tasks 用 Service Account へ Cloud Run 呼び出し権限
#    （Service Account 自体は作成済み）
gcloud run services add-iam-policy-binding omoi-backend \
  --region=asia-northeast1 \
  --member="serviceAccount:omoi-task-invoker@omoi-506412.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

# 5. Worker Token の読み取り権限
gcloud secrets add-iam-policy-binding task-worker-token \
  --member="serviceAccount:161105379266-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

**これが片付けば、Deploy と E2E 確認まではこちらで進められる。**

---

## 3. 実測結果（8/31・写真 5 枚）

条件は CPU 1 / Memory 2GiB / Concurrency 1 / timeout 600、`gemini-3.5-flash-lite`。
生成結果は 4 層・`aspectRatio` 1.4016（2L 判 Landscape）で、契約検証も通過。

| 項目 | 時間 |
|---|---|
| **実測（Request 全体）** | **4 分 10 秒** |
| `ai.total` | 234.5 秒 |
| ONNX inference（×11） | 114.4 秒（1 回あたり 10.4 秒） |
| `rgba_layer_build`（×5） | 53.4 秒（1.9〜10.0 秒とばらつき大） |
| `mask_quality_check`（×22） | 28.3 秒 |
| Semantic Planning | 27.7 秒 |
| Composition | 6.6 秒 |
| 画像デコード（×5） | 1.1 秒 |

### 分かったこと

- **ONNX inference が全体の 49%**。前後の resize / tensor 準備 / mask 復元は合計 1.4 秒しかなく、推論そのものが支配的。
- **候補 12 件のうち 3 件が rejected**（c_07 / c_08 / c_09）で、約 33 秒が捨てられている。component 段階では accepted だが、combined の quality check で落ちている。
- **写真サイズはほぼ効かない**。デコードは 1.1 秒（全体の 0.5%）で、Backend が `gemini_analysis_max_side=1536` で縮小するため、元が 3600px でも 2048px でも AI に渡る時点で同じ。

---

## 4. この期間に直した不具合

### `physicalOutput: null` による契約違反

Real 生成は `physicalOutput` を持たないが、Response Model が `null` としてシリアライズしていた。`contracts/artwork.schema.json` は object のみ許容し null を認めないため、**Real の応答だけが Schema 違反**になっていた。

共通 Mock は `physicalOutput` を持つため検証を通っており、Real 側の出力を検証する仕組みが無かったのが原因。技術設計 §19.6 の「Real 生成結果が同じ Schema を満たすことを接続確認条件にする」が未実装だった。

非同期化で一度再発したため、最終的に Artwork モデル側の `model_serializer` で解決している（Route への付け忘れでも壊れない形）。

### `pending` で `stage` を持ってしまう問題

Schema 上 `pending` は `stage` を持てないが、実装が `pending` / `processing` を同じモデルで扱っていた。ローカルの Inline 実行では一瞬で `processing` まで進むため気づけないが、**Cloud Tasks 経路では 202 直後に `pending` のまま GET される時間帯が確実にある**ため、本番だけで踏むものだった。

### Deploy 手順の不整合

Secret 名が §3.2 と §6.7 で食い違っており（`GEMINI_API_KEY` / `gemini-api-key`）、そのままでは Deploy が通らない状態だった。`docs/deploy.md` の統合時にあわせて修正済み。

---

## 5. 決まっていないこと

### Asset 用 GCS（Bucket 名 / URL 方式 / 保持期間）

`GcsAssetStore` はコード実装済みだが未有効化。現状は `ASSET_BACKEND=local` のまま。

**AGENTS.md 上、単独で FIX しない範囲**なので、以下を決めてから有効化したい。

- Bucket 名
- 公開 URL か署名付き URL か
- 保持期間（初期案 2 週間）

署名付きにすると、Artwork Data に埋めた URL が期限切れで 404 になる可能性がある（後から STL 生成する場合など）。公開バケットにする場合は、推測できないオブジェクト名にする必要がある。

> 注：`JOB_INPUT_BUCKET` / `JOB_INPUT_BACKEND=gcs` は **Job 入力写真の一時置き場**であって、Asset 配信の GCS 化とは別。前者は作成済み。

### stage の粒度

契約上は 4 段階（`analyzing` / `extracting` / `composing` / `finalizing`）だが、**実装は現状 `analyzing` → `finalizing` の 2 段階のみ**。`extracting` / `composing` の遷移を拾う仕組みが AI 側に無いため。

実測では **`extracting` が 200 秒（全体の 85%）** を占めるので、2 段階だと 3 分半ずっと同じ表示になる。ローディング画面の体験に直結する。

`GenerationObserver` の `segmentation_attempt` は候補ごとに呼ばれるので、`analyzing` → `extracting` の切り替えは AI 側を触らずに取れる可能性がある。`composing` は 7 秒しかないので、無理に出さなくてもよさそう。

Frontend は 4 段階すべてに対応済みなので、**後から増えても契約変更なしで動く**。

### Real AI 実行時の公開設定

Real AI を動かすときは Gemini 課金を守るため `--no-allow-unauthenticated` で公開を閉じる運用にしている。

ただし**閉じるとブラウザの Frontend からは呼べない**（ID トークンを付けられないため）。Cloud Tasks は invoker SA を持つので影響しない。

E2E 確認のたびに一時的に開ける必要があり、その都度もりかんさんへ IAM をお願いすることになる。**デモ当日は審査員が URL から操作する前提なので、開けた状態で Real AI を動かすことになる。** 課金をどう抑えるかは別途決めたい。

### Concurrency の設定

非同期化により、Worker（約 4 分占有）とポーリングの GET（2 秒おきに 120 回程度）が同時に走る。`concurrency=1` のままでは Worker が占有している間ポーリングが処理できないため、**`concurrency=4` へ上げる判断をした**（`max-instances=1` は維持）。

`max-instances` を上げると `LocalDirAssetStore` が破綻する（書き込みと配信でインスタンスが分かれる）ため、Asset の GCS 化が必須条件になる。まず concurrency を上げる形で動かし、メモリが不足するようなら再検討する。

---

## 6. 直近の担当

| 誰 | 何 |
|---|---|
| もりかんさん | 上記 IAM 5 件（Owner 権限が必要） |
| 橋内 | IAM 後の Deploy → 非同期 E2E 確認 → プレゼン動画 |
| クメ先生 | AI 品質・速度改善、stage 粒度の判断 |
| まなみんさん | Frontend E2E、レスポンシブ、Design 反映 |
| がっぽさん | ローディング画面、発表資料デザイン |
| ナンちゃんさん | 実 Artwork Data からの STL 生成・実印刷 |

---

## 7. 参照

- Deploy 手順一式：`docs/deploy.md` §3.1（事前準備）→ §6.3–6.6（Provisioning）→ §3.5（Build / Deploy）→ §6.8（確認）
- どの手順が Owner 権限を必要とするかは §3.5 冒頭の実行順マップに記載
- 非同期 Job の契約：`contracts/job-status-response.schema.json` / `contracts/generate-accepted-response.schema.json`
- 動作確認用 Mock：`contracts/mock/job-status-{processing,completed,failed}.json`
