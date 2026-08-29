"""Payment, contribution, feedback and governance schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.core.enums import FeedbackAspect, Sentiment, VoteChoice
from app.schemas.common import ORMModel


# --------------------------------------------------------------------------
# Payments
# --------------------------------------------------------------------------
class OrderResponse(BaseModel):
    """Everything the checkout sheet needs. No secret is ever included."""

    payment_id: int
    order_id: str
    amount: Decimal
    amount_paise: int
    currency: str
    key_id: str
    provider: str
    payment_type: str
    campaign_public_id: str | None = None
    demo_mode: bool = False
    notice: str | None = None


class ContributeRequest(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("10000000"))
    is_anonymous: bool = False


class VerifyPaymentRequest(BaseModel):
    """A client-side claim. Accepted only if the signature verifies server-side."""

    razorpay_order_id: str = Field(min_length=6, max_length=80)
    razorpay_payment_id: str = Field(min_length=6, max_length=80)
    razorpay_signature: str = Field(min_length=16, max_length=255)


class PaymentResponse(ORMModel):
    id: int
    payment_type: str
    razorpay_order_id: str
    razorpay_payment_id: str | None = None
    amount: Decimal
    currency: str
    status: str
    webhook_verified: bool
    provider: str
    created_at: datetime
    verified_at: datetime | None = None


class BlockchainRecord(ORMModel):
    id: int
    record_type: str
    tx_hash: str
    network: str
    contract_address: str | None = None
    status: str
    block_number: int | None = None
    gas_used: int | None = None
    created_at: datetime
    explorer_url: str | None = None
    simulated: bool = False


class ContributionResponse(ORMModel):
    id: int
    campaign_id: int
    campaign_public_id: str | None = None
    campaign_title: str | None = None
    amount: Decimal
    status: str
    blockchain_tx: str | None = None
    blockchain_attempts: int = 0
    created_at: datetime
    payment: PaymentResponse | None = None
    blockchain_record: BlockchainRecord | None = None


class ContributionPublic(BaseModel):
    """Contributor-facing list on a public campaign page — no identities."""

    id: int
    amount: Decimal
    contributor_name: str
    status: str
    blockchain_tx: str | None = None
    created_at: datetime


class VerificationProgress(BaseModel):
    """Drives the honest multi-step payment screen in the UI."""

    payment_received: bool = False
    payment_verified: bool = False
    webhook_verified: bool = False
    contribution_recorded: bool = False
    blockchain_status: str = "PENDING"
    blockchain_tx: str | None = None
    contribution_id: int | None = None
    message: str = ""


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------
class FeedbackCreateRequest(BaseModel):
    text: str = Field(min_length=10, max_length=2000)
    rating: int = Field(ge=1, le=5)


class FeedbackResponse(ORMModel):
    id: int
    campaign_id: int
    text: str
    rating: int
    sentiment: str
    sentiment_score: float | None = None
    aspect: str | None = None
    aspects: list[str] = Field(default_factory=list)
    aspect_label: str | None = None
    author_name: str | None = None
    created_at: datetime


class FeedbackFilter(BaseModel):
    sentiment: Sentiment | None = None
    aspect: FeedbackAspect | None = None


# --------------------------------------------------------------------------
# Governance
# --------------------------------------------------------------------------
class VoteRequest(BaseModel):
    choice: VoteChoice


class VoteResponse(ORMModel):
    id: int
    campaign_id: int
    choice: str
    weight: Decimal
    blockchain_tx: str | None = None
    blockchain_status: str | None = None
    created_at: datetime
    campaign_title: str | None = None
    campaign_public_id: str | None = None


class GovernanceResponse(BaseModel):
    campaign_public_id: str
    campaign_title: str
    campaign_status: str
    status: str
    is_open: bool
    closes_at: str | None = None
    total_eligible_voters: int
    votes_cast: int
    participation_percentage: float
    results: dict[str, dict[str, Any]]
    leading_choice: str | None = None
    selected_outcome: str | None = None
    weight_mode: str
    options: list[str]
    target_amount: Decimal
    raised_amount: Decimal
    shortfall: Decimal
    viewer: dict[str, Any] | None = None
    blockchain_records: list[BlockchainRecord] = Field(default_factory=list)
    note: str = (
        "Governance results are recorded on chain for tamper-evidence. Any refund "
        "of rupees is executed by payment infrastructure, not by the blockchain."
    )
