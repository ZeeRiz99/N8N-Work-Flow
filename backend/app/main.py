"""Replyline backend entry point.

Run (from backend/):  .venv\\Scripts\\python -m uvicorn app.main:app --reload --port 8000
"""

import logging
import time
import uuid

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.db import check_database
from app.core.logging import configure_logging, request_id_var

logger = logging.getLogger("replyline")
REQUEST_ID_HEADER = "X-Request-ID"


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    app = FastAPI(title="Replyline API", version="0.0.1")

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

    return app


app = create_app()
