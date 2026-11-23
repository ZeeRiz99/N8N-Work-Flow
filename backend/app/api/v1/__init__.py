from fastapi import APIRouter

from app.api.v1 import (
    ai,
    analytics,
    auth,
    automation,
    data,
    drafts,
    followups,
    internal,
    leads,
    org,
    public,
    sample,
)

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(org.router)
api_router.include_router(public.router)
api_router.include_router(internal.router)
# data before leads: /leads/import and /leads/export must win over /leads/{lead_id}.
api_router.include_router(data.router)
api_router.include_router(leads.router)
api_router.include_router(ai.router)
api_router.include_router(sample.router)
api_router.include_router(drafts.router)
api_router.include_router(automation.router)
api_router.include_router(analytics.router)
api_router.include_router(followups.router)
