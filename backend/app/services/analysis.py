"""Analyze a lead (P3: FakeAIProvider).

Idempotent: analyzing a lead that is already done returns the stored result.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import fake_provider
from app.models import Lead, LeadInquiry


def analyze_lead(db: Session, org_id: uuid.UUID, lead_id: uuid.UUID) -> dict | None:
    lead = db.scalar(select(Lead).where(Lead.id == lead_id, Lead.organization_id == org_id))
    if lead is None:
        return None
    if lead.ai_status == "done" and lead.score is not None:
        return _result(lead, "Already analyzed (fake).")

    latest = db.scalar(
        select(LeadInquiry)
        .where(LeadInquiry.lead_id == lead.id, LeadInquiry.organization_id == org_id)
        .order_by(LeadInquiry.received_at.desc())
        .limit(1)
    )
    lead.ai_status = "processing"
    db.flush()
    result = fake_provider.analyze(
        latest.message if latest else "",
        has_phone=bool(lead.phone_raw),
        has_company=bool(lead.company),
        form_fields=latest.form_fields if latest else {},
    )
    lead.score = result.score
    lead.priority = result.band
    lead.score_source = "fake"
    lead.score_provisional = False
    lead.ai_status = "done"
    db.commit()
    return _result(lead, result.summary)


def _result(lead: Lead, summary: str) -> dict:
    return {
        "lead_id": str(lead.id),
        "ai_status": lead.ai_status,
        "score": lead.score,
        "band": lead.priority,
        "score_source": lead.score_source,
        "summary": summary,
    }
