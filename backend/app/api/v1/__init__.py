from fastapi import APIRouter

from app.api.v1 import internal, leads, public

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(public.router)
api_router.include_router(internal.router)
api_router.include_router(leads.router)
