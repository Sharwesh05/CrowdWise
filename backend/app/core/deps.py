"""FastAPI dependencies: current user, role guards, CSRF."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import get_db
from app.core.enums import UserRole
from app.core.errors import AuthenticationError, PermissionDeniedError
from app.core.security import constant_time_equals, decode_token
from app.models.user import User
from app.services import auth_service

DbSession = Annotated[Session, Depends(get_db)]

# Requests that change state must carry the double-submit CSRF token; safe
# methods and the signed webhook endpoint are exempt.
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_CSRF_EXEMPT_PATHS = ("/api/webhooks/",)


def _token_from_request(request: Request) -> str | None:
    # An explicit Authorization header wins over the ambient cookie: a caller that
    # names a token means that token, even when a browser session is also present.
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get(settings.access_cookie_name)


def get_current_user(request: Request, db: DbSession) -> User:
    token = _token_from_request(request)
    if not token:
        raise AuthenticationError("Authentication required.")
    payload = decode_token(token, expected_type="access")
    try:
        user_id = int(payload["sub"])
    except (KeyError, TypeError, ValueError) as exc:
        raise AuthenticationError("Invalid authentication token.") from exc
    user = auth_service.get_active_user(db, user_id)
    request.state.user_id = user.id
    return user


def get_optional_user(request: Request, db: DbSession) -> User | None:
    """For public pages that render differently when signed in."""
    try:
        return get_current_user(request, db)
    except AuthenticationError:
        return None


CurrentUser = Annotated[User, Depends(get_current_user)]
OptionalUser = Annotated[User | None, Depends(get_optional_user)]


def require_role(*roles: UserRole) -> Callable[..., User]:
    allowed = {str(role) for role in roles}

    def _dependency(user: CurrentUser) -> User:
        if user.role not in allowed:
            raise PermissionDeniedError(
                "Your account does not have access to this resource.",
                details={"required": sorted(allowed), "actual": user.role},
            )
        return user

    return _dependency


CreatorUser = Annotated[User, Depends(require_role(UserRole.CREATOR))]
ContributorUser = Annotated[User, Depends(require_role(UserRole.CONTRIBUTOR))]
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]
# Admins can act anywhere a creator can, which keeps demo controls workable.
CreatorOrAdmin = Annotated[User, Depends(require_role(UserRole.CREATOR, UserRole.ADMIN))]


def verify_csrf(request: Request) -> None:
    """Double-submit CSRF check for cookie-authenticated state changes.

    Skipped when the caller authenticates with a Bearer token: that request
    cannot be forged by a browser riding the user's cookies.
    """
    if request.method not in _UNSAFE_METHODS:
        return
    if any(request.url.path.startswith(path) for path in _CSRF_EXEMPT_PATHS):
        return
    if request.headers.get("authorization", "").lower().startswith("bearer "):
        return
    cookie_token = request.cookies.get(settings.csrf_cookie_name)
    if not cookie_token:
        return  # not a cookie session
    header_token = request.headers.get("x-csrf-token", "")
    if not constant_time_equals(cookie_token, header_token):
        raise PermissionDeniedError("CSRF token missing or invalid.")


CSRFProtected = Depends(verify_csrf)


def require_demo_mode() -> None:
    if not settings.demo_mode:
        raise PermissionDeniedError("Demo controls are disabled outside DEMO_MODE.")
