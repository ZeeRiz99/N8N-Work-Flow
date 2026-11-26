"""All models, imported here so Alembic sees every table."""

from app.models.activity import AuditLog, LeadActivity, LeadNote
from app.models.analysis import LeadAnalysis, LeadScore, ReportSnapshot, ScoringConfig
from app.models.base import Base
from app.models.communication import (
    CommunicationDraft,
    CommunicationLog,
    FollowUp,
    Suppression,
)
from app.models.crm import LeadSource, PipelineStage, Service
from app.models.duplicates import DuplicateCandidate
from app.models.leads import Lead, LeadInquiry
from app.models.reliability import (
    IdempotencyKey,
    OutboxEvent,
    RateLimitHit,
    UsageCounter,
    WorkflowExecution,
)
from app.models.tenancy import (
    ApiKey,
    Invitation,
    Organization,
    OrganizationMember,
    RefreshToken,
    User,
)

__all__ = [
    "RateLimitHit",
    "UsageCounter",
    "ApiKey",
    "Invitation",
    "AuditLog",
    "Base",
    "DuplicateCandidate",
    "IdempotencyKey",
    "Lead",
    "LeadActivity",
    "CommunicationDraft",
    "CommunicationLog",
    "FollowUp",
    "Suppression",
    "LeadAnalysis",
    "ReportSnapshot",
    "LeadInquiry",
    "LeadNote",
    "LeadScore",
    "LeadSource",
    "Organization",
    "OrganizationMember",
    "OutboxEvent",
    "PipelineStage",
    "RefreshToken",
    "ScoringConfig",
    "Service",
    "User",
    "WorkflowExecution",
]
