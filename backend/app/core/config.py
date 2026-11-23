"""Application settings, read from environment variables and the repo-root .env file."""

from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, field_validator
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
    # 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 (::1) first, and Docker
    # publishes the port on 127.0.0.1 only, so every connection waited for the IPv6 attempt.
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432
    db_connect_timeout_seconds: int = 3

    # URLs
    cors_origins: str = "http://localhost:3000"
    frontend_public_url: str = "http://localhost:3000"
    # Backend -> n8n webhooks (127.0.0.1 for the same IPv6 reason as the database).
    n8n_webhook_base_url: str = "http://127.0.0.1:5678/webhook/rl"
    n8n_webhook_secret: str = Field(default="", repr=False)
    # n8n -> backend: the plain key lives only in .env and the n8n credential; the DB keeps a hash.
    service_api_key: str = Field(default="", repr=False)

    # Outbox dispatcher
    outbox_dispatch_enabled: bool = True
    outbox_poll_seconds: float = 5.0
    outbox_max_attempts: int = 8
    outbox_http_timeout_seconds: float = 10.0

    # Public form
    public_form_rate_limit_per_minute: int = 10

    # Auth (D7): short-lived access JWT + rotating refresh token, both in httpOnly cookies.
    app_secret_key: str = Field(default="", repr=False)
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 14
    login_rate_limit_per_minute: int = 5
    # Self-service sign-up creates a new organization; on in development, off in production.
    allow_registration: bool = True

    # AI (ADR 004: Gemini only). "fake" runs the offline deterministic provider (tests, CI).
    ai_provider: str = "gemini"

    @field_validator("ai_provider", mode="before")
    @classmethod
    def _provider_word(cls, v: str) -> str:
        """Keep only the first word: a .env comment without a space before '#' would
        otherwise become part of the value ("gemini# comment")."""
        return str(v).split("#")[0].strip().lower() or "gemini"

    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = ""
    gemini_model_fallback: str = ""
    ai_timeout_seconds: float = 30.0
    ai_daily_call_cap: int = 500  # per organization; past it, leads get a provisional score
    # All Gemini requests on this machine per quota day (midnight Pacific), retries included.
    # Kept under the free tier's daily quota so it is never exhausted (ADR 011).
    gemini_daily_budget: int = 18

    # Integrations page ("Test connection"); the backend runs on the host, so Mailpit is local.
    smtp_test_host: str = "127.0.0.1"
    smtp_test_port: int = 1025
    n8n_editor_url: str = "http://localhost:5678"
    telegram_bot_token: str = Field(default="", repr=False)
    ai_retry_enabled: bool = True  # retry failed analyses with backoff (never drop a lead)
    ai_retry_poll_seconds: float = 30.0

    @property
    def gemini_models(self) -> tuple[str, str]:
        """An empty value in .env means "use the default", not "no model"."""
        return (
            self.gemini_model.strip() or "gemini-3.6-flash",
            self.gemini_model_fallback.strip() or "gemini-3.5-flash",
        )

    @property
    def cookie_secure(self) -> bool:
        return self.app_env != "development"

    # Temporary dev access to dashboard reads (P3 only; replaced by real auth in P4).
    demo_org_slug: str = "harbor-web"

    @property
    def n8n_webhook_base(self) -> str:
        """Webhook base with localhost pinned to IPv4 (Docker publishes 127.0.0.1 only)."""
        return self.n8n_webhook_base_url.rstrip("/").replace("://localhost", "://127.0.0.1")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

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
