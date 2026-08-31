"""Campaign, application, documents, outcome configuration and events."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, TimestampMixin, UTCDateTime, utcnow
from app.core.enums import (
    ApplicationStatus,
    ApprovalStatus,
    CampaignCategory,
    CampaignStatus,
    GovernanceStatus,
    OutcomeType,
    VotingWeightMode,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.models.chain import BlockchainTransaction
    from app.models.community import (
        AIAnalysis,
        AICommunityInsight,
        CampaignUpdate,
        Feedback,
    )
    from app.models.governance import Vote
    from app.models.payment import Contribution, Payment
    from app.models.user import User


class Campaign(Base, TimestampMixin):
    __tablename__ = "campaigns"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable external identifier (e.g. CMP-124): used in public URLs, in the QR
    # payload and as the on-chain campaign reference. Internal ids stay private.
    public_id: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(180), nullable=False)
    slug: Mapped[str] = mapped_column(String(200), unique=True, index=True, nullable=False)
    short_description: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_solution: Mapped[str] = mapped_column(Text, nullable=False)
    expected_impact: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str] = mapped_column(
        String(30), default=CampaignCategory.OTHER, index=True, nullable=False
    )

    target_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    raised_amount: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("0.00"), nullable=False
    )
    minimum_contribution: Mapped[Decimal] = mapped_column(
        Numeric(14, 2), default=Decimal("100.00"), nullable=False
    )
    contributor_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    deadline: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), default=CampaignStatus.DRAFT, index=True, nullable=False
    )
    approval_status: Mapped[str] = mapped_column(
        String(30), default=ApprovalStatus.NOT_SUBMITTED, nullable=False
    )
    governance_status: Mapped[str] = mapped_column(
        String(20), default=GovernanceStatus.NOT_APPLICABLE, nullable=False
    )
    governance_closes_at: Mapped[datetime | None] = mapped_column(
        UTCDateTime, nullable=True
    )

    qr_token: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    review_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_demo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    creator: Mapped["User"] = relationship(back_populates="campaigns", foreign_keys=[creator_id])
    application: Mapped["CampaignApplication | None"] = relationship(
        back_populates="campaign", uselist=False, cascade="all, delete-orphan"
    )
    documents: Mapped[list["CampaignDocument"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    outcome: Mapped["CampaignOutcome | None"] = relationship(
        back_populates="campaign", uselist=False, cascade="all, delete-orphan"
    )
    events: Mapped[list["CampaignEvent"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan", order_by="CampaignEvent.id"
    )
    analyses: Mapped[list["AIAnalysis"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    insights: Mapped[list["AICommunityInsight"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    feedback: Mapped[list["Feedback"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    updates: Mapped[list["CampaignUpdate"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    contributions: Mapped[list["Contribution"]] = relationship(back_populates="campaign")
    payments: Mapped[list["Payment"]] = relationship(back_populates="campaign")
    votes: Mapped[list["Vote"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )
    blockchain_transactions: Mapped[list["BlockchainTransaction"]] = relationship(
        back_populates="campaign", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("ix_campaigns_status_approval", "status", "approval_status"),
        Index("ix_campaigns_category_status", "category", "status"),
        Index("ix_campaigns_deadline", "deadline"),
    )

    @property
    def funding_percentage(self) -> float:
        target = float(self.target_amount or 0)
        if target <= 0:
            return 0.0
        return round(min(float(self.raised_amount or 0) / target * 100, 999.9), 2)

    @property
    def target_met(self) -> bool:
        return Decimal(self.raised_amount or 0) >= Decimal(self.target_amount or 0)


class CampaignApplication(Base, TimestampMixin):
    """The creator's application to run a campaign, gated by the ₹500 fee."""

    __tablename__ = "campaign_applications"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    creator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), index=True, nullable=False
    )
    application_fee: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    razorpay_order_id: Mapped[str | None] = mapped_column(String(80), index=True, nullable=True)
    razorpay_payment_id: Mapped[str | None] = mapped_column(String(80), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), default=ApplicationStatus.DRAFT, index=True, nullable=False
    )
    submitted_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="application")


class CampaignDocument(Base):
    """Uploaded supporting document.

    Only the randomised storage key is persisted — never the user-supplied
    filename as a path component.
    """

    __tablename__ = "campaign_documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="documents")


class CampaignOutcome(Base):
    """Predefined rules for what happens when the campaign ends.

    Locked before contributions begin: `locked_at` is set at publication and the
    service layer refuses edits afterwards.
    """

    __tablename__ = "campaign_outcomes"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    outcome_type: Mapped[str] = mapped_column(
        String(30), default=OutcomeType.CONTRIBUTOR_VOTE, nullable=False
    )
    threshold: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), default=Decimal("50.00"))
    voting_weight_mode: Mapped[str] = mapped_column(
        String(30), default=VotingWeightMode.ONE_PERSON_ONE_VOTE, nullable=False
    )
    configuration: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    selected_outcome: Mapped[str | None] = mapped_column(String(30), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="outcome")


class CampaignEvent(Base):
    """The campaign's public timeline (distinct from platform-wide audit logs)."""

    __tablename__ = "campaign_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    event_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime,
        default=utcnow,
        index=True,
        nullable=False,
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="events")
