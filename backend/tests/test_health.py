from fastapi.testclient import TestClient

from app.main import create_app


def make_client(monkeypatch, db_ok: bool) -> TestClient:
    monkeypatch.setattr(
        "app.main.check_database", lambda: (True, "ok") if db_ok else (False, "OperationalError")
    )
    return TestClient(create_app())


def test_health_is_ok_without_database(monkeypatch):
    client = make_client(monkeypatch, db_ok=False)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_ready_reports_database_down_as_503(monkeypatch):
    client = make_client(monkeypatch, db_ok=False)
    resp = client.get("/ready")
    assert resp.status_code == 503
    assert resp.json() == {"status": "not_ready", "checks": {"database": "OperationalError"}}


def test_ready_ok_when_database_up(monkeypatch):
    client = make_client(monkeypatch, db_ok=True)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_request_id_is_echoed(monkeypatch):
    client = make_client(monkeypatch, db_ok=True)
    resp = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert resp.headers["X-Request-ID"] == "abc123"


def test_request_id_generated_when_missing_or_unsafe(monkeypatch):
    client = make_client(monkeypatch, db_ok=True)
    generated = client.get("/health").headers["X-Request-ID"]
    assert len(generated) == 32
    too_long = client.get("/health", headers={"X-Request-ID": "x" * 200}).headers["X-Request-ID"]
    assert too_long != "x" * 200
