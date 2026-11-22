"""Public capture: the hosted form posts here.

No login; protected by the form key, a honeypot field and a per-IP rate limit.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select

from app.api.deps import DbSession, public_form_rate_limit
from app.models import Organization
from app.schemas.public import PublicFormConfig, PublicLeadIn, PublicLeadOut
from app.services.leads import ingest_public_lead

router = APIRouter(prefix="/public", tags=["public"])

DEFAULT_TIMELINES = ["Within 1 month", "1 to 3 months", "No fixed date"]


@router.get("/forms/{org_slug}", response_model=PublicFormConfig)
def form_config(org_slug: str, db: DbSession) -> PublicFormConfig:
    org = db.scalar(select(Organization).where(Organization.slug == org_slug))
    if org is None:
        raise HTTPException(404, "Form not found.")
    s = org.settings or {}
    return PublicFormConfig(
        organization_name=org.name,
        form_key=org.public_form_key,
        services=s.get("services", []),
        budget_options=s.get("budget_options", []),
        timeline_options=s.get("timeline_options", DEFAULT_TIMELINES),
        response_time_line=s.get(
            "response_time_line", "We usually answer within one business day."
        ),
    )


@router.post(
    "/leads",
    response_model=PublicLeadOut,
    status_code=201,
    dependencies=[Depends(public_form_rate_limit)],
)
def submit_lead(
    payload: PublicLeadIn,
    request: Request,
    db: DbSession,
    x_form_key: Annotated[str | None, Header()] = None,
    idempotency_key: Annotated[str | None, Header()] = None,
) -> PublicLeadOut:
    # The organization comes from the public key, never from anything else the client sends.
    org = db.scalar(select(Organization).where(Organization.public_form_key == (x_form_key or "")))
    if org is None:
        raise HTTPException(401, "Unknown form.")

    if payload.nickname:
        # Honeypot filled: answer like a success so the bot learns nothing; store nothing.
        return PublicLeadOut(reference=str(uuid.uuid4()))

    key = idempotency_key[:200] if idempotency_key else None
    result = ingest_public_lead(db, org, payload, idempotency_key=key)
    worker = getattr(request.app.state, "outbox", None)
    if worker is not None and not result.replayed:
        worker.nudge()
    return PublicLeadOut(reference=str(result.inquiry_id))
