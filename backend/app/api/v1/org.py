"""Organization, team and CRM settings. Reads for every member; changes for admins (owners for
role changes that touch ownership)."""

import re
import uuid
from datetime import datetime
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from sqlalchemy import func, select

from app.api.deps import AdminDep, DbSession, UserDep, csrf_protect
from app.models import LeadSource, Organization, OrganizationMember, PipelineStage, Service, User
from app.repositories.tenant import get_owned, scoped

router = APIRouter(tags=["organization"], dependencies=[Depends(csrf_protect)])
_TIMEZONES = available_timezones()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


# ---------------------------------------------------------------- organization / business profile


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    timezone: str
    default_country: str
    currency: str
    public_form_key: str
    response_time_line: str | None
    reply_target_minutes: int | None


class OrgPatch(Strict):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    timezone: str | None = None
    default_country: str | None = Field(default=None, min_length=2, max_length=2)
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    response_time_line: str | None = Field(default=None, max_length=200)
    reply_target_minutes: int | None = Field(default=None, ge=5, le=10080)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, v: str | None) -> str | None:
        if v is not None and v not in _TIMEZONES:
            raise ValueError("Unknown time zone. Use a name like Asia/Karachi.")
        return v


def _org_out(org: Organization) -> OrgOut:
    s = org.settings or {}
    return OrgOut(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        timezone=org.timezone,
        default_country=org.default_country,
        currency=org.currency,
        public_form_key=org.public_form_key,
        response_time_line=s.get("response_time_line"),
        reply_target_minutes=s.get("reply_target_minutes"),
    )


@router.get("/org", response_model=OrgOut)
def get_org(user: UserDep, db: DbSession) -> OrgOut:
    return _org_out(db.get(Organization, user.organization_id))


@router.patch("/org", response_model=OrgOut)
def patch_org(body: OrgPatch, user: AdminDep, db: DbSession) -> OrgOut:
    org = db.get(Organization, user.organization_id)
    data = body.model_dump(exclude_unset=True)
    for key in ("name", "timezone", "currency"):
        if key in data:
            setattr(org, key, data[key])
    if "default_country" in data:
        org.default_country = data["default_country"].upper()
    settings = dict(org.settings or {})
    for key in ("response_time_line", "reply_target_minutes"):
        if key in data:
            settings[key] = data[key]
    org.settings = settings
    db.commit()
    return _org_out(org)


# ---------------------------------------------------------------- team


class MemberOut(BaseModel):
    id: str
    user_id: str
    full_name: str
    email: str
    role: str
    last_login_at: datetime | None


class MemberPatch(Strict):
    role: str = Field(pattern=r"^(owner|admin|member)$")


def _owners(db, org_id: uuid.UUID) -> int:
    return db.scalar(
        select(func.count()).where(
            OrganizationMember.organization_id == org_id, OrganizationMember.role == "owner"
        )
    )


@router.get("/org/members", response_model=list[MemberOut])
def list_members(user: UserDep, db: DbSession) -> list[MemberOut]:
    rows = db.execute(
        select(OrganizationMember, User)
        .join(User, User.id == OrganizationMember.user_id)
        .where(OrganizationMember.organization_id == user.organization_id)
        .order_by(User.full_name)
    ).all()
    return [
        MemberOut(
            id=str(m.id),
            user_id=str(u.id),
            full_name=u.full_name,
            email=u.email,
            role=m.role,
            last_login_at=u.last_login_at,
        )
        for m, u in rows
    ]


@router.patch("/org/members/{member_id}", response_model=MemberOut)
def change_role(
    member_id: uuid.UUID, body: MemberPatch, user: AdminDep, db: DbSession
) -> MemberOut:
    member = get_owned(db, OrganizationMember, member_id, user.organization_id)
    touches_owner = "owner" in (member.role, body.role)
    if touches_owner and user.role != "owner":
        raise HTTPException(403, "Only an owner can grant or remove the owner role.")
    if member.role == "owner" and body.role != "owner" and _owners(db, user.organization_id) <= 1:
        raise HTTPException(409, "An organization needs at least one owner.")
    member.role = body.role
    db.commit()
    u = db.get(User, member.user_id)
    return MemberOut(
        id=str(member.id),
        user_id=str(u.id),
        full_name=u.full_name,
        email=u.email,
        role=member.role,
        last_login_at=u.last_login_at,
    )


@router.delete("/org/members/{member_id}", status_code=204)
def remove_member(member_id: uuid.UUID, user: AdminDep, db: DbSession) -> None:
    member = get_owned(db, OrganizationMember, member_id, user.organization_id)
    if member.role == "owner" and user.role != "owner":
        raise HTTPException(403, "Only an owner can remove an owner.")
    if member.role == "owner" and _owners(db, user.organization_id) <= 1:
        raise HTTPException(409, "An organization needs at least one owner.")
    db.delete(member)
    db.commit()


# ---------------------------------------------------------------- pipeline stages


class StageOut(BaseModel):
    id: str
    key: str
    label: str
    position: int
    category: str
    is_system: bool


class StageIn(Strict):
    label: str = Field(min_length=1, max_length=60)
    category: str = Field(default="open", pattern=r"^(open|won|lost)$")


class StagePatch(Strict):
    label: str | None = Field(default=None, min_length=1, max_length=60)
    position: int | None = Field(default=None, ge=0, le=100)


def _stage_out(s: PipelineStage) -> StageOut:
    return StageOut(
        id=str(s.id),
        key=s.key,
        label=s.label,
        position=s.position,
        category=s.category,
        is_system=s.is_system,
    )


