# backend — Cloud Run Deploy Unit

Python 3.13系 + FastAPI 0.139系 + Pydantic【仮決定】。
依存は `pyproject.toml` + `uv.lock` で再現可能にする（requirements の手書き分散管理をしない）。

AI・画像処理は `ai/` 配下の内部Module。独立Serviceにしない。

実装前提は `/AGENTS.md` §4・§5・§6 と `/skills/backend/SKILL.md`。

## セットアップ

```bash
uv sync --all-groups
cp ../.env.example .env        # .env はCommitしない
uv run uvicorn app.main:app --reload
```

```bash
uv run pytest        # 契約テスト
uv run ruff check .  # Lint
uv run ruff format . # Format
```

`MOCK_AI=true` にすると実Geminiを呼ばず、共通Mock（`../contracts/mock/artwork.json` +
`../contracts/assets/`）を **Real生成と同じ形式**で返す。
返る形は `../contracts/mock/generate-success-response.json` と同じ
（`url` だけRuntime依存なので環境ごとに変わる）。

```bash
MOCK_AI=true CORS_ORIGINS=http://localhost:5173 uv run uvicorn app.main:app --reload
curl -F photos=@../contracts/assets/source-p1.jpg -F memoryText=海に行った日 \
  http://127.0.0.1:8000/api/v1/artworks/generate
```

## API

`POST /api/v1/artworks/generate`

- Request: `multipart/form-data` — `photos`（複数・可変長）/ `memoryText`（任意）
- Response: `202 + {"jobId": "..."}`
- `GET /api/v1/jobs/{jobId}` でPollingし、完了時に `{"artwork": ..., "assetManifest": ...}` を受け取る
  - Schema正本: `/contracts/generate-success-response.schema.json`【FIX】（技術設計 §14.2）
    （`artwork.schema.json` と `asset-manifest.schema.json` を `$ref` するだけの層）
  - 外側のKeyは `artwork` / `assetManifest`。**P0では `data` 等の追加Envelopeを設けない**
- Error: `/AGENTS.md` §4 の形式

`POST /api/v1/physical-output/exports`

- Request: `multipart/form-data`
  - `artwork`: 確定Artwork Data JSON
  - `assets`: 現在の `layers[]` が参照するLayer Asset画像。元写真や差し替え候補Assetは任意
  - `outputFormat`: `stlZip` / `photoPdf` / `photoJpegZip`。未指定時は `stlZip`
  - `physicalOutputConfig`: 任意JSON。未指定ならBackend側のPoC既定値（rail / 2L Landscape / 4行 x 3穴）
- Response:
  - `outputFormat=stlZip`: `application/zip`
    - `stl/`: 平面パーツSTL + 番号付きスロット土台STL
    - `physical-output-config.json`: 製造条件
    - `flat-photo-parts-report.json`: 寸法・警告・組み立て情報
  - `outputFormat=photoPdf`: `application/pdf`
    - 2L Landscape（178 x 127mm）写真紙100%印刷用の `flat-photo-print-layout.pdf`
    - 全面不透明の `layerIndex: 0` 背景は既定で2L全面へcover cropする
  - `outputFormat=photoJpegZip`: `application/zip`
    - `photo/`: コンビニ2L写真プリント用のJPEG一式
    - 既定は2L Landscape 300dpi（2102 x 1500px）。PDFが普通紙文書扱いになる環境ではこちらを使う

このEndpointは2026-09-02時点のPhysical Output PoC候補。入力境界はDrive仕様どおり
確定Artwork Data + Assetsで、Artwork Dataへmm値を混ぜない。複数成果物を返すため
STL側ResponseはZIPだが、入力をPortable Artwork Bundle ZIPへ固定しない。SVGはユーザー向け
主要Downloadにはせず、必要なら開発確認・手修正用の生成物として扱う。
Layer PNGは生成入力写真とは別制限で検証する。`MAX_PHYSICAL_ASSET_BYTES` と
`MAX_PHYSICAL_TOTAL_ASSET_BYTES` を使い、Bundle内に元写真が混ざっていても
現在の `layers[]` が参照するAssetだけをSTL/PDF生成対象にする。

`GET /health` は担当裁量のHealth Check。OpenAPIには載せず、Product API Contractに含めない。

## 構成

```
backend/
├─ app/
│  ├─ main.py               # FastAPI組み立て、CORS、Router、静的配信
│  ├─ config.py             # 環境変数（【PoC後FIX】の値もここへ集約）
│  ├─ errors.py             # AGENTS.md §4 の Error形式と例外Handler
│  ├─ api/v1/artworks.py    # POST /api/v1/artworks/generate
│  ├─ api/v1/physical_output.py
│  │                        # POST /api/v1/physical-output/exports
│  ├─ models/               # contracts/ Schema の写像（Pydantic）
│  │                        #   api.py = GenerateSuccessResponse
│  └─ services/
│     ├─ validation.py      # Schemaで表現できない規則の検証
│     ├─ asset_store.py     # Asset Binary → URL（方式は【未決定】）
│     ├─ generator.py       # Mock / Real の選択（Fallback経路を作らない）
│     ├─ mock_generator.py  # MOCK_AI=true 用。共通Mockを同じ形式で返す
│     └─ physical_output.py # Artwork + Assets → STL ZIP / PDF
├─ ai/                      # AI・画像処理Module（**呼び出し境界だけ**）
│  ├─ types.py              #   InputPhoto / AssetBlob / GenerationResult / Protocol
│  ├─ errors.py             #   AiError系。HTTP StatusやUI文言はここで決めない
│  └─ gemini.py             #   Real実装の入口。中身は AI担当（クメ先生）が入れる
└─ tests/
```

## 未決定を固定しないための約束

- **Asset Binary Storage方式は【未決定】。** 暫定で `LocalDirAssetStore` が
  Local Directoryへ書き出し `/dev/assets` から静的配信している。開発用の繋ぎであり、
  Cloud Runの複数Instance / 揮発Diskを前提にしていない。方式が決まったら
  `AssetStore` の別実装へ差し替える。**Asset Manifest の形（API境界）は変えない**
- `GET /api/v1/assets/{assetId}` は【検討中】。先回りで作らない。
  暫定の静的配信は `/api/v1` 配下に置いていない
- `GET|PUT /api/v1/artworks/{artworkId}` / finalize / bundle も作らない。
  `tests/test_no_extra_endpoints.py` がAPI表面を固定している
- Real AI失敗時に黙ってMockへ落ちる経路を作らない。`MOCK_AI` は明示Modeのみ。
  Mockの実装は Backend側（`app/services/mock_generator.py`）に置き、`ai/` は境界だけに保つ
- Upload制限・モデルID等の【PoC後FIX】値は `app/config.py` に集約し、環境変数で差し替える

## 単独でFIXしないこと

同期 / 非同期方式、Asset Binary Storage方式、Queue / Job Runner の導入、
追加Endpoint、Bundle生成主体。いずれも共通決定に影響するので公開チャンネルで共有してから進める。
