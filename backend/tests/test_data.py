"""Phase 4 slices 4–5: CSV import (preview, errors, merge, limits), export (formula injection),
and fuzzy duplicate review (scan, merge, dismiss, never automatic)."""

import csv
import io
import uuid

import pytest
from sqlalchemy import func, select

from app.models import AuditLog, Lead, LeadInquiry
from app.services import csv_io

PW = "Sunrise-Bakery-2026"  # fictional test-only password  # gitleaks:allow

CSV = (
    "Name,Email,Phone,Company,Notes\n"
    "Amira Hassan,amira@example.com,(415) 555-0132,Cedar & Pine Bakery,Wants a website\n"
    "Tomas Rivera,tomas@example.com,,Rivera Auto Care,\n"
    ",nobody@example.com,,No Name Ltd,\n"
    "Lena Fischer,not-an-email,,Fischer Studio,\n"
    "Amira H.,AMIRA@example.com,,,Second message\n"
)


@pytest.fixture
def owner(client):
    resp = client.post(
        "/api/v1/auth/register",
        json={
            "organization_name": "Harbor Test",
            "full_name": "Jordan Lee",
            "email": "jordan@example.com",
            "password": PW,
        },
    )
    assert resp.status_code == 201
    return resp.json()


def org_count(db, owner, model=Lead):
    org_id = uuid.UUID(owner["organization_id"])
    return db.scalar(select(func.count()).select_from(model).where(model.organization_id == org_id))


def test_preview_guesses_columns_reports_errors_and_saves_nothing(client, db, owner):
    report = client.post("/api/v1/leads/import", json={"csv": CSV}).json()
    assert report["dry_run"] is True
    assert report["mapping"] == {
        "full_name": "Name",
        "email": "Email",
        "phone": "Phone",
        "company": "Company",
        "message": "Notes",
    }
    assert report["total_rows"] == 5 and report["valid_rows"] == 3
    assert report["would_create"] == 2 and report["would_merge"] == 1  # row 5 = row 1's email
    assert {(e["row"], e["field"]) for e in report["errors"]} == {(3, "full_name"), (4, "email")}
    assert org_count(db, owner) == 0


def test_import_creates_merges_and_audits(client, db, owner):
    report = client.post("/api/v1/leads/import", json={"csv": CSV, "dry_run": False}).json()
    assert report["created"] == 2 and report["merged"] == 1
    assert org_count(db, owner) == 2
    assert org_count(db, owner, LeadInquiry) == 2  # two rows had a message
    amira = db.scalar(select(Lead).where(Lead.email_normalized == "amira@example.com"))
    assert amira.phone_e164 == "+14155550132" and amira.ai_status == "skipped"
    row = db.scalar(select(AuditLog).where(AuditLog.action == "leads.imported"))
    assert row.summary["created"] == 2 and "amira" not in str(row.summary).lower()


def test_explicit_mapping_and_bad_mapping(client, owner):
    text = "Client,Mail\nPriya Nair,priya@example.com\n"
    ok = client.post(
        "/api/v1/leads/import",
        json={"csv": text, "mapping": {"full_name": "Client", "email": "Mail"}},
    )
    assert ok.json()["would_create"] == 1
    bad = client.post("/api/v1/leads/import", json={"csv": text, "mapping": {"full_name": "Nope"}})
    assert bad.status_code == 422
    no_name = client.post("/api/v1/leads/import", json={"csv": "Mail\nx@example.com\n"})
    assert no_name.status_code == 422


def test_import_limits():
    with pytest.raises(csv_io.CsvRejected):
        csv_io.parse("Name\n" + "x\n" * (csv_io.MAX_ROWS + 1))
    with pytest.raises(csv_io.CsvRejected):
        csv_io.parse("")
    headers, rows = csv_io.parse("﻿Name,Email\nA,a@example.com\n")  # Excel BOM is fine
    assert headers == ["Name", "Email"] and rows[0]["Name"] == "A"


@pytest.mark.parametrize("payload", ['=HYPERLINK("http://x")', "+1+1", "-2+3", "@SUM(A1)", "\tcmd"])
def test_export_cells_cannot_run_as_formulas(payload):
    assert csv_io.safe_cell(payload) == "'" + payload
    assert csv_io.safe_cell("Normal text") == "Normal text"


