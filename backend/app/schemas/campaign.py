"""Campaign, KYC, AI and QR schemas.

The public projection deliberately omits creator contact details, payment
identifiers and KYC data: `PublicCampaign` is the only campaign shape an
unauthenticated caller can ever receive.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.core.enums import CampaignCategory, OutcomeType, VotingWeightMode
from app.schemas.common import ORMModel


# --------------------------------------------------------------------------
# KYC
# --------------------------------------------------------------------------
class KYCSubmitRequest(BaseModel):
    """DEMO KYC. Test values only — never real identity documents."""

    full_name: str = Field(min_length=3, max_length=120)
    date_of_birth: str = Field(description="YYYY-MM-DD (demo value)")
    pan_number: str = Field(min_length=10, max_length=10, description="Demo PAN, e.g. ABCDE1234F")
    address: str = Field(min_length=10, max_length=500)
    bank_account_number: str = Field(min_length=6, max_length=24)
    bank_ifsc: str = Field(min_length=11, max_length=11)
    document_storage_key: str | None = None
    confirm_demo_data: bool = Field(
        default=True, description="Acknowledges that only test data is being submitted."
    )

    @field_validator("confirm_demo_data")
    @classmethod
    def _must_confirm(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Demo KYC requires confirming that the data is test data.")
        return value


class KYCStatusResponse(BaseModel):
    status: str
    provider: str | None = None
    reference: str | None = None
    submitted_at: datetime | None = None
    verified_at: datetime | None = None
    demo_mode: bool = True
    checks: dict[str, Any] | None = None
    notice: str = "DEMO KYC MODE — simulated verification with test data only."


# --------------------------------------------------------------------------
# Campaign write models
# --------------------------------------------------------------------------
class CampaignCreateRequest(BaseModel):
    title: str = Field(min_length=6, max_length=180)
    short_description: str = Field(min_length=20, max_length=300)
    description: str = Field(min_length=100, max_length=20000)
    problem_statement: str = Field(min_length=40, max_length=8000)
    proposed_solution: str = Field(min_length=40, max_length=8000)
    expected_impact: str | None = Field(default=None, max_length=4000)
    category: CampaignCategory = CampaignCategory.OTHER
    target_amount: Decimal = Field(gt=0, le=Decimal("1000000000"))
    minimum_contribution: Decimal = Field(default=Decimal("100"), gt=0)
    deadline: datetime
    cover_image_url: str | None = Field(default=None, max_length=500)
    outcome_type: OutcomeType = OutcomeType.CONTRIBUTOR_VOTE
    voting_weight_mode: VotingWeightMode = VotingWeightMode.ONE_PERSON_ONE_VOTE


class CampaignUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=6, max_length=180)
    short_description: str | None = Field(default=None, min_length=20, max_length=300)
    description: str | None = Field(default=None, min_length=100, max_length=20000)
    problem_statement: str | None = Field(default=None, min_length=40, max_length=8000)
    proposed_solution: str | None = Field(default=None, min_length=40, max_length=8000)
    expected_impact: str | None = Field(default=None, max_length=4000)
    category: CampaignCategory | None = None
    target_amount: Decimal | None = Field(default=None, gt=0)
    minimum_contribution: Decimal | None = Field(default=None, gt=0)
    deadline: datetime | None = None
    cover_image_url: str | None = Field(default=None, max_length=500)


# --------------------------------------------------------------------------
# AI
# --------------------------------------------------------------------------
AI_DISCLAIMER = (
    "AI analysis is provided as decision support and is not a guarantee of "
    "campaign success or legitimacy."
)


class AIAnalysisResponse(ORMModel):
    id: int
    campaign_id: int
    type: str
    model: str
    provider: str
    status: str
    feasibility_score: int | None = None
    problem_clarity_score: int | None = None
    impact_score: int | None = None
    risk_score: int | None = None
    risk_level: str | None = None
    summary: str | None = None
    strengths: list[str] = Field(default_factory=list)
    concerns: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    questions_for_creator: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    created_at: datetime
    disclaimer: str = AI_DISCLAIMER


class CommunityInsightResponse(ORMModel):
    id: int
    campaign_id: int
    positive_percentage: float
    neutral_percentage: float
    negative_percentage: float
    average_rating: float | None = None
    feedback_count: int
    top_concerns: list[str] = Field(default_factory=list)
    positive_themes: list[str] = Field(default_factory=list)
    aspect_distribution: dict[str, float] = Field(default_factory=dict)
    community_summary: str | None = None
    recommendations: list[str] = Field(default_factory=list)
    questions_from_community: list[str] = Field(default_factory=list)
    risk_change: str | None = None
    model: str
    provider: str
    status: str
    created_at: datetime
    disclaimer: str = AI_DISCLAIMER


# --------------------------------------------------------------------------
# Campaign read models
# --------------------------------------------------------------------------
class CreatorSummary(BaseModel):
    id: int
    name: str
    is_verified: bool = False


class CampaignSummary(BaseModel):
    """Card projection used in listings."""

    id: int
    public_id: str
    title: str
    slug: str
    short_description: str
    category: str
    cover_image_url: str | None = None
    target_amount: Decimal
    raised_amount: Decimal
    funding_percentage: float
    minimum_contribution: Decimal
    contributor_count: int
    deadline: datetime
    days_remaining: int
    status: str
    creator: CreatorSummary
    average_rating: float | None = None
    health_score: int | None = None
    health_label: str | None = None
    is_demo: bool = False


class HealthResponse(BaseModel):
    score: int
    label: str
    financial_score: int
    community_score: int
    ai_score: int
    signals: dict[str, Any]
    note: str = (
        "CrowdWise Campaign Health summarises observed funding, community and AI "
        "signals. It is not a prediction of financial success."
    )


class CampaignUpdateCreateRequest(BaseModel):
    title: str = Field(min_length=4, max_length=140)
    body: str = Field(min_length=20, max_length=5000)


class CampaignUpdateEditRequest(BaseModel):
    title: str | None = Field(default=None, min_length=4, max_length=140)
    body: str | None = Field(default=None, min_length=20, max_length=5000)
    is_pinned: bool | None = None


class CampaignUpdateResponse(ORMModel):
    id: int
    campaign_id: int
    title: str
    body: str
    is_pinned: bool
    author_name: str | None = None
    created_at: datetime
    updated_at: datetime | None = None


class SentimentSummary(BaseModel):
    feedback_count: int = 0
    analyzed_count: int = 0
    average_rating: float = 0.0
    positive_percentage: float = 0.0
    neutral_percentage: float = 0.0
    negative_percentage: float = 0.0
    aspect_distribution: list[dict[str, Any]] = Field(default_factory=list)
    rating_distribution: dict[int, int] = Field(default_factory=dict)


class BlockchainSummary(BaseModel):
    recorded: int = 0
    pending: int = 0
    network: str | None = None
    contract_address: str | None = None
    latest_tx_hash: str | None = None
    explorer_url: str | None = None
    simulated: bool = False


class PublicCampaign(CampaignSummary):
    """Full public campaign page payload."""

    description: str
    problem_statement: str
    proposed_solution: str
    expected_impact: str | None = None
    published_at: datetime | None = None
    governance_status: str
    governance_closes_at: datetime | None = None
    qr_url: str
    outcome_rules: dict[str, Any] | None = None
    analysis: AIAnalysisResponse | None = None
    sentiment: SentimentSummary | None = None
    # Count only, so the Updates tab can show a badge without the page
    # having to fetch the list before it is opened.
    update_count: int = 0
    insights: CommunityInsightResponse | None = None
    health: HealthResponse | None = None
    blockchain: BlockchainSummary | None = None


class CampaignEventResponse(ORMModel):
    id: int
    event_type: str
    actor_id: int | None = None
    metadata: dict[str, Any] | None = Field(
        default=None, validation_alias="event_metadata", serialization_alias="metadata"
    )
    created_at: datetime


class ApplicationResponse(ORMModel):
    id: int
    campaign_id: int
    application_fee: Decimal
    status: str
    razorpay_order_id: str | None = None
    submitted_at: datetime | None = None
    reviewed_at: datetime | None = None


class CreatorCampaign(PublicCampaign):
    """Owner view: adds application, review notes and the campaign timeline."""

    approval_status: str
    review_notes: str | None = None
    application: ApplicationResponse | None = None
    qr_token: str | None = None
    events: list[CampaignEventResponse] = Field(default_factory=list)
    allowed_transitions: list[str] = Field(default_factory=list)


class QRResponse(BaseModel):
    public_id: str
    campaign_url: str
    qr_token: str | None = None
    qr_image_data_uri: str
    download_url: str
