"""Authentication routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response

from app.core.config import settings
from app.core.deps import CSRFProtected, CurrentUser, DbSession
from app.core.security import clear_auth_cookies, decode_token, set_auth_cookies
from app.schemas.auth import (
    AuthResponse,
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    SessionUser,
)
from app.schemas.common import MessageResponse
from app.services import auth_service

router = APIRouter(prefix="/api/auth", tags=["Auth"])


def _session_user(user) -> SessionUser:
    return SessionUser(
        id=user.id,
        name=user.name,
        email=user.email,
        phone=user.phone,
        role=user.role,
        wallet_address=user.wallet_address,
        is_active=user.is_active,
        created_at=user.created_at,
        kyc_status=user.kyc_status,
        is_kyc_verified=user.is_kyc_verified,
    )


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest, response: Response, db: DbSession) -> AuthResponse:
    """Create a CREATOR or CONTRIBUTOR account. Admins are provisioned separately."""
    user = auth_service.register(
        db,
        name=payload.name,
        email=str(payload.email),
        password=payload.password,
        role=str(payload.role),
        phone=payload.phone,
        wallet_address=payload.wallet_address,
    )
    db.commit()
    db.refresh(user)
    access, refresh = auth_service.issue_tokens(user)
    csrf = set_auth_cookies(response, access, refresh)
    return AuthResponse(user=_session_user(user), csrf_token=csrf, message="Account created.")


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest, response: Response, db: DbSession) -> AuthResponse:
    user = auth_service.authenticate(db, str(payload.email), payload.password)
    db.commit()
    db.refresh(user)
    access, refresh = auth_service.issue_tokens(user)
    csrf = set_auth_cookies(response, access, refresh)
    return AuthResponse(user=_session_user(user), csrf_token=csrf)


@router.post("/logout", response_model=MessageResponse)
def logout(response: Response) -> MessageResponse:
    clear_auth_cookies(response)
    return MessageResponse(message="Signed out.")


@router.get("/me", response_model=SessionUser)
def me(user: CurrentUser) -> SessionUser:
    return _session_user(user)


@router.post("/refresh", response_model=AuthResponse)
def refresh_session(request: Request, response: Response, db: DbSession) -> AuthResponse:
    """Exchange a valid refresh cookie for a new access token."""
    token = request.cookies.get(settings.refresh_cookie_name) or ""
    payload = decode_token(token, expected_type="refresh")
    user = auth_service.get_active_user(db, int(payload["sub"]))
    access, refresh = auth_service.issue_tokens(user)
    csrf = set_auth_cookies(response, access, refresh)
    return AuthResponse(user=_session_user(user), csrf_token=csrf, message="Session refreshed.")


@router.post("/change-password", response_model=MessageResponse, dependencies=[CSRFProtected])
def change_password(
    payload: ChangePasswordRequest, user: CurrentUser, db: DbSession
) -> MessageResponse:
    auth_service.change_password(db, user, payload.current_password, payload.new_password)
    db.commit()
    return MessageResponse(message="Password updated.")
