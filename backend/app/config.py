"""環境変数からの設定読み込み。

Key名の共有は Repository Root の `.env.example`。Secret値はCommitしない（AGENTS.md §10）。
【PoC後FIX】の値をコードへ直書きせず、ここへ集約して環境変数で差し替えられるようにする。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ---- 実行環境 ----
    app_env: str = "local"

    # ---- Mock ----
    # true で実Geminiを呼ばず共通Mock相当を返す。明示Modeであり隠れFallbackではない。
    mock_ai: bool = False
    # 共通Contract（`contracts/`）の場所。Deploy時にCopy先が変わるなら差し替える。
    contracts_dir: Path = REPO_ROOT / "contracts"

    # ---- CORS ----
    # Frontend と Backend は別Origin。Productionでは必要最小限へ限定する。
    cors_origins: str = ""

    # ---- AI ----
    gemini_api_key: str | None = None
    gemini_model: str | None = None
    # physical_layer_v2がReal生成の既定。v3 architectureはPoC比較用に残す。
    semantic_profile: str = "physical_layer_v2"
    segmentation_backend: str = "efficient_sam_onnx"
    efficientsam_model_path: Path | None = None
    segmentation_max_retries: int = Field(default=1, ge=0, le=3)
    candidate_count: int = Field(default=12, ge=1, le=20)
    # MVP production profileは4層を成功条件にする。Schema自体の可変長性は維持する。
    target_layer_min: int = Field(default=4, ge=1, le=20)
    target_layer_max: int = Field(default=4, ge=1, le=20)
    # 2L判 Landscape (178 mm x 127 mm)。Contract Schemaの固定値ではなく生成Policy。
    artwork_canvas_aspect_ratio: float = Field(default=178 / 127, gt=0)
    gemini_analysis_max_side: int = Field(default=1536, ge=256, le=4096)
    gemini_request_timeout_ms: int = Field(default=120_000, ge=1_000, le=600_000)
    segmentation_max_side: int = Field(default=1024, ge=256, le=4096)
    layer_padding_px: int = Field(default=8, ge=0, le=256)
    layout_min_scale: float = Field(default=0.05, gt=0)
    layout_max_scale: float = Field(default=1.2, gt=0)
    # physical_layer_v2の内部構図制約。Artwork Data / 共通Contractには出さない。
    physical_scene_anchor_min_scale: float = Field(default=0.60, gt=0, le=1)
    physical_max_bottom_gap: float = Field(default=0.30, ge=0, le=1)
    # physical_layer_v3_architectureだけで使う、主建物Maskの微小孤立成分除去上限。
    # 閾値を超える分離領域は結合せず不採用にする。
    architecture_micro_island_max_area_ratio: float = Field(default=0.001, ge=0, le=1)
    # physical profileの一般subjectで除去できる微小孤立成分の面積比上限。
    # 【PoC後FIX】暫定0.5%。主成分以外の合計がこの値を超えるMaskは不採用にする。
    mask_micro_island_max_area_ratio: float = Field(default=0.005, ge=0, le=1)
    # Quality Gateは校正前は観測のみ。値はPoC後に環境変数で明示設定する。
    quality_gate_mode: str = "observe"
    quality_max_component_count: int | None = Field(default=None, ge=1)
    quality_min_largest_component_ratio: float | None = Field(default=None, ge=0, le=1)
    quality_min_bbox_coverage: float | None = Field(default=None, ge=0, le=1)
    quality_reject_border_touch: bool = False
    quality_diagnostics_max_side: int = Field(default=1024, ge=64, le=4096)

    # ---- Upload制限【PoC後FIX】----
    # 代表ケースは写真5枚だが、固定5枚の契約ではない。実測後に見直す。
    max_photos: int = Field(default=20, ge=1)
    max_photo_bytes: int = Field(default=15 * 1024 * 1024, ge=1)
    max_total_upload_bytes: int = Field(default=60 * 1024 * 1024, ge=1)

    # ---- Asset公開 ----
    # 既定はLocal Directory + 静的配信（開発用の暫定実装）。
    # "gcs" にするとGCS Bucketへ書き出す。GCS_BUCKET等はチームでBucket名・
    # URL方式・保持期間を確認してから有効にする（AGENTS.md: Asset Binary Storage方式は
    # 単独でFIXしない）。
    asset_backend: str = "local"
    asset_dir: Path = BACKEND_DIR / ".dev-assets"
    # 静的配信のURL Prefix。Product APIの `/api/v1` 配下には置かない。
    asset_mount_path: str = "/dev/assets"
    # 外部Storage等へ移したときのURL Prefix上書き。未設定ならRequestのOriginを使う。
    asset_public_base_url: str | None = None
    gcs_bucket: str | None = None
    gcs_asset_prefix: str = "assets"
    # true: 公開URL(バケット自体をpublicにする前提)。false: 署名付きURL。
    gcs_asset_public: bool = False
    gcs_signed_url_ttl_seconds: int = Field(default=3600, ge=60)

    # ---- 非同期化 ----
    # Job Store: "memory"(既定・ローカル/テスト用) / "firestore"(本番)。
    job_store_backend: str = "memory"
    # 実行基盤: "inline"(既定・ローカル/テスト用。enqueue内で直接実行する)
    #          / "cloud_tasks"(本番。同一Cloud RunのInternal Worker Endpointを叩く)。
    task_queue_backend: str = "inline"
    firestore_project_id: str | None = None
    firestore_collection: str = "jobs"
    # 一時エラーの最大試行回数（同じjobIdのまま。技術設計の非同期化方針Doc §6）。
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    # Cloud Tasks enqueue用。実際のQueue / Serviceは事前にチームでProvisionする。
    cloud_tasks_project_id: str | None = None
    cloud_tasks_location: str | None = None
    cloud_tasks_queue: str = "omoi-artwork-generate"
    # WorkerがHTTPで叩かれる自サービスのURL（例: https://omoi-backend-xxx.a.run.app）。
    cloud_tasks_worker_base_url: str | None = None
    # Cloud TasksのOIDC token発行に使うService Account。
    cloud_tasks_service_account_email: str | None = None
    # Job入力写真の一時置き場（Cloud Tasks経路のみ使用。Inline経路はMemory内で完結する）。
    job_input_backend: str = "local"
    job_input_dir: Path = BACKEND_DIR / ".dev-job-input"
    gcs_job_input_prefix: str = "job-input"
    # Internal Worker EndpointをCloud Tasks以外から叩かせないための共有Secret。
    # 本番では必ず設定する（未設定だと`APP_ENV=deployed`でWorker Endpointが503を返す）。
    task_worker_token: str | None = None

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def contracts_assets_dir(self) -> Path:
        return self.contracts_dir / "assets"


@lru_cache
def get_settings() -> Settings:
    return Settings()
