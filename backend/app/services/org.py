"""Organization setup: the defaults every new organization starts with."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import LeadSource, PipelineStage, Service
from app.models.crm import DEFAULT_SOURCES, DEFAULT_STAGES

# Demo catalog (fictional business). Prices in minor units (cents) per D17.
DEMO_SERVICES = [
    (
        "Website Development",
        ["website", "web site", "online ordering", "landing page", "shop"],
        150_000,
        500_000,
    ),
    ("Booking System", ["booking", "appointments", "reservations", "schedule"], 100_000, 400_000),
    ("AI Chatbot", ["chatbot", "chat bot", "ai assistant", "faq bot"], 200_000, 800_000),
    (
        "Automation Setup",
        ["automation", "n8n", "zapier", "workflow", "integration"],
        50_000,
        300_000,
    ),
]


def provision_defaults(db: Session, org_id: uuid.UUID) -> None:
    """Create the default pipeline stages and lead sources if the organization has none."""
    if db.scalar(select(PipelineStage.id).where(PipelineStage.organization_id == org_id).limit(1)):
        return
    for pos, (key, label, category) in enumerate(DEFAULT_STAGES):
        db.add(
            PipelineStage(
                organization_id=org_id,
                key=key,
                label=label,
                position=pos,
                category=category,
                is_system=True,
            )
        )
    for key, label, kind in DEFAULT_SOURCES:
        db.add(LeadSource(organization_id=org_id, key=key, label=label, kind=kind))
    db.flush()


def provision_demo_services(db: Session, org_id: uuid.UUID, currency: str = "USD") -> int:
    existing = set(db.scalars(select(Service.name).where(Service.organization_id == org_id)))
    added = 0
    for name, keywords, lo, hi in DEMO_SERVICES:
        if name in existing:
            continue
        db.add(
            Service(
                organization_id=org_id,
                name=name,
                keywords=keywords,
                price_min_minor=lo,
                price_max_minor=hi,
                currency=currency,
            )
        )
        added += 1
    db.flush()
    return added


def stage_id(db: Session, org_id: uuid.UUID, key: str) -> uuid.UUID | None:
    return db.scalar(
        select(PipelineStage.id).where(
            PipelineStage.organization_id == org_id, PipelineStage.key == key
        )
    )


def source_id(db: Session, org_id: uuid.UUID, key: str) -> uuid.UUID | None:
    return db.scalar(
        select(LeadSource.id).where(LeadSource.organization_id == org_id, LeadSource.key == key)
    )
