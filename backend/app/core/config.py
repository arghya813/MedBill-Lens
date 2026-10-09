"""Application configuration loaded from environment variables / .env file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_DATA_DIR = BACKEND_DIR / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDBILL_",
        env_file=(BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- App -------------------------------------------------------------
    app_name: str = "MedBill Lens"
    app_version: str = "1.0.0"
    environment: str = Field(default="development")
    debug: bool = False
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # --- Database --------------------------------------------------------
    # SQLite by default; point at PostgreSQL later with:
    #   postgresql+psycopg://user:pass@localhost:5432/medbill
    database_url: str = "sqlite:///./medbill.db"
    sql_echo: bool = False

    # --- AI provider -----------------------------------------------------
    # "demo" | "openai" | "openai_compatible"
    # Leave blank / "demo" to run fully offline with the deterministic
    # demo provider. The application is never blocked by a missing key.
    ai_provider: str = "demo"
    ai_api_key: str = ""
    ai_base_url: str = "https://api.openai.com/v1"
    ai_model: str = "gpt-4o-mini"
    ai_vision_model: str = ""
    ai_timeout_seconds: float = 60.0
    ai_max_retries: int = 2
    # When a real provider fails, fall back to the deterministic provider
    # instead of surfacing an error to the user.
    ai_fallback_to_demo: bool = True

    # --- Uploads & privacy ----------------------------------------------
    max_upload_size_mb: int = 10
    raw_file_retention_minutes: int = 30
    storage_dir: str = ""  # defaults to ./data/uploads (git-ignored)
    serve_raw_files: bool = False  # never expose uploaded docs publicly
    anonymize_reports_by_default: bool = True

    # --- Demo mode -------------------------------------------------------
    demo_mode: bool = True
    seed_demo_benchmarks: bool = True

    # --- Rate limiting ---------------------------------------------------
    rate_limit_enabled: bool = True
    rate_limit_requests: int = 60
    rate_limit_window_seconds: int = 60

    # --- Authentication (architecture only, off by default) -------------
    auth_enabled: bool = False
    api_key_header: str = "X-API-Key"
    api_key: str = ""

    # --- Flagging thresholds (percent above benchmark max) ---------------
    # Fully deterministic and configurable. AI never decides these.
    flag_within_tolerance_pct: float = 0.0
    flag_review_pct: float = 10.0
    flag_attention_pct: float = 25.0
    # Minimum records required before a benchmark is considered usable.
    benchmark_min_records: int = 1
    # Minimum absolute currency difference before a difference is highlighted.
    min_significant_difference: float = 100.0

    # --- Benchmark matching ---------------------------------------------
    # Only records matching city + hospital category are considered.
    benchmark_require_city_match: bool = True
    benchmark_require_category_match: bool = True
    benchmark_city_tier_fallback: bool = True
    benchmark_service_similarity_threshold: float = 0.55
    benchmark_match_treatment: bool = True

    # --- Locale ----------------------------------------------------------
    currency_symbol: str = "₹"
    currency_code: str = "INR"
    locale: str = "en-IN"

    @field_validator("ai_provider")
    @classmethod
    def _normalize_provider(cls, value: str) -> str:
        value = (value or "demo").strip().lower()
        if value in {"", "none", "off", "mock", "demo", "deterministic"}:
            return "demo"
        return value

    @property
    def storage_path(self) -> Path:
        if self.storage_dir:
            path = Path(self.storage_dir)
        else:
            path = DEFAULT_DATA_DIR / "uploads"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def data_path(self) -> Path:
        path = DEFAULT_DATA_DIR
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def sample_bills_path(self) -> Path:
        path = self.data_path / "sample_bills"
        path.mkdir(parents=True, exist_ok=True)
        return path

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_size_mb) * 1024 * 1024

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def provider_requested_is_real(self) -> bool:
        return self.ai_provider != "demo"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
