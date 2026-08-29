"""User and KYC models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UTCDateTime
from app.core.enums import KYCStatus, UserRole

if TYPE_CHECKING:  # pragma: no cover
    from app.models.campaign import Campaign
    from app.models.community import Feedback
    from app.models.governance import Vote
    from app.models.payment import Contribution, Payment


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), default=UserRole.CONTRIBUTOR, nullable=False)
    # Optional self-custodied wallet used as the on-chain contributor reference.
    wallet_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    kyc_verifications: Mapped[list["KYCVerification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", order_by="KYCVerification.id"
    )
    campaigns: Mapped[list["Campaign"]] = relationship(
        back_populates="creator", foreign_keys="Campaign.creator_id"
    )
    payments: Mapped[list["Payment"]] = relationship(back_populates="user")
    contributions: Mapped[list["Contribution"]] = relationship(back_populates="contributor")
    feedback: Mapped[list["Feedback"]] = relationship(back_populates="contributor")
    votes: Mapped[list["Vote"]] = relationship(back_populates="contributor")

    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)

    @property
    def latest_kyc(self) -> "KYCVerification | None":
        return self.kyc_verifications[-1] if self.kyc_verifications else None

    @property
    def kyc_status(self) -> str:
        latest = self.latest_kyc
        return latest.status if latest else KYCStatus.NOT_STARTED

    @property
    def is_kyc_verified(self) -> bool:
        return self.kyc_status == KYCStatus.VERIFIED


class KYCVerification(Base, TimestampMixin):
    """Demo KYC record.

    In DEMO_MODE the `verification_metadata` column holds only fake/test values.
    Nothing in this table is ever written to the blockchain or sent to an LLM.
    """

    __tablename__ = "kyc_verifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    provider: Mapped[str] = mapped_column(String(40), default="demo", nullable=False)
    verification_reference: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default=KYCStatus.SUBMITTED, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # `metadata` is reserved by SQLAlchemy's Declarative API, hence the prefix.
    verification_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="kyc_verifications")

    __table_args__ = (Index("ix_kyc_user_status", "user_id", "status"),)
