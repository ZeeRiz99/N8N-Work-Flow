"""Tenant scoping (D8). Every read and write of a tenant table goes through these helpers, so
organization_id is never forgotten. A record from another organization looks exactly like a
missing one (404), so ids cannot be probed across organizations."""

import uuid

from fastapi import HTTPException
from sqlalchemy import Select, select
from sqlalchemy.orm import Session


def scoped[T](model: type[T], org_id: uuid.UUID) -> Select[tuple[T]]:
    """SELECT * FROM model WHERE organization_id = :org_id, to extend with more filters."""
    return select(model).where(model.organization_id == org_id)  # type: ignore[attr-defined]


def get_owned[T](db: Session, model: type[T], obj_id: uuid.UUID, org_id: uuid.UUID) -> T:
    obj = db.scalar(scoped(model, org_id).where(model.id == obj_id))  # type: ignore[attr-defined]
    if obj is None:
        raise HTTPException(404, f"{model.__name__} not found.")
    return obj
