"""Database engine. Sync SQLAlchemy 2 with psycopg 3 (D4)."""

from functools import lru_cache

from sqlalchemy import Engine, create_engine, text

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine:
    settings = get_settings()
    return create_engine(
        settings.sqlalchemy_url,
        pool_pre_ping=True,
        connect_args={"connect_timeout": settings.db_connect_timeout_seconds},
    )


def check_database() -> tuple[bool, str]:
    """Return (ok, detail). The detail never contains connection strings or passwords."""
    try:
        with get_engine().connect() as conn:
            conn.execute(text("SELECT 1"))
        return True, "ok"
    except Exception as exc:  # noqa: BLE001 - report any failure as not ready
        return False, type(exc).__name__
