"""Auth endpoints. Tokens live only in httpOnly cookies, never in the response body (D7)."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from app.api.deps import (
    ACCESS_COOKIE,
    REFRESH_COOKIE,
    DbSession,
    UserDep,
    csrf_protect,
    login_rate_limit,
)
from app.core.config import get_settings
from app.core.errors import error_response
from app.models import Organization, User
from app.schemas.public import EMAIL_RE
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"], dependencies=[Depends(csrf_protect)])
REFRESH_PATH = "/api/v1/auth"


class LoginIn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class RegisterIn(LoginIn):
    organization_name: str = Field(min_length=2, max_length=200)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def email_shape(cls, v: str) -> str:
        if not EMAIL_RE.match(v):
            raise ValueError("Enter a valid email address.")
        return v

    @field_validator("password")
    @classmethod
    def strong_enough(cls, v: str) -> str:
        problems = auth_service.password_problems(v)
        if problems:
            raise ValueError(" ".join(problems))
        return v


class MeOut(BaseModel):
    user_id: str
    email: str
    full_name: str
    role: str
    organization_id: str
    organization_name: str
    organization_slug: str


def _set_cookies(response: Response, session: auth_service.Session_) -> None:
    s = get_settings()
    response.set_cookie(
        ACCESS_COOKIE,
        session.access_token,
        max_age=s.access_token_ttl_minutes * 60,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        REFRESH_COOKIE,
        session.refresh_token,
        max_age=s.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=s.cookie_secure,
        samesite="lax",
        path=REFRESH_PATH,  # sent only to /api/v1/auth/*, never to the rest of the API
    )


def _clear_cookies(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path=REFRESH_PATH)


def _me(db, user_id, org_id, role, email, full_name) -> MeOut:
    org = db.get(Organization, org_id)
    return MeOut(
        user_id=str(user_id),
        email=email,
        full_name=full_name,
        role=role,
        organization_id=str(org_id),
        organization_name=org.name,
        organization_slug=org.slug,
    )


@router.post("/register", response_model=MeOut, status_code=201)
def register(body: RegisterIn, response: Response, db: DbSession) -> MeOut:
    if not get_settings().allow_registration:
        raise HTTPException(403, "Sign-up is closed. Ask an admin for an invitation.")
    try:
        session = auth_service.register(
            db, get_settings(), body.organization_name, body.full_name, body.email, body.password
        )
    except auth_service.AuthError as exc:
        raise HTTPException(409, str(exc)) from exc
    _set_cookies(response, session)
    return _me(
        db, session.user_id, session.organization_id, session.role, body.email, body.full_name
    )


@router.post("/login", response_model=MeOut, dependencies=[Depends(login_rate_limit)])
def login(body: LoginIn, response: Response, db: DbSession) -> MeOut:
    try:
        session = auth_service.login(db, get_settings(), body.email, body.password)
    except auth_service.AuthError as exc:
        raise HTTPException(401, str(exc)) from exc
    _set_cookies(response, session)
    user = db.get(User, session.user_id)
    return _me(db, user.id, session.organization_id, session.role, user.email, user.full_name)


@router.post("/refresh", status_code=204)
def refresh(request: Request, response: Response, db: DbSession) -> Response:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(401, "Please log in.")
    try:
        session = auth_service.refresh(db, get_settings(), raw)
    except auth_service.AuthError as exc:
        # Return (not raise) so the cookie deletions travel with the 401.
        failed = error_response(401, str(exc))
        _clear_cookies(failed)
        return failed
    _set_cookies(response, session)
    response.status_code = 204
    return response


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, db: DbSession) -> Response:
    auth_service.logout(db, request.cookies.get(REFRESH_COOKIE))
    _clear_cookies(response)
    response.status_code = 204
    return response


@router.get("/me", response_model=MeOut)
def me(user: UserDep, db: DbSession) -> MeOut:
    org = db.scalar(select(Organization).where(Organization.id == user.organization_id))
    return MeOut(
        user_id=str(user.user_id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organization_id=str(org.id),
        organization_name=org.name,
        organization_slug=org.slug,
    )
