from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://touchgo:touchgo@localhost:5432/touchgo_news"
    sources_config_path: str = "config/sources.yaml"
    anthropic_api_key: str = ""
    classification_batch_size: int = 20
    classification_interval_minutes: int = 3
    classification_max_attempts: int = 5
    scoring_batch_size: int = 20
    scoring_interval_minutes: int = 3
    scoring_max_attempts: int = 5
    default_reviewer_id: str = "reviewer"


@lru_cache
def get_settings() -> Settings:
    return Settings()