@router.get("/settings/pipeline", response_model=list[StageOut])
def list_stages(user: UserDep, db: DbSession) -> list[StageOut]:
    rows = db.scalars(
        scoped(PipelineStage, user.organization_id).order_by(PipelineStage.position)
    ).all()
    return [_stage_out(s) for s in rows]


@router.post("/settings/pipeline", response_model=StageOut, status_code=201)
def add_stage(body: StageIn, user: AdminDep, db: DbSession) -> StageOut:
    key = re.sub(r"[^a-z0-9]+", "_", body.label.lower()).strip("_")[:30] or "stage"
    taken = set(
        db.scalars(
            select(PipelineStage.key).where(PipelineStage.organization_id == user.organization_id)
        )
    )
    base, n = key, 1
    while key in taken:
        n += 1
        key = f"{base}_{n}"
    last = db.scalar(
        select(func.max(PipelineStage.position)).where(
            PipelineStage.organization_id == user.organization_id
        )
    )
    stage = PipelineStage(
        organization_id=user.organization_id,
        key=key,
        label=body.label,
        category=body.category,
        position=(last or 0) + 1,
        is_system=False,
    )
    db.add(stage)
    db.commit()
    return _stage_out(stage)


@router.patch("/settings/pipeline/{stage_id}", response_model=StageOut)
def edit_stage(stage_id: uuid.UUID, body: StagePatch, user: AdminDep, db: DbSession) -> StageOut:
    stage = get_owned(db, PipelineStage, stage_id, user.organization_id)
    if body.label is not None:
        stage.label = body.label  # the key stays stable even for system stages
    if body.position is not None:
        stage.position = body.position
    db.commit()
    return _stage_out(stage)


@router.delete("/settings/pipeline/{stage_id}", status_code=204)
def delete_stage(stage_id: uuid.UUID, user: AdminDep, db: DbSession) -> None:
    from app.models import Lead

    stage = get_owned(db, PipelineStage, stage_id, user.organization_id)
    if stage.is_system:
        raise HTTPException(409, "Built-in stages can be renamed but not deleted.")
    in_use = db.scalar(
        select(func.count()).where(
            Lead.organization_id == user.organization_id, Lead.stage_id == stage.id
        )
    )
    if in_use:
        raise HTTPException(409, f"{in_use} lead(s) are in this stage. Move them first.")
    db.delete(stage)
    db.commit()


# ---------------------------------------------------------------- lead sources


class SourceOut(BaseModel):
    id: str
    key: str
    label: str
    kind: str


@router.get("/settings/sources", response_model=list[SourceOut])
def list_sources(user: UserDep, db: DbSession) -> list[SourceOut]:
    rows = db.scalars(scoped(LeadSource, user.organization_id).order_by(LeadSource.label)).all()
    return [SourceOut(id=str(s.id), key=s.key, label=s.label, kind=s.kind) for s in rows]


# ---------------------------------------------------------------- service catalog


class ServiceOut(BaseModel):
    id: str
    name: str
    description: str | None
    keywords: list[str]
    price_min_minor: int | None
    price_max_minor: int | None
    currency: str
    active: bool


class ServiceIn(Strict):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    keywords: list[str] = Field(default_factory=list, max_length=30)
    price_min_minor: int | None = Field(default=None, ge=0)
    price_max_minor: int | None = Field(default=None, ge=0)
    active: bool = True

    @model_validator(mode="after")
    def range_ok(self) -> "ServiceIn":
        lo, hi = self.price_min_minor, self.price_max_minor
        if lo is not None and hi is not None and lo > hi:
            raise ValueError("The lowest price must not be above the highest price.")
        self.keywords = [k.strip().lower()[:60] for k in self.keywords if k.strip()]
        return self


class ServicePatch(ServiceIn):
    name: str | None = Field(default=None, min_length=1, max_length=120)  # type: ignore[assignment]


def _service_out(s: Service) -> ServiceOut:
    return ServiceOut(
        id=str(s.id),
        name=s.name,
        description=s.description,
        keywords=list(s.keywords or []),
        price_min_minor=s.price_min_minor,
        price_max_minor=s.price_max_minor,
        currency=s.currency,
        active=s.active,
    )


@router.get("/settings/services", response_model=list[ServiceOut])
def list_services(user: UserDep, db: DbSession) -> list[ServiceOut]:
    rows = db.scalars(scoped(Service, user.organization_id).order_by(Service.name)).all()
    return [_service_out(s) for s in rows]


@router.post("/settings/services", response_model=ServiceOut, status_code=201)
def add_service(body: ServiceIn, user: AdminDep, db: DbSession) -> ServiceOut:
    if db.scalar(
        scoped(Service, user.organization_id).where(func.lower(Service.name) == body.name.lower())
    ):
        raise HTTPException(409, "A service with this name already exists.")
    org = db.get(Organization, user.organization_id)
    svc = Service(organization_id=org.id, currency=org.currency, **body.model_dump())
    db.add(svc)
    db.commit()
    return _service_out(svc)


@router.patch("/settings/services/{service_id}", response_model=ServiceOut)
def edit_service(
    service_id: uuid.UUID, body: ServicePatch, user: AdminDep, db: DbSession
) -> ServiceOut:
    svc = get_owned(db, Service, service_id, user.organization_id)
    data = body.model_dump(exclude_unset=True)
    lo = data.get("price_min_minor", svc.price_min_minor)
    hi = data.get("price_max_minor", svc.price_max_minor)
    if lo is not None and hi is not None and lo > hi:
        raise HTTPException(422, "The lowest price must not be above the highest price.")
    for key, value in data.items():
        setattr(svc, key, value)
    db.commit()
    return _service_out(svc)
