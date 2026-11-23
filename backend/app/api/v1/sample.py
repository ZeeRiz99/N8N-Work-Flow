"""Load or remove fictional sample leads for the caller's organization (development only)."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from app.api.deps import AdminDep, DbSession, UserDep, csrf_protect
from app.core.config import get_settings
from app.models import Lead, Organization
from app.services import sample_data

router = APIRouter(tags=["sample-data"], dependencies=[Depends(csrf_protect)])


class SampleIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = Field(default=40, ge=1, le=200)


def _dev_only() -> None:
    if get_settings().app_env != "development":
        raise HTTPException(403, "Sample data is only available in development.")


def _sample_count(db, org_id) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.organization_id == org_id, Lead.custom_fields["sample"].astext == "true")
        )
        or 0
    )


@router.get("/org/sample-data")
def sample_status(user: UserDep, db: DbSession) -> dict:
    return {
        "available": get_settings().app_env == "development",
        "sample_leads": _sample_count(db, user.organization_id),
    }


@router.post("/org/sample-data", status_code=201)
def load_sample(body: SampleIn, user: AdminDep, db: DbSession) -> dict:
    """Uses the offline AI for scoring, so loading never spends the Gemini quota."""
    _dev_only()
    org = db.get(Organization, user.organization_id)
    out = sample_data.load(db, org, body.count, author_id=user.user_id)
    return {**out, "sample_leads": _sample_count(db, org.id)}


@router.delete("/org/sample-data")
def clear_sample(user: AdminDep, db: DbSession) -> dict:
    _dev_only()
    return {"removed": sample_data.clear(db, user.organization_id)}
