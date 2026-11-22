"""Test fixtures.

Database tests run against <APP_DB_NAME>_test (or TEST_DATABASE_URL), migrated with Alembic once
per session. Each test runs inside a transaction that is rolled back, so tests never see each
other's rows and never touch development data. If the test database is unreachable, database
tests are skipped with a clear reason instead of failing on connection errors.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import hash_key
from app.models import ApiKey, Organization

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _test_db_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL")
    if url:
        return url
    s = get_settings()
    base = s.sqlalchemy_url
    return base.rsplit("/", 1)[0] + f"/{s.app_db_name}_test"


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = _test_db_url()
    eng = create_engine(url, connect_args={"connect_timeout": 3})
    try:
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(
            f"test database unreachable ({type(exc).__name__}); start .\\scripts\\dev.ps1 up"
        )

    from alembic import command
    from alembic.config import Config

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    os.environ["DATABASE_URL"] = url  # env.py reads settings; point it at the test DB
    get_settings.cache_clear()
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


@pytest.fixture
def db(engine: Engine) -> Iterator[Session]:
    conn = engine.connect()
    outer = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint", expire_on_commit=False)
    try:
        yield session
    finally:
        session.close()
        outer.rollback()
        conn.close()


@pytest.fixture
def org(db: Session) -> Organization:
    o = Organization(
        name="Test Studio",
        slug=f"test-{uuid.uuid4().hex[:8]}",
        public_form_key=f"pk_test_{uuid.uuid4().hex}",
        settings={"services": ["Website Development"]},
    )
    db.add(o)
    db.flush()
    return o


@pytest.fixture
def service_key(db: Session, org: Organization) -> str:
    key = f"svc_{uuid.uuid4().hex}"
    db.add(
        ApiKey(
            organization_id=org.id,
            name="test",
            prefix=key[:8],
            key_hash=hash_key(key),
            scopes=["internal"],
        )
    )
    db.flush()
    return key


@pytest.fixture
def client(db: Session) -> Iterator[TestClient]:
    from app.core.db import get_db
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)  # no lifespan: the outbox worker does not start in tests


@pytest.fixture(autouse=True)
def _reset_rate_limiter() -> None:
    from app.api.deps import public_form_limiter

    public_form_limiter._hits.clear()
