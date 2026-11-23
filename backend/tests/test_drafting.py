"""P5: reply drafting with code checks (master prompt §8.4)."""

import pytest

from app.ai.draft_checks import OPT_OUT_LINE, finalize_body, passed, run_checks
from app.ai.provider import AIUnavailable
from app.services import analysis
from tests.test_crm import new_lead, owner  # noqa: F401 - fixture reuse

MSG = (
    "We run a bakery and need a new website with online ordering. Budget around $2,000, "
    "live within a month. Can you send a quote?"
)
CATALOG = [{"name": "Website Development", "price_min_minor": 150000, "price_max_minor": 500000}]


def checks(subject="Re: your website", body="Hello,\nThanks.", services=None, **kw):
    args = dict(
        catalog=CATALOG,
        allowed_domains={"harborweb.example.com"},
        do_not_contact=False,
        has_email=True,
    )
    args.update(kw)
    return {c["key"]: c for c in run_checks(subject, finalize_body(body), services or [], **args)}


def test_clean_draft_passes_and_opt_out_is_added_by_code():
    c = checks(
        body="We can build it. Projects range from $1,500 to $5,000.",
        services=["Website Development"],
    )
    assert all(x["ok"] for x in c.values())
    assert OPT_OUT_LINE in finalize_body("Hi")
    assert finalize_body(f"Hi\n{OPT_OUT_LINE}").count(OPT_OUT_LINE) == 1


@pytest.mark.parametrize(
    ("body", "key"),
    [
        ("Our price is $999 for everything.", "prices"),
        ("See http://evil.example.net/offer", "links"),
        ("We can give you 20% off this week.", "promises"),
        ("I've attached our brochure.", "promises"),
        ("Let's meet on Monday at 3pm.", "promises"),
        ("We will deliver within 5 days.", "promises"),
        ("word " * 300, "length"),
    ],
)
def test_each_violation_is_caught(body, key):
    assert checks(body=body)[key]["ok"] is False


def test_unknown_service_do_not_contact_and_language():
    c = checks(services=["Mobile App"], do_not_contact=True, language="de")
    assert not c["services"]["ok"] and not c["contactable"]["ok"]
    assert c["language"]["ok"] is False and c["language"]["severity"] == "warn"
    assert passed([c["language"]])  # a warning alone does not block


def test_allowed_link_passes():
    assert checks(body="Our work: https://harborweb.example.com/portfolio")["links"]["ok"]


def test_generate_uses_facts_and_passes_checks(client, owner):  # noqa: F811
    lead = new_lead(client, message=MSG)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")
    resp = client.post(f"/api/v1/leads/{lead['id']}/drafts/generate", json={"style": "friendly"})
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["to"] == "amira@example.com" and d["source"] == "fake"
    assert d["body"].startswith("Hi Amira") and d["body"].endswith(OPT_OUT_LINE)
    assert d["all_passed"], d["checks"]
    timeline = client.get(f"/api/v1/leads/{lead['id']}/activities").json()
    assert any(a["type"] == "draft_generated" for a in timeline)


def test_no_draft_for_spam(client, owner):  # noqa: F811
    spam = "Cheap SEO services and backlinks! Visit http://spam.example.net for crypto deals."
    lead = new_lead(client, message=spam)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")
    resp = client.post(f"/api/v1/leads/{lead['id']}/drafts/generate", json={})
    assert resp.status_code == 409 and "spam" in resp.text


def test_ai_outage_falls_back_to_a_template(client, owner, monkeypatch):  # noqa: F811
    lead = new_lead(client, message=MSG)
    client.post(f"/api/v1/leads/{lead['id']}/reanalyze")

    class Down:
        name = "gemini"

        def generate(self, *a, **k):
            raise AIUnavailable("ClientError 429")

    monkeypatch.setattr(analysis, "get_provider", lambda: Down())
    d = client.post(f"/api/v1/leads/{lead['id']}/drafts/generate", json={}).json()
    assert d["source"] == "template" and "429" in d["note"] and d["all_passed"]


def test_recheck_after_edit_catches_new_problems(client, owner):  # noqa: F811
    lead = new_lead(client, message=MSG)
    resp = client.post(
        f"/api/v1/leads/{lead['id']}/drafts/check",
        json={"subject": "Hi", "body": "Special 50% discount, only $99!", "services_mentioned": []},
    ).json()
    bad = {c["key"] for c in resp["checks"] if not c["ok"]}
    assert {"prices", "promises"} <= bad and resp["all_passed"] is False


def test_questions_skip_what_the_lead_record_already_has():
    from types import SimpleNamespace

    from app.services.drafting import open_questions

    lead = SimpleNamespace(
        phone_raw="+1 415 555 0100", full_name="Dan", email="d@x.com", company=None
    )
    got = open_questions(["phone_number", "contact name", "Budget", "company", "budget"], lead)
    assert got == ["budget", "company"]
