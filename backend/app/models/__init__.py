"""All models, imported here so Alembic sees every table."""

from app.models.activity import AuditLog, LeadActivity, LeadNote
from app.models.base import Base
from app.models.crm import LeadSource, PipelineStage, Service
from app.models.duplicates import DuplicateCandidate
from app.models.leads import Lead, LeadInquiry
from app.models.reliability import IdempotencyKey, OutboxEvent, WorkflowExecution
from app.models.tenancy import ApiKey, Organization, OrganizationMember, RefreshToken, User

__all__ = [
    "ApiKey",
    "AuditLog",
    "Base",
    "DuplicateCandidate",
    "IdempotencyKey",
    "Lead",
    "LeadActivity",
    "LeadInquiry",
    "LeadNote",
    "LeadSource",
    "Organization",
    "OrganizationMember",
    "OutboxEvent",
    "PipelineStage",
    "RefreshToken",
    "Service",
    "User",
    "WorkflowExecution",
]
