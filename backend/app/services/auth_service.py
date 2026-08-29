"""Authentication service."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import EventType, UserRole
from app.core.errors import AuthenticationError, ConflictError, ValidationError
from app.core.logging import get_logger
from app.core.security import create_token, hash_password, verify_password
from app.models.user import User
from app.services import audit_service

logger = get_logger(__name__)


def get_by_email(db: Session, email: str) -> User | None:
    return db.execute(
        select(User).where(func.lower(User.email) == email.strip().lower())
    ).scalars().first()


def register(
    db: Session,
    *,
    name: str,
    email: str,
    password: str,
    role: str,
    phone: str | None = None,
    wallet_address: str | None = None,
) -> User:
    normalized = email.strip().lower()
    if role not in (UserRole.CREATOR, UserRole.CONTRIBUTOR):
        # Admins are provisioned deliberately (seed/ops), never by self-signup.
        raise ValidationError("Accounts can be registered as CREATOR or CONTRIBUTOR.")
    if get_by_email(db, normalized):
        raise ConflictError("An account with this email already exists.")
    if len(name.strip()) < 2:
        raise ValidationError("Please provide your name.")

    user = User(
        name=name.strip(),
        email=normalized,
        phone=(phone or "").strip() or None,
        password_hash=hash_password(password),  # validates strength, then bcrypts
        role=role,
        wallet_address=(wallet_address or "").strip() or None,
        is_active=True,
    )
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("An account with this email already exists.") from exc

    audit_service.record_audit(
        db,
        action=(
            EventType.CREATOR_REGISTERED
            if role == UserRole.CREATOR
            else EventType.CONTRIBUTOR_REGISTERED
        ),
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        metadata={"role": role},
    )
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = get_by_email(db, email)
    # Same message and comparable work for both failure modes, so the response
    # does not disclose whether an account exists.
    if user is None:
        hash_password("dummy-password-1")
        raise AuthenticationError("Incorrect email or password.")
    if not verify_password(password, user.password_hash):
        raise AuthenticationError("Incorrect email or password.")
    if not user.is_active:
        raise AuthenticationError("This account has been deactivated.")

    user.last_login_at = utcnow()
    db.flush()
    audit_service.record_audit(
        db,
        action=EventType.USER_LOGGED_IN,
        actor_id=user.id,
        entity_type="user",
        entity_id=user.id,
        metadata={"role": user.role},
    )
    return user


def issue_tokens(user: User) -> tuple[str, str]:
    claims = {"role": user.role, "email": user.email}
    return (
        create_token(user.id, "access", claims),
        create_token(user.id, "refresh", {"role": user.role}),
    )


def get_active_user(db: Session, user_id: int) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Account not found or inactive.")
    return user


def change_password(db: Session, user: User, current_password: str, new_password: str) -> User:
    if not verify_password(current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect.")
    user.password_hash = hash_password(new_password)
    db.flush()
    audit_service.record_audit(
        db, action="PASSWORD_CHANGED", actor_id=user.id, entity_type="user", entity_id=user.id
    )
    return user
