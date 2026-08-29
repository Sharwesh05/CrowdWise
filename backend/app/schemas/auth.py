"""Auth and user schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.enums import UserRole
from app.schemas.common import ORMModel


class RegisterRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    role: UserRole = UserRole.CONTRIBUTOR
    phone: str | None = Field(default=None, max_length=20)
    wallet_address: str | None = Field(default=None, max_length=64)

    @field_validator("role")
    @classmethod
    def _no_self_service_admin(cls, value: UserRole) -> UserRole:
        if value == UserRole.ADMIN:
            raise ValueError("Admin accounts cannot be self-registered.")
        return value

    @field_validator("phone")
    @classmethod
    def _phone(cls, value: str | None) -> str | None:
        if not value:
            return None
        cleaned = value.strip()
        if not cleaned.replace("+", "").replace("-", "").replace(" ", "").isdigit():
            raise ValueError("Phone number contains invalid characters.")
        return cleaned


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=72)


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=72)
    new_password: str = Field(min_length=8, max_length=72)


class UserResponse(ORMModel):
    id: int
    name: str
    email: EmailStr
    phone: str | None = None
    role: str
    wallet_address: str | None = None
    is_active: bool
    created_at: datetime


class SessionUser(UserResponse):
    """The `/me` projection: adds derived state the UI gates on."""

    kyc_status: str
    is_kyc_verified: bool


class AuthResponse(BaseModel):
    user: SessionUser
    csrf_token: str
    message: str = "Signed in."
