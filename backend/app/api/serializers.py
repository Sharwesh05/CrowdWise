"""Model → schema projections.

Kept in one place so a field can never leak into a public response by accident:
`public_campaign` is the only path from a Campaign row to an anonymous caller.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.enums import ASPECT_LABELS, BlockchainRecordType, ContributionStatus
from app.models.campaign import Campaign
from app.models.chain import BlockchainTransaction
from app.models.community import (
    AIAnalysis,
    AICommunityInsight,
    CampaignUpdate,
    Feedback,
)
from app.models.payment import Contribution
from app.schemas.campaign import (
    AIAnalysisResponse,
    ApplicationResponse,
    BlockchainSummary,
    CampaignEventResponse,
    CampaignSummary,
    CampaignUpdateResponse,
    CommunityInsightResponse,
    CreatorCampaign,
    CreatorSummary,
    HealthResponse,
    PublicCampaign,
    SentimentSummary,
)
from app.schemas.payment import (
    BlockchainRecord,
    ContributionPublic,
    ContributionResponse,
    FeedbackResponse,
    PaymentResponse,
    VoteResponse,
)
from app.services import (
    ai_service,
    audit_service,
    blockchain_service,
    campaign_service,
    campaign_state,
    document_service,
    qr_service,
    sentiment_service,
    update_service,
)


def days_remaining(campaign: Campaign) -> int:
    return max((campaign.deadline - utcnow()).days, 0)


def creator_summary(campaign: Campaign) -> CreatorSummary:
    creator = campaign.creator
    return CreatorSummary(
        id=creator.id,
        name=creator.name,
        # "Verified" means the creator passed KYC — nothing more is disclosed.
        is_verified=creator.is_kyc_verified,
    )


def campaign_summary(
    db: Session, campaign: Campaign, *, with_health: bool = False
) -> CampaignSummary:
    stats = campaign_service.campaign_stats(db, campaign)
    health = campaign_service.campaign_health(db, campaign) if with_health else None
    return CampaignSummary(
        id=campaign.id,
        public_id=campaign.public_id,
        title=campaign.title,
        slug=campaign.slug,
        short_description=campaign.short_description,
        category=campaign.category,
        cover_image_url=campaign.cover_image_url,
        target_amount=campaign.target_amount,
        raised_amount=campaign.raised_amount,
        funding_percentage=campaign.funding_percentage,
        minimum_contribution=campaign.minimum_contribution,
        contributor_count=campaign.contributor_count,
        deadline=campaign.deadline,
        days_remaining=days_remaining(campaign),
        status=campaign.status,
        creator=creator_summary(campaign),
        average_rating=stats["average_rating"],
        health_score=health.score if health else None,
        health_label=health.label if health else None,
        is_demo=campaign.is_demo,
    )


def analysis_response(analysis: AIAnalysis | None) -> AIAnalysisResponse | None:
    if analysis is None:
        return None
    return AIAnalysisResponse(
        id=analysis.id,
        campaign_id=analysis.campaign_id,
        type=analysis.type,
        model=analysis.model,
        provider=analysis.provider,
        status=analysis.status,
        feasibility_score=analysis.feasibility_score,
        problem_clarity_score=analysis.problem_clarity_score,
        impact_score=analysis.impact_score,
        risk_score=analysis.risk_score,
        risk_level=analysis.risk_level,
        summary=analysis.summary,
        strengths=analysis.strengths or [],
        concerns=analysis.concerns or [],
        recommendations=analysis.recommendations or [],
        questions_for_creator=analysis.questions_for_creator or [],
        missing_information=analysis.missing_information or [],
        created_at=analysis.created_at,
    )


def insight_response(insight: AICommunityInsight | None) -> CommunityInsightResponse | None:
    if insight is None:
        return None
    return CommunityInsightResponse(
        id=insight.id,
        campaign_id=insight.campaign_id,
        positive_percentage=insight.positive_percentage,
        neutral_percentage=insight.neutral_percentage,
        negative_percentage=insight.negative_percentage,
        average_rating=insight.average_rating,
        feedback_count=insight.feedback_count,
        top_concerns=insight.top_concerns or [],
        positive_themes=insight.positive_themes or [],
        aspect_distribution=insight.aspect_distribution or {},
        community_summary=insight.community_summary,
        recommendations=insight.recommendations or [],
        questions_from_community=insight.questions_from_community or [],
        risk_change=insight.risk_change,
        model=insight.model,
        provider=insight.provider,
        status=insight.status,
        created_at=insight.created_at,
    )


def health_response(db: Session, campaign: Campaign) -> HealthResponse:
    health = campaign_service.campaign_health(db, campaign)
    return HealthResponse(
        score=health.score,
        label=health.label,
        financial_score=health.financial_score,
        community_score=health.community_score,
        ai_score=health.ai_score,
        signals=health.signals,
    )


def sentiment_summary(db: Session, campaign_id: int) -> SentimentSummary:
    stats = sentiment_service.aggregate_campaign_sentiment(db, campaign_id)
    return SentimentSummary(**sentiment_service.sentiment_summary_payload(stats))


def blockchain_summary(db: Session, campaign: Campaign) -> BlockchainSummary:
    stats = campaign_service.campaign_stats(db, campaign)
    latest = db.execute(
        select(BlockchainTransaction)
        .where(BlockchainTransaction.campaign_id == campaign.id)
        .order_by(BlockchainTransaction.id.desc())
        .limit(1)
    ).scalars().first()
    simulated = bool(latest and (latest.payload or {}).get("simulated")) or (
        settings.blockchain_provider == "mock"
    )
    return BlockchainSummary(
        recorded=stats["blockchain_recorded"],
        pending=max(stats["blockchain_pending"], 0),
        network=latest.network if latest else settings.blockchain_network,
        contract_address=latest.contract_address if latest else (settings.contract_address or None),
        latest_tx_hash=latest.tx_hash if latest else None,
        explorer_url=blockchain_service.explorer_url(latest.tx_hash) if latest else None,
        simulated=simulated,
    )


def outcome_rules(campaign: Campaign) -> dict[str, Any] | None:
    outcome = campaign.outcome
    if outcome is None:
        return None
    return {
        "outcome_type": outcome.outcome_type,
        "voting_weight_mode": outcome.voting_weight_mode,
        "options": (outcome.configuration or {}).get("options", ["REFUND", "CONTINUE"]),
        "eligibility": (outcome.configuration or {}).get(
            "eligibility", "at_least_one_verified_contribution"
        ),
        "locked_at": outcome.locked_at.isoformat() if outcome.locked_at else None,
        "selected_outcome": outcome.selected_outcome,
        "note": (
            "These outcome rules were fixed before contributions opened and cannot "
            "be changed once voting begins."
        ),
    }


def public_campaign(db: Session, campaign: Campaign) -> PublicCampaign:
    base = campaign_summary(db, campaign, with_health=True)
    return PublicCampaign(
        **base.model_dump(),
        description=campaign.description,
        problem_statement=campaign.problem_statement,
        proposed_solution=campaign.proposed_solution,
        expected_impact=campaign.expected_impact,
        published_at=campaign.published_at,
        governance_status=campaign.governance_status,
        governance_closes_at=campaign.governance_closes_at,
        qr_url=qr_service.campaign_url(campaign.public_id),
        outcome_rules=outcome_rules(campaign),
        analysis=analysis_response(ai_service.latest_analysis(db, campaign.id)),
        sentiment=sentiment_summary(db, campaign.id),
        update_count=update_service.count_updates(db, campaign.id),
        insights=insight_response(ai_service.latest_insight(db, campaign.id)),
        health=health_response(db, campaign),
        blockchain=blockchain_summary(db, campaign),
    )


def creator_campaign(db: Session, campaign: Campaign) -> CreatorCampaign:
    base = public_campaign(db, campaign)
    application = campaign.application
    return CreatorCampaign(
        **base.model_dump(),
        approval_status=campaign.approval_status,
        review_notes=campaign.review_notes,
        application=(
            ApplicationResponse.model_validate(application) if application else None
        ),
        qr_token=campaign.qr_token,
        events=[
            CampaignEventResponse.model_validate(event, from_attributes=True)
            for event in audit_service.list_campaign_events(db, campaign.id, limit=50)
        ],
        allowed_transitions=campaign_state.next_states(campaign.status),
        editable=campaign.status in campaign_service.EDITABLE_STATUSES,
    )


def feedback_response(feedback: Feedback, *, include_author: bool = False) -> FeedbackResponse:
    return FeedbackResponse(
        id=feedback.id,
        campaign_id=feedback.campaign_id,
        text=feedback.text,
        rating=feedback.rating,
        sentiment=feedback.sentiment,
        sentiment_score=feedback.sentiment_score,
        aspect=feedback.aspect,
        aspects=feedback.aspects or [],
        aspect_label=ASPECT_LABELS.get(feedback.aspect or "", None),
        # Feedback is attributed only by display name, and only where the product
        # calls for it. Author identity never leaves the database otherwise.
        author_name=(feedback.contributor.name if include_author and feedback.contributor else None),
        created_at=feedback.created_at,
    )


def campaign_update_response(update: CampaignUpdate) -> CampaignUpdateResponse:
    return CampaignUpdateResponse(
        id=update.id,
        campaign_id=update.campaign_id,
        title=update.title,
        body=update.body,
        is_pinned=update.is_pinned,
        # Updates are signed, unlike feedback: the community needs to know the
        # creator is the one speaking.
        author_name=update.author.name if update.author else None,
        created_at=update.created_at,
        updated_at=update.updated_at,
    )


def blockchain_record(record: BlockchainTransaction | None) -> BlockchainRecord | None:
    if record is None:
        return None
    return BlockchainRecord(
        id=record.id,
        record_type=record.record_type,
        tx_hash=record.tx_hash,
        network=record.network,
        contract_address=record.contract_address,
        status=record.status,
        block_number=record.block_number,
        gas_used=record.gas_used,
        created_at=record.created_at,
        explorer_url=blockchain_service.explorer_url(record.tx_hash),
        simulated=bool((record.payload or {}).get("simulated")),
    )


def contribution_response(
    db: Session, contribution: Contribution, *, with_payment: bool = True
) -> ContributionResponse:
    campaign = contribution.campaign
    record = (
        db.get(BlockchainTransaction, contribution.blockchain_record_id)
        if contribution.blockchain_record_id
        else None
    )
    return ContributionResponse(
        id=contribution.id,
        campaign_id=contribution.campaign_id,
        campaign_public_id=campaign.public_id if campaign else None,
        campaign_title=campaign.title if campaign else None,
        amount=contribution.amount,
        status=contribution.status,
        blockchain_tx=contribution.blockchain_tx,
        blockchain_attempts=contribution.blockchain_attempts,
        created_at=contribution.created_at,
        payment=(
            PaymentResponse.model_validate(contribution.payment)
            if with_payment and contribution.payment
            else None
        ),
        blockchain_record=blockchain_record(record),
    )


def contribution_public(contribution: Contribution) -> ContributionPublic:
    name = "Anonymous"
    if not contribution.is_anonymous and contribution.contributor:
        parts = contribution.contributor.name.split()
        # Public backer list shows a first name and an initial only.
        name = parts[0] + (f" {parts[-1][0]}." if len(parts) > 1 else "")
    return ContributionPublic(
        id=contribution.id,
        amount=contribution.amount,
        contributor_name=name,
        status=contribution.status,
        blockchain_tx=contribution.blockchain_tx,
        created_at=contribution.created_at,
    )


def vote_response(vote, campaign: Campaign | None = None) -> VoteResponse:
    return VoteResponse(
        id=vote.id,
        campaign_id=vote.campaign_id,
        choice=vote.choice,
        weight=vote.weight,
        blockchain_tx=vote.blockchain_tx,
        blockchain_status=vote.blockchain_status,
        created_at=vote.created_at,
        campaign_title=campaign.title if campaign else None,
        campaign_public_id=campaign.public_id if campaign else None,
    )


def verified_contribution_total(db: Session, user_id: int) -> Decimal:
    from sqlalchemy import func

    total = db.execute(
        select(func.sum(Contribution.amount)).where(
            Contribution.contributor_id == user_id,
            Contribution.status.in_(
                [
                    str(ContributionStatus.PAYMENT_VERIFIED),
                    str(ContributionStatus.BLOCKCHAIN_PENDING),
                    str(ContributionStatus.BLOCKCHAIN_RECORDED),
                ]
            ),
        )
    ).scalar_one_or_none()
    return Decimal(total or 0)


__all__ = [
    "analysis_response",
    "blockchain_record",
    "blockchain_summary",
    "campaign_summary",
    "contribution_public",
    "contribution_response",
    "creator_campaign",
    "feedback_response",
    "health_response",
    "insight_response",
    "outcome_rules",
    "public_campaign",
    "sentiment_summary",
    "verified_contribution_total",
    "vote_response",
    "BlockchainRecordType",
]


def document_response(document) -> "DocumentResponse":
    """One shape for a document, wherever it is listed.

    `url` always points at the authenticated download route. The storage key is
    never exposed: `/api/files` does not check who is asking, so a key in a
    response body would be a bearer token for the file, for good.
    """
    from app.schemas.campaign import DocumentResponse

    return DocumentResponse(
        id=document.id,
        file_name=document.file_name,
        mime_type=document.mime_type,
        size=document.size,
        created_at=document.created_at,
        visibility=document.visibility,
        is_machine_readable=document.is_machine_readable,
        extraction_note=document.extraction_note,
        url=document_service.download_path(document.campaign_id, document.id),
    )
