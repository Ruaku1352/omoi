# omoi

Our Memories, One Image — 複数の写真から思い出を象徴する要素を抽出し、
多層作品として構成して、3Dプリンターで2.5Dの物理作品にする。

Tornado 2026「ミリオンがえし」

---

## 最初に読むもの

| 読む人 | ファイル |
|---|---|
| **AI Coding Agent** | [`AGENTS.md`](AGENTS.md) ← 必ず最初に |
| 実装担当 | `AGENTS.md` → 自分の領域の `skills/*/SKILL.md` |
| 契約を確認したい | `contracts/artwork.schema.json` |

人間向けの仕様正本はDriveの「要件定義」「技術設計」。
Repository上のMachine Readableな契約の正本は `contracts/`。

---

## 構成

```
/
├─ frontend/          # Firebase Hosting Deploy Unit（React / Vite）
├─ backend/           # Cloud Run Deploy Unit（FastAPI）
│  └─ ai/             #   AI・画像処理Module（独立Serviceにしない）
├─ contracts/         # Deploy Unitを跨ぐ共通Contract
│  ├─ artwork.schema.json        # Artwork Data Schema（正本）
│  ├─ asset-manifest.schema.json # 生成成功時に併せて返すAsset解決表
│  ├─ mock/artwork.json          # 共通Mock（写真5枚・4層）
│  └─ assets/                    # Mockが参照するダミーAsset
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
python scripts/validate_contracts.py     # 共通Mockを検証
```

`.env.example` をコピーして各自の `.env` を作る。**`.env` はCommitしない。**

```bash
cp .env.example frontend/.env
cp .env.example backend/.env
```

`frontend/` と `backend/` は未Scaffold。各担当が初期化する。

---

## 共通Mockで並行開発する

Real AIの完成を待たずに各担当が開発を始められるよう、
`contracts/mock/artwork.json` + `contracts/assets/` を全担当の共通Fixtureにしている。

- 写真5枚・4層の代表ケース。ただし `layers[]` / `sourcePhotos[]` は**可変長**
- 差し替えUIを単独検証できるよう `replacementCandidates` を持つLayerを含む
- 透過領域を実際に持つ RGBA PNG

Real生成結果も同じSchemaを満たすことが接続確認の条件。

```bash
python scripts/validate_contracts.py path/to/real-artwork.json
```

---

## 共通Contractを変えたいとき

`contracts/` / API / Repository Top Level / 共通Stack / P0スコープ / 費用に影響する変更は、
担当内で確定させず**公開チャンネルで共有してから**進める。

変更する場合は同一PRで Schema / Mock / `AGENTS.md` / 関連Skills を同時更新する。
破壊的変更なら `schemaVersion` を上げる。

担当Directory内部だけの変更はPM承認不要。
