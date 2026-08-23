# Backend の Cloud Run Deploy

対象は `backend/`（Cloud Run Deploy Unit）のみ。Frontend（Firebase Hosting）はこの文書の範囲外。

前提: `AGENTS.md` §2.1 / §10、`skills/backend/SKILL.md`、`skills/integration/SKILL.md`。

**このDocumentはDeploy手順の準備であり、実際のDeployは行っていない。**
`gcloud` コマンドはこのDocumentを書いた環境からは実行・検証していないので、
実行前に一度 `--dry-run` 相当の確認（`gcloud run deploy --help` のオプション確認等）を推奨する。

---

## 1. contracts/ の扱い【本題・方針決定】

### 何が問題か

`backend/` は `contracts/`（Deploy Unitを跨ぐ共通Contract。AGENTS.md §2.2）を実行時に読む。

- `app/config.py` の `CONTRACTS_DIR` 既定値は `backend/` の**親ディレクトリ** `/contracts`
- `MOCK_AI=true` のとき `contracts/mock/artwork.json` と `contracts/assets/*` を実際に読んで返す
- Real AI実装後も `scripts/validate_contracts.py` 等がSchemaを参照する前提は変わらない

`contracts/` は `backend/` より上の階層にあるため、`cd backend && gcloud run deploy --source .`
のように **`backend/` をBuild Contextにすると `contracts/` がコンテナに含まれない**。
これが実際に詰まっていた原因。

### 選択肢

**案A: Dockerfile をリポジトリルートに置き、ルートからBuildする（採用）**

`docker build` / `gcloud run deploy --source .` の実行位置をリポジトリルートにし、
`backend/` と `contracts/` を**そのままの兄弟関係**でイメージへコピーする。

- Pros
  - `contracts/` を複製しない。**Deploy Unitを跨ぐ共通Contractという位置づけ（AGENTS.md §2.2）を
    崩さない** — コピーではなく「ビルド時に単一の正本をイメージへ積む」だけ
  - ローカル開発（`cd backend && uv run uvicorn ...`）と**同じ相対配置**をイメージ内でも保てるので、
    `app/config.py` の `CONTRACTS_DIR` 既定値をそのまま使える。環境ごとの分岐コードが要らない
  - `contracts/` の更新が自動的に次回Buildへ反映される（同期漏れが起きない）
- Cons
  - Build Contextにリポジトリ全体が入る（`.dockerignore` で `frontend/` 等は除外済み。実害は小さい）
  - `gcloud run deploy` をリポジトリルートから実行する運用に統一する必要がある
    （`backend/` に入ったまま実行する癖がある人は要注意）

**案B: `contracts/` を `backend/` 配下へコピーしてから Build する**

デプロイ前スクリプトで `cp -r contracts backend/contracts` してから `cd backend && gcloud run deploy --source .`。

- Pros: 既存の「`cd backend`」運用のままいける
- Cons
  - **共通Contractの複製ができてしまう。** コピー元(`contracts/`)とコピー先(`backend/contracts/`)が
    Gitの追跡上ズレたり、コピーし忘れたまま古い状態でDeployするリスクが常にある
  - AGENTS.md §2.2 が言う「Deploy Unitを跨ぐ共通Contract」という位置づけと矛盾する
    （`backend/` 専有物に見えてしまう）
  - コピー処理自体をどこかに実装・保守する必要がある（`.gitignore`にも追加が要る）

**案C: 実行時に `contracts/` を読まない（Schema/Mockをbackendパッケージへ組み込む）**

Build時に `contracts/` の中身をPythonパッケージのリソースとして焼き込み、実行時は
外部ディレクトリを見ない形にする。

- Pros: 実行時の相対パス問題が原理的に無くなる。将来的にBackendを単独Artifactとして
  配布する場合には筋が良い
- Cons
  - Schemaだけでなく `contracts/mock/` のJSONと `contracts/assets/` のBinary（PNG/JPEG）も
    含めて「組み込みリソース化」する仕組みが要り、変更の影響範囲が大きい
  - 「`contracts/`を正本として読む」という今の設計から外れるので、Backend単体の判断で
    決めていい範囲を超える（契約の扱い方そのものの変更）
  - P0でここまでやる必要性が今のところ無い

### 推奨

**案A**。理由は上記の通りで、複製によるドリフトを避けられる・既存コードを変更しなくて済む・
契約の所在（Deploy Unitを跨ぐ共通物）という設計意図を壊さない、の3点が揃っている。

