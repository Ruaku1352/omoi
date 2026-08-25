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
  `PORT` は環境変数から受け取り、`8000` に固定していない。最終`default` targetは
  Model Artifactを含まないMock用、`real-ai` targetだけがEfficientSAM ONNXを含む
- `.dockerignore` — `frontend/`、ローカル生成物、Secret類を除外

ビルド確認（ローカルDockerがあれば）:

```bash
# Mock: Model Artifactを含まないdefault target。リポジトリルートで実行すること。
docker build --target default -t omoi-backend-mock .

docker run --rm -p 8080:8080 \
  -e MOCK_AI=true \
  -e CORS_ORIGINS=http://localhost:5173 \
  omoi-backend-mock

curl -F photos=@contracts/assets/source-p1.jpg -F memoryText=海に行った日 \
  http://127.0.0.1:8080/api/v1/artworks/generate

# Real AI: 事前取得・checksum検証済みのONNX artifactを含むreal-ai target。
uv --directory backend run python ../scripts/fetch_efficientsam_onnx.py \
  --sha256 143c3198a7b2a15f23c21cdb723432fb3fbcdbabbdad3483cf3babd8b95c1397
docker build --target real-ai -t omoi-backend-real .
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

### 3.2 Real AIのSecret要件

Real AI Runtimeは `GEMINI_API_KEY` 環境変数を必要とする。Secret値はRepository・Docker Build
Context・資料へ置かない。どのSecret resource / Versionをbindするか、どのRuntime Service
AccountへAccessorを付与するかは、Backend/GCP担当の運用判断とする。

### 3.3 共通の環境変数ルール

> ### ⚠ 環境変数は毎回すべてまとめて渡す
>
> **`--set-env-vars` は「追加」ではなく「置き換え」。**
> 指定しなかった環境変数は**消える**。
> さらに `--set-env-vars` を**1コマンド内に2回以上書くと、後の指定が前を上書きする**
> （gcloudのフラグは繰り返しても連結されない）。どちらの経路でも結果は同じで、
> **渡し漏れた変数が黙って消える。**
>
> **実際に起きた事故**: Asset URLのscheme修正でDeployした際、`CORS_ORIGINS` を
> 渡さなかったため設定が消え、Frontendから CORS で弾かれた。
> Backendは正常に起動し `/health` も `200` を返すので、**ブラウザで叩くまで気づけない。**
>
> **各Deploy経路で必要な変数は、1つの `--set-env-vars` へ全部まとめて渡すこと。**
> Real AIでは `MOCK_AI` / `APP_ENV` / `CORS_ORIGINS` / `GEMINI_MODEL`、Mockでは
> `MOCK_AI` / `APP_ENV` / `CORS_ORIGINS` を1回の指定にする。1つだけ変えたいときも、
> その経路で必要な他の変数を省略しない。

`--set-env-vars` は**1回だけ**。分割しない。

- `PORT` は**指定しない**。Cloud Runが予約している環境変数で、`--set-env-vars` に含めるとエラーになる
- `CONTRACTS_DIR` は**指定しない**。Dockerfileがローカル開発と同じ相対配置を保っているので既定値のままで解決する

#### `^|^` 記法【CORS_ORIGINS では必須】

`gcloud` は `--set-env-vars` の値を**カンマで環境変数の区切りとして解釈する**。
`CORS_ORIGINS` は許可Originをカンマ区切りで並べるため、素直に書くと壊れる。

```bash
# ✗ 壊れる。gcloud が CORS_ORIGINS / http://localhost:5174 / https://... の
#   3つの環境変数だと解釈し、CORS_ORIGINS には最初の1つしか入らない
--set-env-vars="CORS_ORIGINS=http://localhost:5173,http://localhost:5174,https://omoi-manami-test-77989.web.app"
```

先頭に `^区切り文字^` を付けると、**環境変数どうしの区切り文字**を変更できる。
`^|^` なら区切りが `|` になり、値の中のカンマはそのまま渡る。

```bash
# ✓ 正しい。変数の区切りは | 、CORS_ORIGINS の中の , は値として渡る
--set-env-vars="^|^APP_ENV=deployed|CORS_ORIGINS=http://localhost:5173,http://localhost:5174"
```

Originは **scheme + host + port** のみ。末尾スラッシュを付けない。
Portが違えば別Originなので `localhost:5173` と `localhost:5174` は**両方**書く。
本番ではFirebase HostingのOriginへ限定する（AGENTS.md §2.1）。

### 3.4 Mock Deploy（Model Artifactなし）

`--source .` はDockerfileがある場合にDockerfileの**最終stage**をBuildする。最終stageは
Model ArtifactをCOPYしない`default` targetなので、Mock専用の軽量Imageとして使う。
`MOCK_AI=true` ではGemini KeyもONNX artifactも不要である。

```bash
cd /path/to/omoi   # backend/ ではなくリポジトリルート

gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --set-env-vars="^|^APP_ENV=deployed|MOCK_AI=true|CORS_ORIGINS=http://localhost:5173,http://localhost:5174,https://omoi-manami-test-77989.web.app"
```

**その場合も `CORS_ORIGINS` は省略しない。**

### 3.5 Real AIのRuntime / Packaging要件

`gcloud run deploy --source .` の通常経路はDockerfile最終の`default` targetを使うため、
Model Artifactを含むReal AI ImageのDeploy手順としては使わない。Real AIでは、
`backend/.models/efficientsam_ti.onnx` を含む`real-ai` targetを明示的にBuildする必要がある。

`real-ai` targetはONNX artifactを`/srv/models/efficientsam_ti.onnx`へCOPYし、
`EFFICIENTSAM_MODEL_PATH` を設定する。Runtime中のModel Downloadは禁止し、PyTorchを
Runtime必須依存にしない。`GEMINI_MODEL` はSemantic Planning / Composition用の環境変数で、
具体Model IDは未FIX。`GEMINI_SEGMENTATION_MODEL` は設定しない。

targetを選択するBuild方式、Container Registry、Cloud RunへのDeploy、Secret resource / Version、
Runtime Service Account / IAMはBackend/GCP担当が決定する。AI側は上記Runtime / Packaging条件を
満たすことだけを要求する。

同期Real AI E2Eは数分規模である。Cloud Run実測では十分なtimeoutを設定する必要があり、
**600 secは初回測定候補であってFIX値ではない**。CPU・Memory・Concurrency・Minimum instancesの
初回測定条件は`docs/ai/09_CLOUD_RUN_CONSTRAINTS.md`を正本とする。

### 3.6 確認

```bash
export SERVICE_URL=$(gcloud run services describe "$SERVICE" \
  --region "$REGION" --format='value(status.url)')

curl "$SERVICE_URL/health"

curl -F photos=@contracts/assets/source-p1.jpg -F memoryText=海に行った日 \
  "$SERVICE_URL/api/v1/artworks/generate"
```

`MOCK_AI=true` でDeployした場合は生成成功Responseが返るはず。
`MOCK_AI=false` では、Geminiの認証・`GEMINI_MODEL`・EfficientSAM ONNX artifactが揃った
Real AI経路を使う。設定またはProvider処理が失敗した場合はMockへ切り替えず、対応する
API Errorを返す。
（黙ってMockへ落ちない設計どおり。AGENTS.md §9）。

**上の2つはCORSを検証しない。** `CORS_ORIGINS` の渡し漏れは `curl` では絶対に見つからない
（Server側は `200` を返し、足りないのはResponse Headerだけ）。**必ず別途確認する。**

```bash
curl -s -D - -o /dev/null -X OPTIONS "$SERVICE_URL/api/v1/artworks/generate" \
  -H "Origin: http://localhost:5174" \
  -H "Access-Control-Request-Method: POST" | grep -i access-control
```

`access-control-allow-origin: http://localhost:5174` が返れば通っている。
**何も出なければ `CORS_ORIGINS` が渡っていない**ので、実行したDeployのコマンドを
（全変数をまとめたまま）再実行する。確認したいOriginごとに `-H "Origin: ..."` を替えて叩く。

### 3.7 再Deploy

Mockは3.4を再実行する。Real AIのBuild / Registry / Deploy方式はBackend/GCP担当が決定し、
3.5のRuntime / Packaging要件を満たすことを確認する。

**環境変数を1つだけ変えたいときも、各Deployコマンドから変数を削らないこと。**
必要な変数だけを書いた短縮版を作ると、書かなかった変数が消える（3.3の警告）。
変えたい値だけ書き換えて、コマンド全体を実行する。

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

### Asset URLのScheme【対応済み】

`LocalDirAssetStore.publish()` はURLの組み立てに `request_base_url`（＝Requestの`base_url`）を
使っている。Cloud RunはTLSをGoogle側のFrontendで終端し、Container自体へはHTTPで転送するため、
補正しないと生成されるAsset URLが `http://` のまま返っていた。

実機Deployで実際に踏んだ: `curl` では `http://` URLが302で `https://` へRedirectされ配信は
できていたが、**Browserのmixed Content判定はRedirect前のURL Schemeだけを見てBlockする**ため、
HTTPSのFirebase HostingからFrontendが呼ぶと画像が一切表示されない不具合になっていた。

対応: `app/api/v1/artworks.py` の `_public_base_url()` が、`APP_ENV=deployed` のときだけ
`request.base_url` のschemeを `https://` へ補正する（ローカル開発 `APP_ENV=local` 既定値では
何もしない）。Cloud Runの公開Endpointは常にHTTPSでしか外部到達できない
（`http://`は自動でRedirectされる）という事実に乗っているだけなので、
`X-Forwarded-Proto` を信頼する方式（`--proxy-headers`）より単純で、Header偽装等を
気にしなくてよい。`ASSET_PUBLIC_BASE_URL` を明示的に設定した場合はそちらが優先されるので、
将来カスタムドメインを使う等の理由で必要になったときの逃げ道は残っている。

この修正に伴い、`generate_artwork` Endpointが読む `Settings` の取得経路を
`Depends(get_settings)`（Process全体でキャッシュされた、実環境変数を読むだけの関数）から
`Depends(get_settings_dep)`（`request.app.state.settings` を返す）へ揃えた。
`app.state.generator` / `app.state.asset_store` は元々 `create_app()` に渡された
Settingsから作られていたのに、Endpoint内の `settings` だけ別経路を見ていて、
テストでSettingsを差し替えても反映されない食い違いがあったため。

`tests/test_generate_endpoint.py::test_asset_url_scheme_is_https_when_deployed` で
`APP_ENV=deployed` 時にAsset ManifestのURLが `https://` になることを確認している。

---

## 5. 単独でFIXしていないこと（このDocumentの範囲外）

- 同期 / 非同期方式（現状は同期のまま）
- Asset Binary Storage方式（現状はLocal Directoryのまま、上記4節参照）
- Queue / Job Runnerの導入
- 追加Endpoint
- Bundle生成主体

`skills/backend/SKILL.md` の通り、これらは公開チャンネルで共有してから進める。
