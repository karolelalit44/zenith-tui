from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    app_name: str = "FastAPI Demo API"
    app_version: str = "1.0.0"
    debug: bool = False
    database_url: str = "postgresql+psycopg2://user:pass@db:5432/demo_db"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

@lru_cache
def get_settings() -> Settings:
    return Settings()
