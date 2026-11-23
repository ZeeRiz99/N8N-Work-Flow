"""CSV import/export and duplicate review."""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.api.deps import AdminDep, DbSession, UserDep, client_ip, csrf_protect
from app.api.v1.leads import _row, _rows_query
from app.models import Lead, Organization
from app.services import csv_io, duplicates
from app.services.activity import audit

router = APIRouter(tags=["data"], dependencies=[Depends(csrf_protect)])


class ImportIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    csv: str = Field(min_length=1, max_length=csv_io.MAX_BYTES + 1024)
    mapping: dict[str, str] | None = None
    dry_run: bool = True


@router.post("/leads/import")
def import_leads(body: ImportIn, user: UserDep, db: DbSession, request: Request) -> dict:
    """Preview with dry_run=true (the default), then send the same file with dry_run=false."""
    org = db.get(Organization, user.organization_id)
    try:
        report = csv_io.run_import(
            db, org, user.user_id, body.csv, body.mapping, body.dry_run, client_ip(request)
        )
    except csv_io.CsvRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    return {
        "dry_run": report.dry_run,
        "columns": report.columns,
        "mapping": report.mapping,
        "total_rows": report.total_rows,
        "valid_rows": report.valid_rows,
        "would_create": report.would_create,
        "would_merge": report.would_merge,
        "created": report.created,
        "merged": report.merged,
        "errors": [e.__dict__ for e in report.errors[:200]],
        "error_count": len(report.errors),
    }


EXPORT_COLUMNS = [
    "full_name",
    "email",
    "phone",
    "company",
    "website",
    "stage",
    "source",
    "priority",
    "score",
    "assigned_to",
    "do_not_contact",
    "created_at",
]


@router.get("/leads/export")
def export_leads(user: AdminDep, db: DbSession, request: Request) -> Response:
    """Admin-only, audited. Cells that could run as spreadsheet formulas are neutralized."""
    rows = db.execute(
        _rows_query(user.organization_id)
        .where(Lead.archived_at.is_(None))
        .order_by(Lead.created_at)
    ).all()
    flat = []
    for r in rows:
        d = _row(*r)
        flat.append(
            {**d, "stage": d["stage"]["label"], "assigned_to": (d["assigned_to"] or {}).get("name")}
        )
    audit(
        db,
        user.organization_id,
        user.user_id,
        "leads.exported",
        "lead",
        ip=client_ip(request),
        rows=len(flat),
    )
    db.commit()
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    return Response(
        content=csv_io.to_csv(flat, EXPORT_COLUMNS),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="leads-{stamp}.csv"'},
    )


# ---------------------------------------------------------------- duplicates


class MergeIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    keep_lead_id: uuid.UUID


@router.post("/duplicates/scan")
def scan_duplicates(user: AdminDep, db: DbSession) -> dict:
    return {"added": duplicates.scan(db, user.organization_id)}


@router.get("/duplicates")
def list_duplicates(user: UserDep, db: DbSession) -> list[dict]:
    items = []
    for c in duplicates.open_candidates(db, user.organization_id):
        pair = {
            str(lead.id): lead
            for lead in db.scalars(
                select(Lead).where(
                    Lead.id.in_([c.lead_a_id, c.lead_b_id]),
                    Lead.organization_id == user.organization_id,
                )
            )
        }
        a, b = pair.get(str(c.lead_a_id)), pair.get(str(c.lead_b_id))
        if not a or not b:
            continue
        items.append(
            {
                "id": str(c.id),
                "confidence": c.confidence,
                "reasons": c.reasons,
                "leads": [
                    {
                        "id": str(x.id),
                        "full_name": x.full_name,
                        "company": x.company,
                        "email": x.email,
                        "phone": x.phone_raw,
                        "created_at": x.created_at.isoformat(),
                    }
                    for x in (a, b)
                ],
            }
        )
    return items


@router.post("/duplicates/{candidate_id}/merge")
def merge_duplicate(candidate_id: uuid.UUID, body: MergeIn, user: UserDep, db: DbSession) -> dict:
    keep = duplicates.merge(db, user.organization_id, candidate_id, body.keep_lead_id, user.user_id)
    return {"kept_lead_id": str(keep.id)}


@router.post("/duplicates/{candidate_id}/dismiss", status_code=204)
def dismiss_duplicate(candidate_id: uuid.UUID, user: UserDep, db: DbSession) -> None:
    duplicates.dismiss(db, user.organization_id, candidate_id, user.user_id)
