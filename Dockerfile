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
# Mockのローカル起動確認:
#   docker run --rm -p 8080:8080 -e MOCK_AI=true -e CORS_ORIGINS=http://localhost:5173 omoi-backend
# Real AI Imageは、事前に `uv --directory backend run python ../scripts/fetch_efficientsam_onnx.py`
# で取得・checksum検証した backend/.models/efficientsam_ti.onnx を含め、
# `docker build --target real-ai -t omoi-backend-real .` としてbuildする。Runtime downloadはしない。
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

# アプリ本体 + 共通Contract + Physical Output PoC生成器。
# backend/ と contracts/ の兄弟関係を保ったまま積む。
COPY backend /srv/backend
COPY contracts /srv/contracts
COPY scripts /srv/scripts

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

# Real Cloud Run用target。Model ArtifactはGit管理せず、Build Contextへ明示的に供給する。
FROM base AS real-ai
COPY --chown=appuser:appuser backend/.models/efficientsam_ti.onnx /srv/models/efficientsam_ti.onnx
# split encoder / decoder。両方設定したときだけsplit経路が有効になり、
# source photoごとにencoderを1回、bbox / retryごとにdecoderを実行する
# （docs/ai/22 §24.4。monolithicに対して約45%短縮）。
COPY --chown=appuser:appuser backend/.models/efficientsam_ti_encoder.onnx /srv/models/efficientsam_ti_encoder.onnx
COPY --chown=appuser:appuser backend/.models/efficientsam_ti_decoder.onnx /srv/models/efficientsam_ti_decoder.onnx
ENV EFFICIENTSAM_MODEL_PATH=/srv/models/efficientsam_ti.onnx
ENV EFFICIENTSAM_ENCODER_MODEL_PATH=/srv/models/efficientsam_ti_encoder.onnx
ENV EFFICIENTSAM_DECODER_MODEL_PATH=/srv/models/efficientsam_ti_decoder.onnx

# `docker build .` の既存Mock開発経路をModel Artifact必須にしない。
# `gcloud run deploy --source .` もDockerfileの最終stageをBuildするため、
# このtargetはMock専用。Real AIのtarget選択・Deploy方式はBackend/GCP担当が決定する。
FROM base AS default
