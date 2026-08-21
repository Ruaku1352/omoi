# omoi

Our Memories, One Image — 複数の写真から思い出を象徴する要素を抽出し、
多層作品として構成して、3Dプリンターで2.5Dの物理作品にする。

Tornado 2026「ミリオンがえし」

---

## 最初に読むもの

### 人（チーム全員）

**自力で読むのは Drive「ドパガキ向け_5分でわかる設計理解」だけでよい。**
omoiの全体像と、全員がそろえておく前提がここにまとまっている。

そこから先は、必要な範囲だけを**AIと一緒に**確認する。全部を自分で読む必要はない。

| 知りたいこと | 見るもの |
|---|---|
| 全体像・共通前提 | Drive「ドパガキ向け_5分でわかる設計理解」 |
| 何を作るか | Drive「要件定義」 |
| 技術的な決定と状態ラベル | Drive「技術設計」（人間向け仕様の正本） |
| 実際のデータ形・API | `contracts/`（Machine Readable Contractの正本） |

### AI Coding Agent

入口は [`AGENTS.md`](AGENTS.md)。そこから領域別の `skills/*/SKILL.md` を辿る。
Agentが自動読込しない場合は、作業開始時に明示的に読ませる。

### 実装を始めるとき

担当本人が「**Input → 処理 → Output**」を中心に自分の担当処理を説明できれば開始してよい。
PMの個別承認は原則不要で、担当内部だけで完結する実装は承認を待たない。

Mermaid構成図と sequenceDiagram の2枚固定は必須ではない。必要な箇所だけ作り、
作った図はRenderして本人が目視確認する。詳細は `skills/project-context/SKILL.md`。

共通技術設計 / Artwork Data / API・Protocol / MVP Scope / 他担当の実装前提 / 費用へ
影響する変更だけは、担当内で確定させず公開チャンネルで共有してから進める。

---

## 構成

```
/
├─ frontend/          # Firebase Hosting Deploy Unit（React / Vite）
├─ backend/           # Cloud Run Deploy Unit（FastAPI）
│  └─ ai/             #   AI・画像処理Module（独立Serviceにしない）
├─ contracts/         # Deploy Unitを跨ぐ共通Contract（Machine Readableな正本）
│  ├─ artwork.schema.json                   # Artwork Data Schema
│  ├─ asset-manifest.schema.json            # assetId → url の解決表
│  ├─ generate-success-response.schema.json # 生成成功Response（束ねるだけ・Key名は確認中）
│  ├─ mock/artwork.json                     # 共通Mock（写真5枚・4層）
│  ├─ mock/asset-manifest.json              # 共通MockのAsset Manifest
│  ├─ mock/generate-success-response.json   # 共通Mockの生成成功Response
│  └─ assets/                               # Mockが参照するダミーAsset
├─ skills/            # AI Coding Agent向けSkills（7領域）
├─ scripts/           # 開発補助
├─ AGENTS.md
└─ README.md
```

Top Levelは担当者別ではなく、**「一緒にBuild / Deploy / 実行される単位」**と
**「複数Unitから共有されるContract / 開発基盤」**で切っている。

### 意図的に存在しないもの

以下は「まだ決まっていない」ため、先回りで作っていない。必要性が確定してから追加する。

- `physical-output/` — STL等の生成をBrowser / Backend / 独立Local Toolのどこで実行するかが未決定
- `ai/`（Top Level）— AI・画像処理はBackend内部Moduleとして `backend/ai/` に置く
- `worker/` `queue/` — 同期 / 非同期方式が未決定

---

## セットアップ

```bash
pip install jsonschema pillow

python scripts/generate_mock_assets.py   # ダミーAssetを生成（再実行可）
python scripts/validate_contracts.py     # 共通Mock一式を検証
```

`.env.example` をコピーして各自の `.env` を作る。**`.env` はCommitしない。**

```bash
cp .env.example frontend/.env
cp .env.example backend/.env
```

### frontend / backend

```bash
cd frontend && npm install && npm run dev   # Vite Dev Server
cd backend  && uv sync --all-groups \
            && MOCK_AI=true uv run uvicorn app.main:app --reload
```

Scaffold済み。詳細は `frontend/README.md` / `backend/README.md`。
画面とReal AI処理はこれから各担当が積む。

---

## 共通Mockで並行開発する

Real AIの完成を待たずに各担当が開発を始められるよう、
`contracts/mock/` + `contracts/assets/` を全担当の共通Fixtureにしている。

| Fixture | 使うところ |
|---|---|
| `mock/artwork.json` | Artwork Data を読む側すべて（3D / 2D / 物理出力） |
| `mock/asset-manifest.json` | `assetId` → URL の解決を組む側 |
| `mock/generate-success-response.json` | Frontend ↔ Backend の生成成功境界（Key名は確認中） |

- 写真5枚・4層の代表ケース。ただし `layers[]` / `sourcePhotos[]` は**可変長**
- 差し替えUIを単独検証できるよう `replacementCandidates` を持つLayerを含む
- 透過領域を実際に持つ RGBA PNG
- Mock Manifest の `url` は Placeholder。実際のURLはRuntime依存で環境ごとに解決する

Real生成結果も同じSchemaを満たすことが接続確認の条件。
Artwork単体でも生成成功Responseでも、そのまま渡せば形を自動判定して検証する。

```bash
python scripts/validate_contracts.py path/to/real-artwork.json
python scripts/validate_contracts.py path/to/generate-response.json
```

---

## 共通Contractを変えたいとき

`contracts/` / API / Repository Top Level / 共通Stack / P0スコープ / 費用に影響する変更は、
担当内で確定させず**公開チャンネルで共有してから**進める。

変更する場合は同一PRで Schema / Mock / `AGENTS.md` / 関連Skills を同時更新する。
破壊的変更なら `schemaVersion` を上げる。

担当Directory内部だけの変更はPM承認不要。
