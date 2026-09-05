from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env", env_file_encoding="utf-8"
    )

    # --- Telemetry Layer ---
    telemetry_enabled: bool = False
    telemetry_buffer_size: int = 1000
    telemetry_flush_interval_seconds: int = 30
    telemetry_drift_threshold: float = 0.8
    telemetry_error_spike_threshold: float = 5.0

    # --- Investigation Layer ---
    investigation_enabled: bool = True
    investigation_changelog_max_age_days: int = 90
    investigation_rag_top_k: int = 5

    # --- Validation Layer ---
    validation_enabled: bool = True
    validation_timeout_seconds: int = 300
    validation_memory_limit: str = "512m"
    validation_cpu_limit: str = "1.0"

    # --- Execution Layer (LLM) ---
    api_base_url: str = "https://api.github.com"
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    llm_timeout_seconds: int = 60
    llm_max_tokens: int = 1024
    fix_max_attempts: int = 3
    fix_max_cost_per_run: float = 1.0
    fix_max_tokens_per_run: int = 500000
    fix_token_budget_max: int = 120000
    fix_max_patch_history: int = 10
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    search_limit: int = 10

    # --- Multi-provider Git ---
    git_provider: str = "github"
    github_token: str | None = None
    github_app_id: int | None = None
    github_app_private_key: str | None = None
    github_install_id: int | None = None
    webhook_secret: str | None = None
    gitlab_token: str | None = None
    gitlab_url: str = "https://gitlab.com"
    bitbucket_token: str | None = None
    bitbucket_workspace: str | None = None

    # --- Infrastructure ---
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    http_backoff_base_seconds: float = 1.0

    # --- Auth ---
    auth_secret_key: str = "change-me-in-production"
    auth_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7

    # --- Rate Limiting ---
    rate_limit_default: str = "60/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_webhook: str = "30/minute"


@lru_cache
def get_settings() -> Settings:
    return Settings()
