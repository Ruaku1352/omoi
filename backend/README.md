# backend — Cloud Run Deploy Unit

Python 3.13系 + FastAPI 0.139系 + Pydantic【仮決定】。
pyproject.toml + Lock File で依存を再現可能にする。

AI・画像処理は `ai/` 配下の内部Moduleとして置く。独立Serviceにしない。

未Scaffold。担当（もりかん / だいちゃん）が初期化する。
実装前提は `/AGENTS.md` §4・§5・§6 と `skills/backend/SKILL.md` を参照。

生成Endpoint: `POST /api/v1/artworks/generate`（これのみFIX）
