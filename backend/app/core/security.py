"""Password hashing, JWT issuance/verification, HMAC helpers, cookie handling."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import bcrypt
import jwt
from fastapi import Response

from app.core.config import settings
from app.core.errors import AuthenticationError, ValidationError

TokenType = Literal["access", "refresh"]

# bcrypt truncates at 72 bytes; reject longer rather than silently ignore the tail.
_MAX_PASSWORD_BYTES = 72


# --------------------------------------------------------------------------
# Passwords
# --------------------------------------------------------------------------
def hash_password(password: str) -> str:
    validate_password_strength(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def validate_password_strength(password: str) -> None:
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long.")
    if len(password.encode("utf-8")) > _MAX_PASSWORD_BYTES:
        raise ValidationError("Password must be at most 72 bytes long.")
    if not any(c.isalpha() for c in password):
        raise ValidationError("Password must contain at least one letter.")
    if not any(c.isdigit() for c in password):
        raise ValidationError("Password must contain at least one number.")


# --------------------------------------------------------------------------
# JWT
# --------------------------------------------------------------------------
def create_token(
    subject: str | int,
    token_type: TokenType = "access",
    extra_claims: dict[str, Any] | None = None,
) -> str:
    now = datetime.now(timezone.utc)
    lifetime = (
        timedelta(minutes=settings.access_token_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_days)
    )
    payload: dict[str, Any] = {
        "sub": str(subject),
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + lifetime).timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str, expected_type: TokenType | None = None) -> dict[str, Any]:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationError("Session expired. Please sign in again.") from exc
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid authentication token.") from exc
    if expected_type and payload.get("type") != expected_type:
        raise AuthenticationError("Invalid authentication token.")
    return payload


# --------------------------------------------------------------------------
# HMAC / hashing helpers
# --------------------------------------------------------------------------
def hmac_sha256_hex(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a or "", b or "")


def salted_hash(value: str) -> str:
    """Salted SHA-256 used for on-chain references.

    Payment ids and voter identities are never written to a public chain in the
    clear; only this one-way, salted digest is.
    """
    digest = hashlib.sha256(f"{settings.chain_hash_salt}:{value}".encode("utf-8")).hexdigest()
    return "0x" + digest


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


# --------------------------------------------------------------------------
# Cookies
# --------------------------------------------------------------------------
def _cookie_kwargs(max_age: int, http_only: bool = True) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "max_age": max_age,
        "httponly": http_only,
        "secure": settings.cookie_secure,
        "samesite": settings.cookie_samesite,
        "path": "/",
    }
    if settings.cookie_domain:
        kwargs["domain"] = settings.cookie_domain
    return kwargs


def set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> str:
    """Set HTTP-only auth cookies plus a readable CSRF token, return the token."""
    response.set_cookie(
        settings.access_cookie_name,
        access_token,
        **_cookie_kwargs(settings.access_token_minutes * 60),
    )
    response.set_cookie(
        settings.refresh_cookie_name,
        refresh_token,
        **_cookie_kwargs(settings.refresh_token_days * 24 * 3600),
    )
    csrf = new_csrf_token()
    # Readable by JS on purpose: double-submit CSRF pattern.
    response.set_cookie(
        settings.csrf_cookie_name,
        csrf,
        **_cookie_kwargs(settings.access_token_minutes * 60, http_only=False),
    )
    return csrf


def clear_auth_cookies(response: Response) -> None:
    for name in (
        settings.access_cookie_name,
        settings.refresh_cookie_name,
        settings.csrf_cookie_name,
    ):
        response.delete_cookie(name, path="/", domain=settings.cookie_domain or None)
