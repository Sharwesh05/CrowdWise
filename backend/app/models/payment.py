"""Payment and contribution models.

A `Payment` is a gateway fact. A `Contribution` is a domain fact that exists only
after that payment has been verified server-side. Keeping them apart is what makes
"raised_amount only moves after verification" structurally true.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UTCDateTime, utcnow
from app.core.enums import ContributionStatus, PaymentStatus, PaymentType

if TYPE_CHECKING:  # pragma: no cover
    from app.models.campaign import Campaign
    from app.models.chain import BlockchainTransaction
    from app.models.user import User


class Payment(Base, TimestampMixin):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="SET NULL"), index=True, nullable=True
    )
    payment_type: Mapped[str] = mapped_column(String(30), index=True, nullable=False)
    razorpay_order_id: Mapped[str] = mapped_column(
        String(80), unique=True, index=True, nullable=False
    )
    razorpay_payment_id: Mapped[str | None] = mapped_column(
        String(80), unique=True, index=True, nullable=True
    )
    razorpay_signature: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="INR", nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default=PaymentStatus.CREATED, index=True, nullable=False
    )
    # True only once a signed Razorpay webhook has confirmed this payment.
    webhook_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider: Mapped[str] = mapped_column(String(20), default="demo", nullable=False)
    notes: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="payments")
    campaign: Mapped["Campaign | None"] = relationship(back_populates="payments")
    contribution: Mapped["Contribution | None"] = relationship(
        back_populates="payment", uselist=False
    )

    __table_args__ = (
        Index("ix_payments_type_status", "payment_type", "status"),
        Index("ix_payments_user_created", "user_id", "created_at"),
    )

    @property
    def is_application_fee(self) -> bool:
        return self.payment_type == PaymentType.APPLICATION_FEE


class Contribution(Base):
    __tablename__ = "contributions"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contributor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    # One contribution per payment: the DB, not application logic, is what makes
    # duplicate webhook deliveries harmless.
    payment_id: Mapped[int] = mapped_column(
        ForeignKey("payments.id", ondelete="RESTRICT"), unique=True, nullable=False
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default=ContributionStatus.PAYMENT_VERIFIED, index=True, nullable=False
    )
    blockchain_tx: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # use_alter: contributions and blockchain_transactions reference each other,
    # so this constraint is created after both tables exist.
    blockchain_record_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "blockchain_transactions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_contribution_blockchain_record",
        ),
        nullable=True,
    )
    blockchain_attempts: Mapped[int] = mapped_column(default=0, nullable=False)
    blockchain_error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_anonymous: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="contributions")
    contributor: Mapped["User"] = relationship(back_populates="contributions")
    payment: Mapped["Payment"] = relationship(back_populates="contribution")
    blockchain_record: Mapped["BlockchainTransaction | None"] = relationship(
        foreign_keys=[blockchain_record_id], post_update=True
    )

    __table_args__ = (
        UniqueConstraint("payment_id", name="uq_contribution_payment"),
        Index("ix_contributions_campaign_created", "campaign_id", "created_at"),
        Index("ix_contributions_contributor_created", "contributor_id", "created_at"),
    )


class WebhookEvent(Base):
    """Idempotency ledger for inbound gateway webhooks.

    The unique `event_id` is the single mechanism that makes redelivery a no-op.
    """

    __tablename__ = "webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String(20), default="razorpay", nullable=False)
    event_id: Mapped[str] = mapped_column(String(120), unique=True, index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payment_reference: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="PROCESSED", nullable=False)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )
