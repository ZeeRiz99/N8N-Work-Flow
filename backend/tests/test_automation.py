"""P6 slice 5: Automation Center overview and Integrations."""

from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse


def test_overview_has_workflows_journey_and_outbox(client, owner, monkeypatch):  # noqa: F811
    from app.api.v1 import automation

    monkeypatch.setattr(automation, "_n8n_status", lambda: {"ok": True, "detail": "HTTP 200"})
    new_lead(client, message="Need a website, budget $2,000")
    o = client.get("/api/v1/automation/overview").json()
    assert o["n8n"]["ok"] and {w["key"] for w in o["workflows"]} == {"W1", "W4b", "W9"}
    assert [s["key"] for s in o["journey"]] == ["W1", "W2", "W3", "W4", "you", "W4b"]
    assert o["journey"][0]["count"] == 1
    assert o["outbox"]["pending"] == 1  # the lead.created event


def test_integrations_list_and_admin_only_test(client, owner, monkeypatch):  # noqa: F811
    from app.api.v1 import automation

    kinds = {i["kind"]: i for i in client.get("/api/v1/integrations").json()}
    assert set(kinds) == {"n8n", "email", "gemini", "telegram"}
    assert kinds["telegram"]["configured"] is False
    assert client.post("/api/v1/integrations/telegram/test").status_code == 409
    monkeypatch.setattr(automation, "_n8n_status", lambda: {"ok": False, "detail": "ConnectError"})
    r = client.post("/api/v1/integrations/n8n/test").json()
    assert r == {"ok": False, "detail": "n8n health check: ConnectError"}
