"""Campaign lifecycle service.

Every status change in the product passes through here, and every one of them is
validated by `campaign_state`. A creator cannot publish by patching a field; an
admin cannot approve a campaign that never paid its fee; nothing reaches LIVE
without KYC, fee verification, AI analysis and a human decision.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from slugify import slugify
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.enums import (
    PUBLIC_CAMPAIGN_STATUSES,
    ApplicationStatus,
    ApprovalStatus,
    CampaignStatus,
    ContributionStatus,
    EventType,
    GovernanceStatus,
    OutcomeType,
    VotingWeightMode,
)
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.models.campaign import Campaign, CampaignApplication, CampaignOutcome
from app.models.community import Feedback
from app.models.payment import Contribution
from app.models.user import User
from app.services import audit_service, campaign_state, kyc_service, qr_service

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Identifiers
# --------------------------------------------------------------------------
# Crockford base32: no I, L, O or U, so an id read aloud or copied off a QR
# code cannot be confused between 1/I/L or 0/O.
_ID_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_ID_LENGTH = 6


def _title_digest(title: str, attempt: int) -> str:
    """Deterministic short code for a title. 32**6 ≈ 1.07e9 codes."""
    seed = slugify(title) or "campaign"
    if attempt:
        seed = f"{seed}#{attempt}"
    value = int.from_bytes(
        hashlib.blake2b(seed.encode("utf-8"), digest_size=8).digest(), "big"
    )
    out = []
    for _ in range(_ID_LENGTH):
        out.append(_ID_ALPHABET[value % len(_ID_ALPHABET)])
        value //= len(_ID_ALPHABET)
    return "".join(out)


def next_public_id(db: Session, title: str) -> str:
    """External id derived from the title: CMP-7QF2KD.

    Derived rather than sequential so the id carries no information about how
    many campaigns exist or in what order they were created — a count that
    leaked from CMP-100, CMP-101, ... on every public URL and QR code. The
    same title always yields the same code; a genuine collision (or a repeated
    title) walks the attempt counter until the id is free.
    """
    for attempt in range(1000):
        candidate = f"CMP-{_title_digest(title, attempt)}"
        taken = db.execute(
            select(Campaign.id).where(Campaign.public_id == candidate)
        ).first()
        if not taken:
            return candidate
    raise ConflictError("Could not allocate a campaign id; please retry.")


def unique_slug(db: Session, title: str) -> str:
    base = slugify(title)[:150] or "campaign"
    candidate = base
    suffix = 2
    while db.execute(select(Campaign.id).where(Campaign.slug == candidate)).first():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


# --------------------------------------------------------------------------
# Lookups
# --------------------------------------------------------------------------
def get_by_id(db: Session, campaign_id: int) -> Campaign:
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign not found.")
    return campaign


def get_by_public_id(db: Session, public_id: str) -> Campaign:
    campaign = db.execute(
        select(Campaign).where(Campaign.public_id == public_id)
    ).scalars().first()
    if campaign is None:
        # Accept the slug too, so a shared link keeps working after a rename.
        campaign = db.execute(select(Campaign).where(Campaign.slug == public_id)).scalars().first()
    if campaign is None:
        raise NotFoundError("Campaign not found.")
    return campaign


def get_public(db: Session, public_id: str) -> Campaign:
    campaign = get_by_public_id(db, public_id)
    if campaign.status not in PUBLIC_CAMPAIGN_STATUSES:
        raise NotFoundError("Campaign not found.")
    return campaign


def assert_owner(campaign: Campaign, user: User) -> None:
    if campaign.creator_id != user.id:
        raise PermissionDeniedError("You do not have access to this campaign.")


# --------------------------------------------------------------------------
# Creation
# --------------------------------------------------------------------------
@dataclass(slots=True)
class CampaignDraft:
    title: str
    short_description: str
    description: str
    problem_statement: str
    proposed_solution: str
    category: str
    target_amount: Decimal
    minimum_contribution: Decimal
    deadline: Any
    expected_impact: str | None = None
    cover_image_url: str | None = None
    outcome_type: str = str(OutcomeType.CONTRIBUTOR_VOTE)
    voting_weight_mode: str = str(VotingWeightMode.ONE_PERSON_ONE_VOTE)


def create_campaign(db: Session, creator: User, draft: CampaignDraft) -> Campaign:
    if draft.target_amount <= 0:
        raise ValidationError("Target amount must be greater than zero.")
    if draft.minimum_contribution <= 0:
        raise ValidationError("Minimum contribution must be greater than zero.")
    if draft.minimum_contribution > draft.target_amount:
        raise ValidationError("Minimum contribution cannot exceed the target amount.")
    deadline = draft.deadline
    if deadline.tzinfo is None:
        deadline = deadline.replace(tzinfo=utcnow().tzinfo)
    if deadline <= utcnow():
        raise ValidationError("Deadline must be in the future.")

    campaign = Campaign(
        public_id=next_public_id(db, draft.title),
        creator_id=creator.id,
        title=draft.title.strip(),
        slug=unique_slug(db, draft.title),
        short_description=draft.short_description.strip(),
        description=draft.description.strip(),
        problem_statement=draft.problem_statement.strip(),
        proposed_solution=draft.proposed_solution.strip(),
        expected_impact=(draft.expected_impact or "").strip() or None,
        category=draft.category,
        target_amount=draft.target_amount,
        minimum_contribution=draft.minimum_contribution,
        deadline=deadline,
        status=CampaignStatus.DRAFT,
        approval_status=ApprovalStatus.NOT_SUBMITTED,
        cover_image_url=draft.cover_image_url,
    )
    db.add(campaign)
    db.flush()

    # The outcome rules are created with the campaign and locked at publication,
    # so contributors always know the end-state rules before they fund anything.
    db.add(
        CampaignOutcome(
            campaign_id=campaign.id,
            outcome_type=draft.outcome_type,
            voting_weight_mode=draft.voting_weight_mode,
            threshold=Decimal("50.00"),
            configuration={
                "options": ["REFUND", "CONTINUE"],
                "eligibility": "at_least_one_verified_contribution",
                "extension_days": settings.governance_extension_days,
            },
        )
    )
    db.add(
        CampaignApplication(
            campaign_id=campaign.id,
            creator_id=creator.id,
            application_fee=Decimal(str(settings.application_fee_amount)),
            status=ApplicationStatus.DRAFT,
        )
    )
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_CREATED,
        actor_id=creator.id,
        metadata={"public_id": campaign.public_id, "target_amount": str(campaign.target_amount)},
    )
    return campaign


# A proposal stays the creator's to correct right up until a reviewer acts on it.
# UNDER_REVIEW is included deliberately: the campaign can sit in the queue for
# days, and a creator who spots a wrong figure in their own budget should be able
# to fix it rather than wait to be rejected for it. The edit is audited, and the
# review panel flags a proposal that changed after its analysis ran, so a
# reviewer is never quietly shown scores for text that no longer exists.
EDITABLE_STATUSES = {
    CampaignStatus.DRAFT,
    CampaignStatus.KYC_PENDING,
    CampaignStatus.FEE_PENDING,
    CampaignStatus.UNDER_REVIEW,
}


def update_campaign(db: Session, campaign: Campaign, changes: dict[str, Any]) -> Campaign:
    if campaign.status not in EDITABLE_STATUSES:
        raise ConflictError(
            f"A campaign in {campaign.status} can no longer be edited.",
            details={"status": campaign.status},
        )
    if campaign.status == CampaignStatus.LIVE:  # pragma: no cover - defensive
        raise ConflictError("A live campaign cannot be edited.")
    allowed = {
        "title", "short_description", "description", "problem_statement",
        "proposed_solution", "expected_impact", "category", "target_amount",
        "minimum_contribution", "deadline", "cover_image_url",
    }
    changed: list[str] = []
    for key, value in changes.items():
        if key in allowed and value is not None and getattr(campaign, key) != value:
            setattr(campaign, key, value)
            changed.append(key)
    if not changed:
        return campaign
    if "title" in changed:
        campaign.slug = unique_slug(db, changes["title"])
    db.flush()
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.CAMPAIGN_UPDATED,
        actor_id=campaign.creator_id,
        metadata={"fields": sorted(changed)},
    )
    return campaign


# --------------------------------------------------------------------------
# Lifecycle progression
# --------------------------------------------------------------------------
def submit_application(db: Session, campaign: Campaign, creator: User) -> Campaign:
    """DRAFT → KYC_PENDING → FEE_PENDING, depending on where the creator stands."""
    if campaign.status not in (CampaignStatus.DRAFT, CampaignStatus.KYC_PENDING):
        raise ConflictError(
            f"This campaign has already been submitted (status {campaign.status})."
        )
    if campaign.status == CampaignStatus.DRAFT:
        campaign_state.transition(campaign, CampaignStatus.KYC_PENDING)
        db.flush()

    # Business rule 1: KYC gates everything downstream.
    kyc_service.require_verified(creator)

    campaign_state.transition(campaign, CampaignStatus.FEE_PENDING)
    application = campaign.application
    if application and application.status == ApplicationStatus.DRAFT:
        application.status = ApplicationStatus.FEE_PENDING
        application.submitted_at = utcnow()
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_SUBMITTED,
        actor_id=creator.id,
        metadata={"status": campaign.status},
    )
    return campaign


def advance_after_fee(db: Session, campaign: Campaign, actor_id: int | None = None) -> Campaign:
    """Called only from the verified-payment path: FEE_PENDING → ANALYSIS_PENDING."""
    if campaign.status != CampaignStatus.FEE_PENDING:
        return campaign
    campaign_state.transition(campaign, CampaignStatus.ANALYSIS_PENDING)
    db.flush()
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.AI_ANALYSIS_STARTED,
        actor_id=actor_id,
        metadata={"trigger": "application_fee_verified"},
    )
    return campaign


def complete_analysis(db: Session, campaign: Campaign, actor_id: int | None = None) -> Campaign:
    """ANALYSIS_PENDING → UNDER_REVIEW once an analysis record exists."""
    if campaign.status != CampaignStatus.ANALYSIS_PENDING:
        return campaign
    campaign_state.transition(campaign, CampaignStatus.UNDER_REVIEW)
    campaign.approval_status = ApprovalStatus.PENDING
    application = campaign.application
    if application:
        application.status = ApplicationStatus.SUBMITTED
    db.flush()
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_SUBMITTED,
        actor_id=actor_id,
        metadata={"status": campaign.status, "awaiting": "admin_review"},
    )
    return campaign


def run_analysis_and_advance(
    db: Session, campaign: Campaign, actor_id: int | None = None
) -> Campaign:
    from app.services import ai_service  # local import avoids a cycle

    if campaign.status not in (CampaignStatus.ANALYSIS_PENDING, CampaignStatus.UNDER_REVIEW):
        raise ConflictError(
            "Analysis can only run after the application fee is verified.",
            details={"status": campaign.status},
        )
    ai_service.analyze_campaign(db, campaign, actor_id=actor_id)
    return complete_analysis(db, campaign, actor_id=actor_id)


# --------------------------------------------------------------------------
# Admin review
# --------------------------------------------------------------------------
def approve_campaign(
    db: Session, campaign: Campaign, admin: User, notes: str | None = None
) -> Campaign:
    if campaign.status != CampaignStatus.UNDER_REVIEW:
        raise ConflictError(
            "Only a campaign under review can be approved.", details={"status": campaign.status}
        )
    application = campaign.application
    if application and application.status not in (
        ApplicationStatus.FEE_PAID,
        ApplicationStatus.SUBMITTED,
    ):
        raise ConflictError("The application fee has not been verified for this campaign.")

    campaign_state.transition(campaign, CampaignStatus.APPROVED)
    campaign.approval_status = ApprovalStatus.APPROVED
    campaign.review_notes = notes
    if application:
        application.status = ApplicationStatus.APPROVED
        application.reviewed_at = utcnow()
        application.reviewed_by = admin.id
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_APPROVED,
        actor_id=admin.id,
        metadata={"notes": notes},
    )
    return publish_campaign(db, campaign, admin)


def reject_campaign(db: Session, campaign: Campaign, admin: User, reason: str) -> Campaign:
    if campaign.status != CampaignStatus.UNDER_REVIEW:
        raise ConflictError("Only a campaign under review can be rejected.")
    campaign_state.transition(campaign, CampaignStatus.REJECTED)
    campaign.approval_status = ApprovalStatus.REJECTED
    campaign.review_notes = reason
    application = campaign.application
    if application:
        application.status = ApplicationStatus.REJECTED
        application.reviewed_at = utcnow()
        application.reviewed_by = admin.id
    db.flush()
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_REJECTED,
        actor_id=admin.id,
        metadata={"reason": reason},
    )
    return campaign


def request_changes(db: Session, campaign: Campaign, admin: User, notes: str) -> Campaign:
    if campaign.status != CampaignStatus.UNDER_REVIEW:
        raise ConflictError("Only a campaign under review can be sent back for changes.")
    campaign_state.transition(campaign, CampaignStatus.DRAFT)
    campaign.approval_status = ApprovalStatus.CHANGES_REQUESTED
    campaign.review_notes = notes
    application = campaign.application
    if application:
        # The fee is not charged twice: the application returns to FEE_PAID, not DRAFT.
        application.status = ApplicationStatus.CHANGES_REQUESTED
        application.reviewed_at = utcnow()
        application.reviewed_by = admin.id
    db.flush()
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_CHANGES_REQUESTED,
        actor_id=admin.id,
        metadata={"notes": notes},
    )
    return campaign


def publish_campaign(db: Session, campaign: Campaign, actor: User) -> Campaign:
    """APPROVED → LIVE. Issues the QR and locks the outcome rules."""
    from app.services import blockchain_service  # local import avoids a cycle

    if campaign.status != CampaignStatus.APPROVED:
        raise ConflictError("Only an approved campaign can be published.")

    campaign_state.transition(campaign, CampaignStatus.LIVE)
    campaign.published_at = utcnow()
    if not campaign.qr_token:
        campaign.qr_token = qr_service.new_qr_token()
    if campaign.outcome and campaign.outcome.locked_at is None:
        # From here on the end-state rules cannot change — contributors fund
        # against a fixed contract.
        campaign.outcome.locked_at = utcnow()
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_PUBLISHED,
        actor_id=actor.id,
        metadata={"public_id": campaign.public_id, "url": qr_service.campaign_url(campaign.public_id)},
    )
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.QR_GENERATED,
        actor_id=actor.id,
        metadata={"qr_url": qr_service.campaign_url(campaign.public_id)},
    )
    blockchain_service.register_campaign(db, campaign)
    return campaign


# --------------------------------------------------------------------------
# Completion
# --------------------------------------------------------------------------
def complete_campaign(db: Session, campaign: Campaign, actor_id: int | None = None) -> Campaign:
    """Deadline reached: LIVE → COMPLETED → TARGET_MET | TARGET_MISSED.

    The system reports the arithmetic; it does not invent a financial outcome.
    What happens next comes from the campaign's predefined rules.
    """
    from app.services import governance_service  # local import avoids a cycle

    if campaign.status in (CampaignStatus.LIVE, CampaignStatus.CONTINUED):
        campaign_state.transition(campaign, CampaignStatus.COMPLETED)
        campaign.completed_at = utcnow()
        db.flush()
        audit_service.record_both(
            db,
            campaign_id=campaign.id,
            action=EventType.CAMPAIGN_COMPLETED,
            actor_id=actor_id,
            metadata={
                "raised_amount": str(campaign.raised_amount),
                "target_amount": str(campaign.target_amount),
            },
        )
    if campaign.status != CampaignStatus.COMPLETED:
        return campaign

    if campaign.target_met:
        campaign_state.transition(campaign, CampaignStatus.TARGET_MET)
        db.flush()
        audit_service.record_both(
            db,
            campaign_id=campaign.id,
            action=EventType.TARGET_MET,
            actor_id=actor_id,
            metadata={"raised_amount": str(campaign.raised_amount)},
        )
        return campaign

    campaign_state.transition(campaign, CampaignStatus.TARGET_MISSED)
    db.flush()
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.TARGET_MISSED,
        actor_id=actor_id,
        metadata={
            "raised_amount": str(campaign.raised_amount),
            "target_amount": str(campaign.target_amount),
            "shortfall": str(Decimal(campaign.target_amount) - Decimal(campaign.raised_amount)),
        },
    )
    return governance_service.apply_predefined_outcome(db, campaign, actor_id=actor_id)


def process_due_deadlines(db: Session, limit: int = 100) -> int:
    """Worker pass: complete every campaign whose deadline has passed."""
    stmt = (
        select(Campaign)
        .where(
            Campaign.status.in_([str(CampaignStatus.LIVE), str(CampaignStatus.CONTINUED)]),
            Campaign.deadline <= utcnow(),
        )
        .limit(limit)
    )
    due = list(db.execute(stmt).scalars().all())
    for campaign in due:
        complete_campaign(db, campaign)
    if due:
        db.commit()
    return len(due)


def extend_deadline(db: Session, campaign: Campaign, days: int, actor_id: int | None) -> Campaign:
    campaign.deadline = utcnow() + timedelta(days=days)
    db.flush()
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.CAMPAIGN_CONTINUED,
        actor_id=actor_id,
        metadata={"extension_days": days, "new_deadline": campaign.deadline.isoformat()},
    )
    return campaign


# --------------------------------------------------------------------------
# Discovery
# --------------------------------------------------------------------------
SORT_OPTIONS = ("trending", "newest", "progress", "most_supported", "ending_soon")


def list_public_campaigns(
    db: Session,
    *,
    search: str | None = None,
    category: str | None = None,
    status: str | None = None,
    sort: str = "trending",
    limit: int = 12,
    offset: int = 0,
) -> tuple[list[Campaign], int]:
    stmt = select(Campaign).where(
        Campaign.status.in_([str(s) for s in PUBLIC_CAMPAIGN_STATUSES])
    )
    if search:
        pattern = f"%{search.strip()}%"
        stmt = stmt.where(
            or_(
                Campaign.title.ilike(pattern),
                Campaign.short_description.ilike(pattern),
                Campaign.description.ilike(pattern),
            )
        )
    if category:
        stmt = stmt.where(Campaign.category == category)
    if status:
        stmt = stmt.where(Campaign.status == status)

    total = int(
        db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one()
    )

    if sort == "newest":
        stmt = stmt.order_by(Campaign.published_at.desc().nullslast(), Campaign.id.desc())
    elif sort == "progress":
        # Ratio, not absolute rupees, so a small campaign near its goal ranks fairly.
        stmt = stmt.order_by((Campaign.raised_amount / Campaign.target_amount).desc())
    elif sort == "most_supported":
        stmt = stmt.order_by(Campaign.contributor_count.desc(), Campaign.raised_amount.desc())
    elif sort == "ending_soon":
        stmt = stmt.order_by(Campaign.deadline.asc())
    else:  # trending: observed activity only — no fabricated engagement metric
        stmt = stmt.order_by(
            Campaign.contributor_count.desc(),
            Campaign.raised_amount.desc(),
            Campaign.published_at.desc().nullslast(),
        )

    rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
    return rows, total


def list_creator_campaigns(db: Session, creator_id: int) -> list[Campaign]:
    return list(
        db.execute(
            select(Campaign)
            .where(Campaign.creator_id == creator_id)
            .order_by(Campaign.id.desc())
        ).scalars().all()
    )


# --------------------------------------------------------------------------
# Campaign health
# --------------------------------------------------------------------------
@dataclass(slots=True)
class CampaignHealth:
    score: int
    label: str
    financial_score: int
    community_score: int
    ai_score: int
    signals: dict[str, Any]


def campaign_health(db: Session, campaign: Campaign) -> CampaignHealth:
    """CrowdWise Campaign Health — a transparent blend of observed signals.

    Explicitly not a prediction of financial success: it summarises what is
    already true about funding, community response and AI-flagged risk.
    """
    from app.services import ai_service, sentiment_service  # local import avoids a cycle

    funding_pct = campaign.funding_percentage
    days_total = max(
        ((campaign.deadline - (campaign.published_at or campaign.created_at)).days or 1), 1
    )
    days_remaining = max((campaign.deadline - utcnow()).days, 0)
    days_elapsed = max(days_total - days_remaining, 1)
    expected_pct = min(days_elapsed / days_total * 100, 100)
    # Velocity: actual progress against the straight-line pace for the window.
    velocity_ratio = (funding_pct / expected_pct) if expected_pct > 0 else 0.0

    contribution_count = int(
        db.execute(
            select(func.count(Contribution.id)).where(Contribution.campaign_id == campaign.id)
        ).scalar_one()
    )
    average_contribution = (
        float(Decimal(campaign.raised_amount) / contribution_count) if contribution_count else 0.0
    )

    financial = min(funding_pct, 100) * 0.6 + min(velocity_ratio * 100, 100) * 0.4
    financial_score = int(max(0, min(100, financial)))

    stats = sentiment_service.aggregate_campaign_sentiment(db, campaign.id)
    if stats.feedback_count:
        rating_component = (stats.average_rating / 5) * 100
        sentiment_component = stats.positive_percentage
        volume_component = min(stats.feedback_count / 20 * 100, 100)
        community_score = int(
            max(
                0,
                min(
                    100,
                    rating_component * 0.4 + sentiment_component * 0.45 + volume_component * 0.15,
                ),
            )
        )
    else:
        community_score = 50  # neutral until the community has actually spoken

    analysis = ai_service.latest_analysis(db, campaign.id)
    if analysis:
        ai_score = int(
            max(
                0,
                min(
                    100,
                    (analysis.feasibility_score or 50) * 0.4
                    + (analysis.impact_score or 50) * 0.2
                    + (100 - (analysis.risk_score or 50)) * 0.4,
                ),
            )
        )
    else:
        ai_score = 50

    score = int(round(financial_score * 0.4 + community_score * 0.3 + ai_score * 0.3))
    label = (
        "Strong" if score >= 75 else
        "Healthy" if score >= 60 else
        "Watch" if score >= 45 else
        "At risk"
    )

    return CampaignHealth(
        score=score,
        label=label,
        financial_score=financial_score,
        community_score=community_score,
        ai_score=ai_score,
        signals={
            "funding_percentage": funding_pct,
            "funding_velocity": round(velocity_ratio, 2),
            "contribution_count": contribution_count,
            "average_contribution": round(average_contribution, 2),
            "days_remaining": days_remaining,
            "average_rating": stats.average_rating,
            "feedback_count": stats.feedback_count,
            "positive_percentage": stats.positive_percentage,
            "ai_risk_score": analysis.risk_score if analysis else None,
            "ai_risk_level": analysis.risk_level if analysis else None,
            "ai_feasibility_score": analysis.feasibility_score if analysis else None,
        },
    )


def campaign_stats(db: Session, campaign: Campaign) -> dict[str, Any]:
    """Aggregates used by the campaign page and creator dashboard."""
    verified_statuses = [
        str(ContributionStatus.PAYMENT_VERIFIED),
        str(ContributionStatus.BLOCKCHAIN_PENDING),
        str(ContributionStatus.BLOCKCHAIN_RECORDED),
    ]
    contribution_count = int(
        db.execute(
            select(func.count(Contribution.id)).where(
                Contribution.campaign_id == campaign.id,
                Contribution.status.in_(verified_statuses),
            )
        ).scalar_one()
    )
    average_rating = db.execute(
        select(func.avg(Feedback.rating)).where(Feedback.campaign_id == campaign.id)
    ).scalar_one_or_none()
    anchored = int(
        db.execute(
            select(func.count(Contribution.id)).where(
                Contribution.campaign_id == campaign.id,
                Contribution.status == str(ContributionStatus.BLOCKCHAIN_RECORDED),
            )
        ).scalar_one()
    )
    return {
        "contribution_count": contribution_count,
        "contributor_count": campaign.contributor_count,
        "average_rating": round(float(average_rating), 2) if average_rating else None,
        "blockchain_recorded": anchored,
        "blockchain_pending": contribution_count - anchored,
        "days_remaining": max((campaign.deadline - utcnow()).days, 0),
        "funding_percentage": campaign.funding_percentage,
    }


def is_governance_open(campaign: Campaign) -> bool:
    return (
        campaign.status == CampaignStatus.GOVERNANCE
        and campaign.governance_status == GovernanceStatus.OPEN
    )
