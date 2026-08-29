"""Governance vote model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime, utcnow

if TYPE_CHECKING:  # pragma: no cover
    from app.models.campaign import Campaign
    from app.models.user import User


class Vote(Base):
    """One vote by one eligible contributor in one governance round.

    Duplicate prevention is a database constraint, not an application check:
    (campaign_id, contributor_id, round) is unique.
    """

    __tablename__ = "votes"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contributor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    governance_round: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    choice: Mapped[str] = mapped_column(String(20), nullable=False)
    weight: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=Decimal("1.00"), nullable=False)
    blockchain_tx: Mapped[str | None] = mapped_column(String(80), nullable=True)
    blockchain_status: Mapped[str | None] = mapped_column(String(30), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="votes")
    contributor: Mapped["User"] = relationship(back_populates="votes")

    __table_args__ = (
        UniqueConstraint(
            "campaign_id", "contributor_id", "governance_round", name="uq_vote_once_per_round"
        ),
        Index("ix_votes_campaign_choice", "campaign_id", "choice"),
    )