このDocumentのDockerfile・手順は案Aで書いている。

---

## 2. Dockerfile / .dockerignore

リポジトリルートに配置（上記の方針決定に基づく）。

- `Dockerfile` — `python:3.13-slim` ベース、`uv` で `uv.lock` から再現Install。
  `PORT` は環境変数から受け取り、`8000` に固定していない
- `.dockerignore` — `frontend/`、ローカル生成物、Secret類を除外

ビルド確認（ローカルDockerがあれば）:

```bash
# リポジトリルートで実行すること。backend/へcdしない。
docker build -t omoi-backend .

docker run --rm -p 8080:8080 \
  -e MOCK_AI=true \
  -e CORS_ORIGINS=http://localhost:5173 \
  omoi-backend

curl -F photos=@contracts/assets/source-p1.jpg -F memoryText=海に行った日 \
  http://127.0.0.1:8080/api/v1/artworks/generate
```

---

## 3. Cloud Run へのDeploy手順

**リージョン**: `asia-northeast1` / **サービス名**: `omoi-backend`

以下はCloud Shell（またはgcloud CLIがセットアップ済みのローカル環境）から、
**リポジトリルートで**実行する前提のコマンド。`PROJECT_ID` は各自の値に置き換える。

### 3.1 事前準備（初回のみ）

```bash
export PROJECT_ID=<your-gcp-project-id>
export REGION=asia-northeast1
export SERVICE=omoi-backend

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  secretmanager.googleapis.com
```

### 3.2 Gemini API Key を Secret Manager へ登録する

**Secret値をコマンド履歴やファイルへ直接書かない。** 対話的に入力する。

```bash
# プロンプトが出たらAPI Keyを貼り付けてEnter → その後Ctrl+D
gcloud secrets create gemini-api-key --replication-policy="automatic"
gcloud secrets versions add gemini-api-key --data-file=-
```

初回のみ、Cloud RunのRuntime Service AccountにSecretへのアクセス権を渡す:

```bash
export PROJECT_NUMBER=$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')

gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:${PROJECT_NUMBER}-compute@developer.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"
```

### 3.3 Deploy する（リポジトリルートで実行）

```bash
cd /path/to/omoi   # backend/ ではなくリポジトリルート

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars="APP_ENV=deployed,MOCK_AI=false,CORS_ORIGINS=https://<frontendのFirebase Hosting Origin>" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:latest" \
  --set-env-vars="GEMINI_MODEL=gemini-3.7-flash,GEMINI_SEGMENTATION_MODEL=gemini-2.5-flash"
```

- `--source .` が `Dockerfile` をリポジトリルートで検出してBuildする（Buildpacksへは落ちない）
- `PORT` は**指定しない**。Cloud Runが予約している環境変数で、`--set-env-vars` に含めるとエラーになる
- `CONTRACTS_DIR` は**指定しない**。Dockerfileがローカル開発と同じ相対配置を保っているので既定値のままで解決する
- `CORS_ORIGINS` は本番ではFirebase HostingのOriginへ限定する（AGENTS.md §2.1）
- Mock AIで先にデプロイ疎通だけ確認したい場合は `MOCK_AI=true` にして、
  `GEMINI_*` 系の `--set-secrets` / `--set-env-vars` は省略してよい

`--set-env-vars` を2回に分けているのは読みやすさのためで、実際は1回の呼び出しへ
まとめてよい（カンマ区切りで1つの `--set-env-vars` に連結する）。

### 3.4 確認

```bash
export SERVICE_URL=$(gcloud run services describe "$SERVICE" \
  --region "$REGION" --format='value(status.url)')

curl "$SERVICE_URL/health"

curl -F photos=@contracts/assets/source-p1.jpg -F memoryText=海に行った日 \
  "$SERVICE_URL/api/v1/artworks/generate"
```

`MOCK_AI=true` でDeployした場合は生成成功Responseが返るはず。
`MOCK_AI=false` かつ `ai/gemini.py` が未実装のままの場合は `AI_FAILED` が返るのが正しい
（黙ってMockへ落ちない設計どおり。AGENTS.md §9）。

### 3.5 再Deploy

コード変更後は3.3のコマンドを再実行するだけでよい（Dockerイメージが再Buildされ、
新Revisionへ切り替わる）。

---

## 4. AssetStore（Local Directory実装）が Cloud Run で成立するかの検証

