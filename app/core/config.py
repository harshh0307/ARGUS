from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_PROJECT_ROOT / ".env", env_file_encoding="utf-8"
    )

    github_spec_url: str = (
        "https://raw.githubusercontent.com/github/rest-api-description/main/"
        "descriptions/api.github.com/api.github.com.json"
    )
    github_old_spec_url: str = (
        "https://raw.githubusercontent.com/github/rest-api-description/"
        "04fd6c592fc546217404b07e0b0e581fb00a963a/"
        "descriptions/api.github.com/api.github.com.json"
    )
    snapshot_dir: str = "data/snapshots"
    api_base_url: str = "https://api.github.com"
    github_token: str | None = None
    github_app_id: int | None = None
    github_app_private_key: str | None = None
    github_install_id: int | None = None
    webhook_secret: str | None = None
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str | None = None
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    http_timeout_seconds: float = 30.0
    http_max_retries: int = 3
    http_backoff_base_seconds: float = 1.0
    openai_api_key: str | None = None
    gemini_api_key: str | None = None
    openrouter_api_key: str | None = None
    openrouter_model: str | None = None
    llm_model: str = "gpt-4o-mini"
    llm_base_url: str | None = None
    fix_max_attempts: int = 3
    embedding_api_key: str | None = None
    embedding_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    search_limit: int = 10
    # Guardrail settings
    llm_timeout_seconds: int = 60
    llm_max_tokens: int = 1024
    fix_max_cost_per_run: float = 1.0
    fix_max_tokens_per_run: int = 500000
    fix_token_budget_max: int = 120000
    fix_max_patch_history: int = 10
    # Auth settings
    auth_secret_key: str = "change-me-in-production"
    auth_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    # Rate limit settings
    rate_limit_default: str = "60/minute"
    rate_limit_auth: str = "10/minute"
    rate_limit_webhook: str = "30/minute"


@lru_cache
def get_settings() -> Settings:
    return Settings()
