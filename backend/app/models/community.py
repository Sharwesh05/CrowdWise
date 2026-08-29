"""Feedback, sentiment, AI campaign analysis and AI community insights."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    JSON,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, UTCDateTime, utcnow
from app.core.enums import AnalysisStatus, AnalysisType, Sentiment

if TYPE_CHECKING:  # pragma: no cover
    from app.models.campaign import Campaign
    from app.models.user import User


class AIAnalysis(Base):
    """Structured campaign analysis produced by the LLM (or its fallback).

    The model never defines its own structure: output is parsed and validated
    against a schema, and a failure degrades to a deterministic fallback marked
    DEGRADED rather than corrupting the record.
    """

    __tablename__ = "ai_analysis"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    type: Mapped[str] = mapped_column(String(20), default=AnalysisType.CAMPAIGN, nullable=False)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="mock", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=AnalysisStatus.COMPLETED, nullable=False
    )

    feasibility_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    problem_clarity_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    impact_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    strengths: Mapped[list | None] = mapped_column(JSON, nullable=True)
    concerns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    questions_for_creator: Mapped[list | None] = mapped_column(JSON, nullable=True)
    missing_information: Mapped[list | None] = mapped_column(JSON, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    raw_result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="analyses")

    __table_args__ = (Index("ix_ai_analysis_campaign_type", "campaign_id", "type"),)

    @property
    def risk_level(self) -> str:
        score = self.risk_score or 0
        if score >= 70:
            return "High"
        if score >= 40:
            return "Medium"
        return "Low"


class Feedback(Base):
    """Community feedback on a campaign, with sentiment and aspect labels."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    contributor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(Text, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    sentiment: Mapped[str] = mapped_column(
        String(20), default=Sentiment.PENDING, index=True, nullable=False
    )
    sentiment_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    aspect: Mapped[str | None] = mapped_column(String(30), index=True, nullable=True)
    # A feedback item can legitimately touch several aspects at once.
    aspects: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sentiment_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="feedback")
    contributor: Mapped["User"] = relationship(back_populates="feedback")

    __table_args__ = (
        UniqueConstraint("campaign_id", "contributor_id", name="uq_feedback_campaign_user"),
        Index("ix_feedback_campaign_created", "campaign_id", "created_at"),
    )


class AICommunityInsight(Base):
    """Cached community intelligence: aggregates in, one LLM call out."""

    __tablename__ = "ai_community_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), index=True, nullable=False
    )
    positive_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    neutral_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    negative_percentage: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    feedback_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    top_concerns: Mapped[list | None] = mapped_column(JSON, nullable=True)
    positive_themes: Mapped[list | None] = mapped_column(JSON, nullable=True)
    aspect_distribution: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    community_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations: Mapped[list | None] = mapped_column(JSON, nullable=True)
    questions_from_community: Mapped[list | None] = mapped_column(JSON, nullable=True)
    risk_change: Mapped[str | None] = mapped_column(String(200), nullable=True)

    model: Mapped[str] = mapped_column(String(80), nullable=False)
    provider: Mapped[str] = mapped_column(String(30), default="mock", nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=AnalysisStatus.COMPLETED, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, index=True, nullable=False
    )

    campaign: Mapped["Campaign"] = relationship(back_populates="insights")