### 結論

**現状の `LocalDirAssetStore` のままでは、Cloud Runの通常運用（複数Instance・Auto Scaling・
Scale to Zero）と相性が悪い。** `backend/app/services/asset_store.py` のdocstringが
自己申告している通り「開発用の繋ぎ」であり、想定通りの制約に踏み込むと壊れる。

### 具体的に何が起きるか

1. **Instance間でファイルシステムが共有されない**
   `POST /generate` を処理したInstance AのLocalDiskへPNGを書き込んでも、直後に
   ブラウザが叩く `GET /dev/assets/...` が別のInstance Bへ振られると `404` になる。
   Cloud Runは複数Instanceが起動している状態でのSession Affinityを保証しない
   （Best-effort機能はあるが保証ではない）
2. **Scale to Zero / Instance Recycleでデータが消える**
   Instanceがアイドルで畳まれる、あるいは新Revisionへ切り替わると、Local Diskの中身は
   跡形もなく消える。数分前に発行したAsset URLが後から `404` になり得る
3. **`--min-instances=1` `--max-instances=1` にしても解決しない**
   1Instanceに固定すればInstance間のズレは防げるが、Scale to Zeroを止めるだけで
   Recycle（新Revisionへの切り替え、あるいはCloud Run側の都合による再起動）自体は防げない。
   加えてAuto Scalingの利点を完全に捨てることになり、同時アクセスが増えたときの
   耐性が無い

### 対処案（実装はまだしない）

- **本筋**: `AssetStore` Protocolの別実装として `GcsAssetStore`（Google Cloud Storageへ書き込み、
  署名付きURLか公開URLを返す）を追加する。`app/services/asset_store.py` のコメントが
  最初からこれを想定した設計（Protocolで抽象化し、Manifestの形は変えない）になっているので、
  差し替え自体の実装コストは大きくない
  - ただし「Asset Binary Storage方式」はAGENTS.md上**単独でFIXしない**範囲に明記されている。
    GCSを使うこと自体、Bucket名・公開/署名付きURLどちらにするか・保持期間は
    チーム確認してから実装する
- **デモ限定の暫定策**: `--min-instances=1 --max-instances=1` にして、かつDeployし直さない
  短時間の検証・デモ用途だけに使う、と明示して割り切る。本番運用や複数人での並行アクセスには使わない
- **恒久策にしないことの明記**: Local Filesystemを、複数Request・複数Instanceをまたぐ
  Assetの正本として扱わない（技術設計§22.5）。`--min/max-instances=1` はこの前提を
  一時的に回避しているだけであり、Local Directory実装そのものをそのまま本番の
  Asset正本として運用し続けることは想定しない。恒久策は上記のGCS移行（またはそれに準ずる
  外部Storage）であり、方式決定・実装は別タスクとして扱う

### 副次的に見つかった論点: Asset URLのScheme

`LocalDirAssetStore.publish()` はURLの組み立てに `request_base_url`（＝Requestの`base_url`）を
使っている。Cloud RunはTLSをGoogle側のFrontendで終端し、Container自体へはHTTPで転送するため、
`ASSET_PUBLIC_BASE_URL` を明示的に設定しない場合、生成されるAsset URLが `http://` のまま
返る可能性がある（FrontendがHTTPSの場合、Mixed Contentでブラウザにブロックされ得る）。

回避策は2つ:

1. `ASSET_PUBLIC_BASE_URL` にCloud RunのService URL（`https://...`）を明示的に設定する
   （設定1つで済むのでこちらを推奨）
2. `uvicorn` 起動時に `--proxy-headers --forwarded-allow-ips=*` を付けて `X-Forwarded-Proto` を
   信頼させ、`request.base_url` 自体が `https` を返すようにする

いずれもAsset Binary Storage方式そのものの決定ではないので、GCS移行を待たずに
Local Directory実装のままでも直せる。ただし数値・設定値としてどちらを採るかは
実際にDeployして挙動を見てから決める（【PoC後FIX】寄りの話なので、ここでは選ばない）。

---

## 5. 単独でFIXしていないこと（このDocumentの範囲外）

- 同期 / 非同期方式（現状は同期のまま）
- Asset Binary Storage方式（現状はLocal Directoryのまま、上記4節参照）
- Queue / Job Runnerの導入
- 追加Endpoint
- Bundle生成主体

`skills/backend/SKILL.md` の通り、これらは公開チャンネルで共有してから進める。
