---
name: integration
description: 担当間の接続を確認するときに使う。Mock と Real の切り替え、Contract Test、End-to-End の接続確認、CORS や環境変数の設定、Deploy後の疎通確認を扱う場合に参照する。
---

# integration

前提は `/AGENTS.md` §9, §10。

## Contract Test
```bash
python scripts/generate_mock_assets.py     # ダミーAssetを再生成
python scripts/validate_contracts.py       # 共通Mock一式を検証
python scripts/validate_contracts.py x.json  # Artwork / 生成成功Response（形は自動判定）
```

- 共通MockがSchema Validationを通ること
- **Real生成結果が同じSchemaを満たすこと**が接続確認の条件
- Frontend / Physical Output 側で独自にField名を読み替えないこと

### Frontend ↔ Backend の生成成功境界

Schemaは `contracts/generate-success-response.schema.json`。

```json
{ "artwork": { ... }, "assetManifest": { "assets": [ ... ] } }
```

- **外側のKey名は【確認待ち：チーム】。** 技術設計に定義が無く、Backendが返している形へ
  合わせた暫定案。FIXではないので、変わったらSchema / Mock / 両実装を同時に直す
- `$ref` 先の `artwork.schema.json` / `asset-manifest.schema.json` は【FIX】された正本。
  ここで再定義しない
- Artworkが参照する全 `assetId` を Manifest が解決できることまで検証される
  （余分なManifest Entryは契約違反ではないので弾かない）
- 共通Mockは `contracts/mock/generate-success-response.json`

## Mock / Real の切り替え
- Backend: `MOCK_AI=true` で実Geminiを呼ばずに同じ形式を返す
- Frontend: `VITE_API_BASE_URL` で接続先を切り替える
- **どちらのModeでも Artwork Schema は同一。**消費側で解釈を分岐させない
- `MOCK_AI` は明示的に有効化する開発・デモ用Mode。本番の隠れFallbackではない

## E2E 接続確認の最低ライン
Real AI の完成を待たず、
**共通Mock Artwork + Assets → 3D / 2D → 物理出力PoC** が同一Artwork Contractで
接続できることを最低ラインとする。

目標は Firebase Hosting の Frontend → Cloud Run の Backend の Real Runtime 接続、
および Real AI で実写真から3D Previewまで1回通すこと。

## 環境変数
Frontend（公開可・`VITE_` Prefix）: `VITE_API_BASE_URL`
Backend（Secret含む）: `GEMINI_API_KEY` / `GEMINI_MODEL` / `GEMINI_SEGMENTATION_MODEL` /
`CORS_ORIGINS` / `APP_ENV` / `MOCK_AI`

`.env` はCommitしない。`.env.example` はKey名だけ。
Frontend と Backend は別Originなので、Productionでは `CORS_ORIGINS` を
Firebase Hosting の Origin に限定する。

### CORS の確認

**CORSの失敗はServer側から見えない。** 許可Originが一致しなくてもHTTPは200で返り、
足りないのは `Access-Control-Allow-Origin` だけなので、
**curlでは成功して見えてブラウザだけが失敗する。**

実際に効いている許可Originは Health Check で確認する。

```bash
curl -s https://<backend>/health   # corsOrigins / corsOriginsInvalid を見る
```

Port違いは別Origin。Deployコマンドと `^|^` 記法は `docs/deploy.md`。
