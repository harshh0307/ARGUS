from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
