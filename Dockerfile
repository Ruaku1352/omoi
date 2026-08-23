# omoi Backend — Cloud Run Deploy Unit
#
# Build ContextはリポジトリルートUnit（docs/deploy.md参照）。
# contracts/ はDeploy Unitを跨ぐ共通Contract（AGENTS.md §2.2）であり、backend/配下へ
# コピーして複製・分岐させない。ローカル開発と同じ「backend/ と contracts/ が兄弟」の
# 相対配置をイメージ内でも保ち、backend/app/config.py の REPO_ROOT解決
# （BACKEND_DIRの親 = contracts/の親）がそのまま通るようにしている。
# そのためCONTRACTS_DIR環境変数は指定不要（デフォルトのまま動く）。
#
# ビルド（リポジトリルートで実行すること。backend/へcdしない）:
#   docker build -t omoi-backend .
#
# ローカル起動確認:
#   docker run --rm -p 8080:8080 -e MOCK_AI=true -e CORS_ORIGINS=http://localhost:5173 omoi-backend
#
# 詳細・Cloud Runへのdeploy手順は docs/deploy.md 参照。

FROM python:3.13-slim AS base

# uv公式イメージからバイナリだけ持ってくる。ローカルのuvバージョンと合わせたい場合は
# タグを固定する（例: ghcr.io/astral-sh/uv:0.12.5）。ここでは latest を使っている。
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1

WORKDIR /srv

# 依存だけ先に解決してDocker Layer Cacheを効かせる。
# アプリコードだけの変更ではこのレイヤーは再実行されない。
COPY backend/pyproject.toml backend/uv.lock backend/.python-version /srv/backend/
RUN cd /srv/backend && uv sync --locked --no-install-project --no-dev
# Real AI実装（ai/gemini.pyがgoogle-genaiを使い始めるタイミング）以降は
# 上の行を `uv sync --locked --no-install-project --no-dev --extra gemini` に変える。

# アプリ本体 + 共通Contract。backend/ と contracts/ の兄弟関係を保ったまま積む。
COPY backend /srv/backend
COPY contracts /srv/contracts

RUN cd /srv/backend && uv sync --locked --no-dev

RUN useradd --no-create-home --shell /usr/sbin/nologin appuser \
    && chown -R appuser:appuser /srv
USER appuser

ENV PATH="/srv/backend/.venv/bin:${PATH}"
WORKDIR /srv/backend

# Cloud RunはPORTを実行時に注入するので8000固定にしない。
# 8080はdocker run単体で試すときのローカル既定値。
ENV PORT=8080
EXPOSE 8080

# Shell形式のCMDにして起動時に $PORT を展開させる（execで余計なshellを残さない）。
CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
