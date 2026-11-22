"""Application settings, read from environment variables and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"

    # Database: DATABASE_URL wins; otherwise it is built from the APP_DB_* values.
    database_url: str = ""
    app_db_name: str = "replyline"
    app_db_user: str = "replyline_app"
    app_db_password: str = Field(default="", repr=False)
    postgres_host: str = "localhost"
    postgres_port: int = 5432
    db_connect_timeout_seconds: int = 3

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        password = quote(self.app_db_password, safe="")
        return (
            f"postgresql+psycopg://{self.app_db_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.app_db_name}"
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
