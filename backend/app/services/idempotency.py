"""Idempotency claims for internal calls: the first caller with a key wins; repeats are told so."""

import uuid

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import IdempotencyKey


def claim_once(db: Session, org_id: uuid.UUID, scope: str, key: str | None, response: dict) -> bool:
    """Record (org, scope, key). Returns True for the first claim, False for any repeat.

    Without a key there is nothing to deduplicate on, so the call counts as a first delivery.
    Uses INSERT ... ON CONFLICT DO NOTHING, so two parallel deliveries cannot both win.
    """
    if not key:
        return True
    stmt = (
        insert(IdempotencyKey)
        .values(organization_id=org_id, scope=scope, key=key[:200], response=response)
        .on_conflict_do_nothing(index_elements=["organization_id", "scope", "key"])
        .returning(IdempotencyKey.id)
    )
    inserted = db.scalar(stmt)
    db.commit()
    return inserted is not None
