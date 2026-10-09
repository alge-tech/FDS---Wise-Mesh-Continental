"""Passwords, the session cookie, role guards, member scoping and the CSRF guard."""

from dataclasses import dataclass
from datetime import timedelta
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.core.enums import MEMBER_ROLES, STAFF_ROLES, Role
from app.core.errors import Forbidden, Unauthenticated
from app.core.ids import utcnow

_hasher = PasswordHasher()  # argon2id with the library's recommended parameters
JWT_ALG = "HS256"
CSRF_HEADER = "x-requested-with"
CSRF_VALUE = "mesh-web"


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


@dataclass(frozen=True)
class Principal:
    user_id: UUID
    role: Role
    member_id: UUID | None
    email: str

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF_ROLES


@dataclass(frozen=True)
class MemberContext:
    """The caller's member. Member endpoints never take a member ID; it comes from here."""

    principal: Principal
    member_id: UUID

    @property
    def user_id(self) -> UUID:
        return self.principal.user_id

    @property
    def role(self) -> Role:
        return self.principal.role


def issue_session(response: Response, user_id: UUID) -> None:
    settings = get_settings()
    now = utcnow()
    token = jwt.encode(
        {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=settings.session_hours)},
        settings.jwt_secret,
        algorithm=JWT_ALG,
    )
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_hours * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        path="/",
    )


def clear_session(response: Response) -> None:
    response.delete_cookie(get_settings().cookie_name, path="/")


def _user_id_from_cookie(request: Request) -> UUID:
    settings = get_settings()
    token = request.cookies.get(settings.cookie_name)
    if not token:
        raise Unauthenticated()
    try:
        claims = jwt.decode(token, settings.jwt_secret, algorithms=[JWT_ALG])
        return UUID(claims["sub"])
    except (jwt.PyJWTError, KeyError, ValueError) as exc:
        raise Unauthenticated("Your session has expired. Log in again.") from exc


def current_principal(request: Request, session: Session = Depends(get_session)) -> Principal:
    from app.modules.members.models import User  # local import: models import core

    user = session.get(User, _user_id_from_cookie(request))
    if user is None:
        raise Unauthenticated()
    return Principal(user.id, Role(user.role), user.member_id, user.email)


def require_roles(*roles: Role):  # type: ignore[no-untyped-def]
    allowed = frozenset(roles)

    def dependency(principal: Principal = Depends(current_principal)) -> Principal:
        if principal.role not in allowed:
            raise Forbidden()
        return principal

    return dependency


def member_context(*roles: Role):  # type: ignore[no-untyped-def]
    """Dependency for member endpoints: a member role, optionally narrowed to `roles`."""
    allowed = frozenset(roles) if roles else MEMBER_ROLES

    def dependency(principal: Principal = Depends(current_principal)) -> MemberContext:
        if principal.member_id is None or principal.role not in MEMBER_ROLES:
            raise Forbidden("This page is for member businesses.")
        if principal.role not in allowed:
            raise Forbidden()
        return MemberContext(principal, principal.member_id)

    return dependency


class CsrfGuard:
    """State-changing requests need X-Requested-With: mesh-web and, if sent, a matching Origin."""

    SAFE = frozenset({"GET", "HEAD", "OPTIONS"})

    def __init__(self, app) -> None:  # type: ignore[no-untyped-def]
        self.app = app

    async def __call__(self, scope, receive, send) -> None:  # type: ignore[no-untyped-def]
        if scope["type"] == "http" and scope["method"] not in self.SAFE:
            headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers", [])}
            origin = headers.get("origin")
            allowed = get_settings().allowed_origins
            if headers.get(CSRF_HEADER) != CSRF_VALUE or (origin and origin not in allowed):
                from fastapi.responses import JSONResponse

                from app.core.errors import envelope

                response = JSONResponse(
                    envelope("FORBIDDEN", "Missing or invalid CSRF header."), status_code=403
                )
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)
