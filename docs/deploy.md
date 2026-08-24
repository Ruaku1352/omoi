# Deploy

Backend（Cloud Run）と Frontend（Firebase Hosting）のDeploy手順。
Runtime / Deploy構成は【仮決定】（AGENTS.md §2.1）。実Deploy検証後に最終FIXする。

> **【要記入】** Project ID / Service名 / Region、および Container Image のBuild方法は
> Repositoryから判別できないため、実際にDeployした担当（もりかん）が埋めること。
> 本ファイル作成時点で `Dockerfile` / `Procfile` / CI設定はRepositoryに存在しない。
> 以下のコマンド例は `<...>` を実値へ置き換えて使う。

---

## Backend / Cloud Run

### 環境変数

| Key | 必須 | 説明 |
|---|---|---|
| `CORS_ORIGINS` | **必須** | 許可するFrontend Origin。カンマ区切り。**未設定だとブラウザから一切呼べない** |
| `MOCK_AI` | 任意 | `true` で実Geminiを呼ばず共通Mockを返す。明示Modeであり隠れFallbackではない |
| `GEMINI_API_KEY` | Real AI時必須 | Secret。**Repositoryへ絶対にCommitしない** |
| `GEMINI_MODEL` | Real AI時必須 | 意味理解・選定・構成用【PoC後FIX】 |
| `GEMINI_SEGMENTATION_MODEL` | Real AI時必須 | Segmentation用【PoC後FIX】 |
| `APP_ENV` | 任意 | `local` / `deployed` |
| `LOG_LEVEL` | 任意 | 既定 `INFO`。起動時のCORS診断ログはINFO以上で出る |
| `CONTRACTS_DIR` | 任意 | `MOCK_AI=true` で共通Mockを読む場所。Imageへの同梱先が変わる場合のみ |
| `MAX_PHOTOS` / `MAX_PHOTO_BYTES` / `MAX_TOTAL_UPLOAD_BYTES` | 任意 | Upload制限【PoC後FIX】 |
| `ASSET_DIR` / `ASSET_MOUNT_PATH` / `ASSET_PUBLIC_BASE_URL` | 任意 | Asset公開の暫定設定。Storage方式は【未決定】 |

Key名の共有は Repository Root の `.env.example`。**`.env` はCommitしない**（AGENTS.md §10）。

### Deployコマンド

```bash
gcloud run deploy <SERVICE_NAME> \
  --project <PROJECT_ID> \
  --region <REGION> \
  --source backend \
  --allow-unauthenticated \
  --update-env-vars "^|^CORS_ORIGINS=http://localhost:5173,http://localhost:5174,https://omoi-manami-test-77989.web.app|MOCK_AI=true"
```

Gemini API Key は環境変数へ直接書かず Secret Manager 経由にする。

```bash
gcloud run services update <SERVICE_NAME> \
  --project <PROJECT_ID> --region <REGION> \
  --set-secrets "GEMINI_API_KEY=<SECRET_NAME>:latest"
```

### `^|^` 記法が必要な理由【重要】

`gcloud` の `--set-env-vars` / `--update-env-vars` は、**値の中のカンマも環境変数の区切りと解釈する**。
`CORS_ORIGINS` はカンマ区切りなので、素直に書くと壊れる。

```bash
# ✗ 壊れる。gcloud が「3つの環境変数」と解釈する
--update-env-vars "CORS_ORIGINS=http://localhost:5173,http://localhost:5174,https://omoi-manami-test-77989.web.app"
```

先頭に `^区切り文字^` を付けると、**環境変数どうしの区切り文字**を変更できる。
`^|^` なら区切りが `|` になり、値の中のカンマは安全になる。

```bash
# ✓ 正しい。変数の区切りは | 、値の中の , はそのまま渡る
--update-env-vars "^|^CORS_ORIGINS=http://a,http://b|MOCK_AI=true"
```

### `--set-env-vars` と `--update-env-vars` の違い【重要】

- `--set-env-vars` … **既存の環境変数を全部消してから**指定分だけ設定する
- `--update-env-vars` … 指定分だけ追加・上書きする

`CORS_ORIGINS` を足すつもりで `--set-env-vars` を使うと、
**`GEMINI_API_KEY` や `MOCK_AI` が消える**。追加・変更時は `--update-env-vars` を使う。

---

## CORS のハマりどころ

**CORSの失敗はサーバー側から見えない。** 許可Originが一致しなくてもHTTPは `200` で返り、
足りないのは `Access-Control-Allow-Origin` ヘッダーだけ。
そのため **`curl` や Health Check では成功して見え、ブラウザだけが失敗する。**

| 書き方 | 結果 |
|---|---|
| `https://example.web.app` | ✓ |
| `https://example.web.app/` | ✓ 末尾スラッシュはBackend側で除去する |
| ` https://example.web.app ` | ✓ 前後の空白は除去する |
| `HTTPS://Example.Web.App` | ✓ 小文字化する |
| `"https://a,https://b"` | ✗ クォートが値に入る。起動ログに警告が出る |
| `example.web.app` | ✗ scheme必須。起動ログに警告が出る |
| `https://example.web.app/api` | ✗ Origin にPathは含めない。起動ログに警告が出る |
| 未設定 | ✗ ブラウザから一切呼べない。起動ログに警告が出る |

Origin は **scheme + host + port** のみ。Port が違えば別Originなので、
`localhost:5173` と `localhost:5174` は**両方**列挙する必要がある。

---

## Deploy後の確認

ブラウザを開かなくても、Health Check で**実際に効いている許可Origin**を確認できる。

```bash
curl -s https://<SERVICE_URL>/health
```

```json
{
  "status": "ok",
  "mockAi": true,
  "corsOrigins": ["http://localhost:5173", "http://localhost:5174", "https://omoi-manami-test-77989.web.app"],
  "corsOriginsInvalid": []
}
```

- `corsOrigins` が **空** → `CORS_ORIGINS` が渡っていない
- `corsOrigins` に**想定より少ない数**しか無い → `^|^` を付け忘れてカンマで分断された
- `corsOriginsInvalid` に値がある → クォート混入・scheme欠落・Pathつき

起動ログにも同じ内容が出る。

```
INFO app.main CORS許可Origin (3件): http://localhost:5173, http://localhost:5174, https://...
```

---

## Frontend / Firebase Hosting

```bash
cd frontend
npm ci
npm run build          # dist/ を生成
firebase deploy --only hosting --project <FIREBASE_PROJECT_ID>
```

Backendの接続先は Build時に埋め込まれる。`.env` の `VITE_API_BASE_URL` に
Cloud Run の Service URL を設定してから `npm run build` する。

**Frontend を新しいOriginへ公開したら、そのOriginを `CORS_ORIGINS` へ足して Backend を再Deployする。**
Preview Channel（`*.web.app` の別ホスト名）も別Originなので、使う場合は追加が必要。

---

## 参照

- 環境変数のKey名: Repository Root の `.env.example`
- Backendの構成: `backend/README.md`
- Mock / Real の切り替えとE2E確認: `skills/integration/SKILL.md`
