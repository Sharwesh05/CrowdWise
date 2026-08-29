"""Blockchain transaction records and platform audit logs."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    BigInteger,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime, utcnow
from app.core.enums import BlockchainTxStatus

if TYPE_CHECKING:  # pragma: no cover
    from app.models.campaign import Campaign


class BlockchainTransaction(Base):
    """A record anchored on chain.

    Only non-sensitive references are ever anchored: a campaign reference, a
    salted payment-reference hash, an amount, a timestamp and an opaque voter
    reference. Personal data never appears here or on chain.
    """

    __tablename__ = "blockchain_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contribution_id: Mapped[int | None] = mapped_column(
        ForeignKey("contributions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    vote_id: Mapped[int | None] = mapped_column(
        ForeignKey("votes.id", ondelete="SET NULL"), index=True, nullable=True
    )
    record_type: Mapped[str] = mapped_column(String(40), index=True, nullable=False)
    tx_hash: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    network: Mapped[str] = mapped_column(String(40), nullable=False)
    contract_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default=BlockchainTxStatus.PENDING, index=True, nullable=False
    )
    block_number: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    gas_used: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)

    campaign: Mapped["Campaign"] = relationship(back_populates="blockchain_transactions")

    __table_args__ = (Index("ix_chain_campaign_type", "campaign_id", "record_type"),)


class AuditLog(Base):
    """Platform-wide, actor-oriented record of every material action."""

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True, nullable=True
    )
    action: Mapped[str] = mapped_column(String(60), index=True, nullable=False)
    entity_type: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    audit_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )

    __table_args__ = (Index("ix_audit_action_created", "action", "created_at"),)
