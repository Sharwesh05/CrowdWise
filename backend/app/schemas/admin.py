"""Admin review and dashboard schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.campaign import AIAnalysisResponse, ApplicationResponse, CampaignSummary
from app.schemas.common import ORMModel


class ApproveRequest(BaseModel):
    notes: str | None = Field(default=None, max_length=2000)


class RejectRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)


class RequestChangesRequest(BaseModel):
    notes: str = Field(min_length=10, max_length=2000)


class ReviewCreator(BaseModel):
    id: int
    name: str
    email: str
    phone: str | None = None
    kyc_status: str
    kyc_verified_at: datetime | None = None
    kyc_reference: str | None = None
    campaigns_created: int = 0


class DocumentResponse(ORMModel):
    id: int
    file_name: str
    mime_type: str
    size: int
    created_at: datetime
    url: str | None = None


class AdminCampaignReview(BaseModel):
    """Everything an admin needs on one screen to make a real decision."""

    campaign: CampaignSummary
    description: str
    problem_statement: str
    proposed_solution: str
    expected_impact: str | None = None
    creator: ReviewCreator
    application: ApplicationResponse | None = None
    application_fee_paid: bool
    application_fee_webhook_verified: bool
    analysis: AIAnalysisResponse | None = None
    risk_indicators: list[str] = Field(default_factory=list)
    recommended_questions: list[str] = Field(default_factory=list)
    documents: list[DocumentResponse] = Field(default_factory=list)
    review_notes: str | None = None
    allowed_actions: list[str] = Field(default_factory=list)


class AdminDashboard(BaseModel):
    total_campaigns: int
    pending_reviews: int
    active_campaigns: int
    completed_campaigns: int
    rejected_campaigns: int
    governance_campaigns: int
    total_contributions_amount: Decimal
    total_contributions_count: int
    total_contributors: int
    total_creators: int
    kyc_summary: dict[str, int]
    failed_payments: int
    unverified_payments: int
    blockchain_pending: int
    blockchain_failed: int
    demo_mode: bool


class AuditLogResponse(ORMModel):
    id: int
    actor_id: int | None = None
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    # validation_alias reads the ORM column; serialization_alias fixes the wire
    # name, because FastAPI serializes response models with by_alias=True.
    metadata: dict[str, Any] | None = Field(
        default=None, validation_alias="audit_metadata", serialization_alias="metadata"
    )
    created_at: datetime


class DemoControlRequest(BaseModel):
    """DEMO CONTROL — admin-only, and only when DEMO_MODE is enabled."""

    action: str = Field(
        description=(
            "complete_kyc | run_analysis | simulate_deadline | mark_target_missed | "
            "open_governance | close_governance | retry_blockchain | refresh_insights | "
            "process_refunds"
        )
    )
    campaign_public_id: str | None = None
    user_email: str | None = None


class DemoControlResponse(BaseModel):
    action: str
    status: str
    message: str
    detail: dict[str, Any] | None = None
