"""One error envelope for every failure: {"error": {code, message, details, request_id}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_var

CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    422: "validation_error",
    429: "rate_limited",
}


def error_response(status: int, message: str, details=None) -> JSONResponse:
    """Build the standard error envelope directly (for handlers that must return, not raise)."""
    return _envelope(status, message, details)


def _envelope(status: int, message: str, details=None) -> JSONResponse:
    body = {
        "error": {
            "code": CODES.get(status, "error"),
            "message": message,
            "details": details,
            "request_id": request_id_var.get(),
        }
    }
    return JSONResponse(body, status_code=status)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return _envelope(exc.status_code, str(exc.detail))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        # Field locations and messages only; never echo the submitted values back.
        details = [
            {"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]}
            for e in exc.errors()
        ]
        return _envelope(422, "Some fields are missing or invalid.", details)