def test_export_is_admin_only_csv_and_audited(client, db, owner):
    client.post(
        "/api/v1/leads",
        json={"full_name": "=CMD()", "email": "x@example.com", "company": "Evil Co"},
    )
    resp = client.get("/api/v1/leads/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    rows = list(csv.reader(io.StringIO(resp.text.lstrip("﻿"))))
    assert rows[0][0] == "full_name" and rows[1][0] == "'=CMD()"
    assert db.scalar(select(AuditLog.id).where(AuditLog.action == "leads.exported"))


def test_member_cannot_export(client, db, owner):
    from app.models import OrganizationMember, User
    from app.services.auth import hash_password

    u = User(email="m@example.com", full_name="M", password_hash=hash_password(PW))
    db.add(u)
    db.flush()
    db.add(
        OrganizationMember(
            organization_id=uuid.UUID(owner["organization_id"]), user_id=u.id, role="member"
        )
    )
    db.flush()
    client.cookies.clear()
    client.post("/api/v1/auth/login", json={"email": "m@example.com", "password": PW})
    assert client.get("/api/v1/leads/export").status_code == 403


# ---------------------------------------------------------------- duplicates


def make(client, name, company, email=None):
    return client.post(
        "/api/v1/leads", json={"full_name": name, "company": company, "email": email}
    ).json()


def test_scan_finds_similar_pairs_but_ignores_strangers(client, owner):
    make(client, "Amira Hassan", "Cedar & Pine Bakery", "amira@example.com")
    make(client, "Amira Hasan", "Cedar and Pine Bakery", "a.hassan@example.com")
    make(client, "Tomas Rivera", "Rivera Auto Care", "tomas@example.com")
    assert client.post("/api/v1/duplicates/scan").json()["added"] == 1
    pairs = client.get("/api/v1/duplicates").json()
    assert len(pairs) == 1
    assert {lead["full_name"] for lead in pairs[0]["leads"]} == {"Amira Hassan", "Amira Hasan"}
    assert client.post("/api/v1/duplicates/scan").json()["added"] == 0  # not suggested twice


def test_merge_moves_history_and_archives_the_other(client, db, owner):
    a = make(client, "Amira Hassan", "Cedar & Pine Bakery", "amira@example.com")
    b = make(client, "Amira Hasan", "Cedar and Pine Bakery", None)
    client.post(f"/api/v1/leads/{b['id']}/notes", json={"body": "Called her yesterday."})
    client.post("/api/v1/duplicates/scan")
    pair = client.get("/api/v1/duplicates").json()[0]
    resp = client.post(f"/api/v1/duplicates/{pair['id']}/merge", json={"keep_lead_id": a["id"]})
    assert resp.status_code == 200
    notes = client.get(f"/api/v1/leads/{a['id']}/notes").json()
    assert [n["body"] for n in notes] == ["Called her yesterday."]
    assert db.get(Lead, uuid.UUID(b["id"])).archived_at is not None
    assert client.get("/api/v1/duplicates").json() == []
    again = client.post(f"/api/v1/duplicates/{pair['id']}/merge", json={"keep_lead_id": a["id"]})
    assert again.status_code == 409


def test_dismiss_keeps_both_leads(client, db, owner):
    make(client, "Amira Hassan", "Cedar & Pine Bakery", "amira@example.com")
    make(client, "Amira Hasan", "Cedar and Pine Bakery", "other@example.com")
    client.post("/api/v1/duplicates/scan")
    pair = client.get("/api/v1/duplicates").json()[0]
    assert client.post(f"/api/v1/duplicates/{pair['id']}/dismiss").status_code == 204
    assert org_count(db, owner) == 2
    assert client.post("/api/v1/duplicates/scan").json()["added"] == 0


def test_scan_never_merges_by_itself(client, db, owner):
    make(client, "Amira Hassan", "Cedar & Pine Bakery", "amira@example.com")
    make(client, "Amira Hasan", "Cedar and Pine Bakery", "a2@example.com")
    client.post("/api/v1/duplicates/scan")
    assert org_count(db, owner) == 2
    active = db.scalar(select(func.count()).select_from(Lead).where(Lead.archived_at.is_(None)))
    assert active >= 2
