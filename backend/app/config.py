from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "SignalHub"
    environment: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:///./signalhub.db"
    lancedb_path: str = "./data/lancedb"
    hubspot_access_token: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
