"""Timeline entries and audit records. Payloads hold ids and labels, never message text."""

import uuid

from sqlalchemy.orm import Session

from app.core.logging import request_id_var
from app.models import AuditLog, LeadActivity


def record(
    db: Session,
    org_id: uuid.UUID,
    lead_id: uuid.UUID,
    type_: str,
    actor_type: str = "system",
    actor_id: uuid.UUID | None = None,
    **payload,
) -> None:
    db.add(
        LeadActivity(
            organization_id=org_id,
            lead_id=lead_id,
            type=type_,
            actor_type=actor_type,
            actor_id=actor_id,
            payload=payload,
        )
    )


def audit(
    db: Session,
    org_id: uuid.UUID,
    actor_user_id: uuid.UUID | None,
    action: str,
    entity: str,
    entity_id: uuid.UUID | None = None,
    ip: str | None = None,
    **summary,
) -> None:
    db.add(
        AuditLog(
            organization_id=org_id,
            actor_user_id=actor_user_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            summary=summary,
            ip=ip,
            request_id=request_id_var.get(),
        )
    )
