"""Replyline backend entry point.

Run (from backend/):  .venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000
"""

import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1 import api_router
from app.core.config import get_settings
from app.core.db import check_database, get_session_factory
from app.core.errors import install_error_handlers
from app.core.logging import configure_logging, request_id_var
from app.services.outbox import OutboxWorker

logger = logging.getLogger("replyline")
REQUEST_ID_HEADER = "X-Request-ID"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    worker = None
    if settings.outbox_dispatch_enabled:
        worker = OutboxWorker(get_session_factory(), settings)
        worker.start()
    app.state.outbox = worker
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Replyline API", version="0.0.1", lifespan=lifespan)
    app.state.outbox = None
    install_error_handlers(app)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "X-Form-Key", "Idempotency-Key", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next) -> Response:
        incoming = request.headers.get(REQUEST_ID_HEADER, "")
        # Accept a caller's id only if it is short and plain; otherwise make one.
        rid = incoming if 0 < len(incoming) <= 64 and incoming.isprintable() else uuid.uuid4().hex
        token = request_id_var.set(rid)
        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers[REQUEST_ID_HEADER] = rid
        logger.info(
            "request",
            extra={
                "path": request.url.path,
                "method": request.method,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - start) * 1000, 1),
            },
        )
        return response

    @app.get("/health", tags=["health"])
    def health() -> dict:
        """Liveness: the process is up. Does not touch the database."""
        return {"status": "ok"}

    @app.get("/ready", tags=["health"])
    def ready() -> JSONResponse:
        """Readiness: dependencies the API needs are reachable."""
        db_ok, db_detail = check_database()
        body = {"status": "ready" if db_ok else "not_ready", "checks": {"database": db_detail}}
        return JSONResponse(body, status_code=200 if db_ok else 503)

    app.include_router(api_router)
    return app


app = create_app()
