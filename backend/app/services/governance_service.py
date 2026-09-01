"""Contributor governance.

Governance exists because a missed target is not automatically a refund and not
automatically a continuation — it is a decision, and the people who funded the
campaign are the ones entitled to make it.

Two rules are load-bearing:

* The available outcomes are **predefined**, locked at publication, and cannot be
  changed once voting opens. Contributors fund against known end-state rules.
* Only a contributor with at least one verified contribution may vote, once.
  Duplicate prevention is a database constraint, not a hopeful `if`.

Refunds are executed by payment infrastructure. The chain records the decision.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import advisory_lock, utcnow
from app.core.enums import (
    CampaignStatus,
    ContributionStatus,
    EventType,
    GovernanceStatus,
    OutcomeType,
    VoteChoice,
    VotingWeightMode,
)
from app.core.errors import ConflictError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.governance import Vote
from app.models.payment import Contribution
from app.models.user import User
from app.services import audit_service, campaign_state

logger = get_logger(__name__)

# Distinct from the chain sweeper's key: the two jobs are unrelated and must
# never block one another.
REFUND_LOCK_KEY = 0x43575F524546 % (2**63)

VERIFIED_CONTRIBUTION_STATUSES = [
    str(ContributionStatus.PAYMENT_VERIFIED),
    str(ContributionStatus.BLOCKCHAIN_PENDING),
    str(ContributionStatus.BLOCKCHAIN_RECORDED),
]


@dataclass(slots=True)
class GovernanceTally:
    campaign_public_id: str
    status: str
    is_open: bool
    closes_at: str | None
    total_eligible_voters: int
    votes_cast: int
    participation_percentage: float
    results: dict[str, dict[str, Any]]
    leading_choice: str | None
    selected_outcome: str | None
    weight_mode: str
    options: list[str]


# --------------------------------------------------------------------------
# Predefined outcome application
# --------------------------------------------------------------------------
def apply_predefined_outcome(
    db: Session, campaign: Campaign, actor_id: int | None = None
) -> Campaign:
    """After TARGET_MISSED, do exactly what the campaign said it would do."""
    outcome = campaign.outcome
    outcome_type = outcome.outcome_type if outcome else str(OutcomeType.CONTRIBUTOR_VOTE)

    if outcome_type == OutcomeType.AUTOMATIC_REFUND:
        campaign_state.transition(campaign, CampaignStatus.REFUND_PENDING)
        if outcome:
            outcome.selected_outcome = str(VoteChoice.REFUND)
            outcome.executed_at = utcnow()
        # Flagging the campaign is not enough: the refund sweep selects
        # *contributions* in REFUND_PENDING, so without this a campaign that
        # promised an automatic refund would report success having refunded
        # nobody. The vote-driven path in close_governance already does this.
        mark_contributions_refund_pending(db, campaign)
        db.flush()
        audit_service.record_both(
            db,
            campaign_id=campaign.id,
            action=EventType.OUTCOME_SELECTED,
            actor_id=actor_id,
            metadata={"outcome": "REFUND", "source": "predefined_automatic_refund"},
        )
        return campaign

    if outcome_type == OutcomeType.KEEP_WHAT_YOU_RAISE:
        campaign_state.transition(campaign, CampaignStatus.CLOSED)
        if outcome:
            outcome.selected_outcome = "KEEP_WHAT_YOU_RAISE"
            outcome.executed_at = utcnow()
        db.flush()
        audit_service.record_both(
            db,
            campaign_id=campaign.id,
            action=EventType.OUTCOME_SELECTED,
            actor_id=actor_id,
            metadata={"outcome": "KEEP_WHAT_YOU_RAISE", "source": "predefined"},
        )
        return campaign

    return open_governance(db, campaign, actor_id=actor_id)


def open_governance(
    db: Session, campaign: Campaign, actor_id: int | None = None, duration_hours: int | None = None
) -> Campaign:
    from app.services import blockchain_service  # local import avoids a cycle

    if campaign.status not in (CampaignStatus.TARGET_MISSED, CampaignStatus.GOVERNANCE):
        raise ConflictError(
            "Governance can only open for a campaign that missed its target.",
            details={"status": campaign.status},
        )
    if campaign.governance_status == GovernanceStatus.OPEN:
        return campaign

    if campaign.status == CampaignStatus.TARGET_MISSED:
        campaign_state.transition(campaign, CampaignStatus.GOVERNANCE)
    campaign.governance_status = GovernanceStatus.OPEN
    hours = duration_hours or settings.governance_duration_hours
    campaign.governance_closes_at = utcnow() + timedelta(hours=hours)
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.VOTING_OPENED,
        actor_id=actor_id,
        metadata={
            "closes_at": campaign.governance_closes_at.isoformat(),
            "options": governance_options(campaign),
            "eligible_voters": count_eligible_voters(db, campaign.id),
        },
    )
    blockchain_service.open_voting_on_chain(
        db, campaign, int(campaign.governance_closes_at.timestamp())
    )
    return campaign


def governance_options(campaign: Campaign) -> list[str]:
    config = (campaign.outcome.configuration if campaign.outcome else None) or {}
    return list(config.get("options") or [str(VoteChoice.REFUND), str(VoteChoice.CONTINUE)])


# --------------------------------------------------------------------------
# Eligibility
# --------------------------------------------------------------------------
def count_eligible_voters(db: Session, campaign_id: int) -> int:
    return int(
        db.execute(
            select(func.count(func.distinct(Contribution.contributor_id))).where(
                Contribution.campaign_id == campaign_id,
                Contribution.status.in_(VERIFIED_CONTRIBUTION_STATUSES),
            )
        ).scalar_one()
    )


def contributor_total(db: Session, campaign_id: int, user_id: int) -> Decimal:
    total = db.execute(
        select(func.sum(Contribution.amount)).where(
            Contribution.campaign_id == campaign_id,
            Contribution.contributor_id == user_id,
            Contribution.status.in_(VERIFIED_CONTRIBUTION_STATUSES),
        )
    ).scalar_one_or_none()
    return Decimal(total or 0)


def is_eligible(db: Session, campaign_id: int, user_id: int) -> bool:
    """MVP eligibility: at least one verified contribution to this campaign."""
    return contributor_total(db, campaign_id, user_id) > 0


def existing_vote(db: Session, campaign_id: int, user_id: int, round_no: int = 1) -> Vote | None:
    return db.execute(
        select(Vote).where(
            Vote.campaign_id == campaign_id,
            Vote.contributor_id == user_id,
            Vote.governance_round == round_no,
        )
    ).scalars().first()


# --------------------------------------------------------------------------
# Voting
# --------------------------------------------------------------------------
def cast_vote(db: Session, campaign: Campaign, user: User, choice: str) -> Vote:
    from app.services import blockchain_service  # local import avoids a cycle

    if campaign.status != CampaignStatus.GOVERNANCE:
        raise ConflictError(
            "This campaign is not in a governance round.", details={"status": campaign.status}
        )
    if campaign.governance_status != GovernanceStatus.OPEN:
        raise ConflictError("Voting for this campaign is closed.")
    if campaign.governance_closes_at and utcnow() > campaign.governance_closes_at:
        raise ConflictError("The voting deadline for this campaign has passed.")

    options = governance_options(campaign)
    if choice not in options:
        raise ValidationError(
            "That is not one of this campaign's predefined outcomes.",
            details={"options": options},
        )
    if not is_eligible(db, campaign.id, user.id):
        raise PermissionDeniedError(
            "Only contributors with a verified contribution to this campaign can vote."
        )
    if existing_vote(db, campaign.id, user.id):
        raise ConflictError("You have already voted in this governance round.")

    weight = Decimal("1.00")
    if (
        campaign.outcome
        and campaign.outcome.voting_weight_mode == VotingWeightMode.CONTRIBUTION_WEIGHTED
    ):
        weight = contributor_total(db, campaign.id, user.id)

    vote = Vote(
        campaign_id=campaign.id,
        contributor_id=user.id,
        governance_round=1,
        choice=choice,
        weight=weight,
    )
    db.add(vote)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("You have already voted in this governance round.") from exc

    audit_service.record_audit(
        db,
        action=EventType.VOTE_CAST,
        actor_id=user.id,
        entity_type="vote",
        entity_id=vote.id,
        metadata={"campaign": campaign.public_id, "choice": choice, "weight": str(weight)},
    )
    # The vote is valid in PostgreSQL whether or not the chain is reachable;
    # anchoring adds tamper-evidence, it does not confer validity.
    blockchain_service.record_vote_on_chain(db, vote)
    return vote


def tally(db: Session, campaign: Campaign) -> GovernanceTally:
    options = governance_options(campaign)
    rows = list(
        db.execute(
            select(Vote.choice, func.count(Vote.id), func.sum(Vote.weight))
            .where(Vote.campaign_id == campaign.id, Vote.governance_round == 1)
            .group_by(Vote.choice)
        ).all()
    )
    weighted = (
        campaign.outcome
        and campaign.outcome.voting_weight_mode == VotingWeightMode.CONTRIBUTION_WEIGHTED
    )
    counts = {choice: {"votes": int(count), "weight": float(weight or 0)} for choice, count, weight in rows}

    total_votes = sum(entry["votes"] for entry in counts.values())
    total_weight = sum(entry["weight"] for entry in counts.values())
    denominator = total_weight if weighted else total_votes

    results: dict[str, dict[str, Any]] = {}
    for option in options:
        entry = counts.get(option, {"votes": 0, "weight": 0.0})
        share = entry["weight"] if weighted else entry["votes"]
        results[option] = {
            "votes": entry["votes"],
            "weight": round(entry["weight"], 2),
            "percentage": round(share / denominator * 100, 1) if denominator else 0.0,
        }

    eligible = count_eligible_voters(db, campaign.id)
    leading = max(results.items(), key=lambda kv: kv[1]["percentage"], default=(None, {}))[0]
    if total_votes == 0:
        leading = None

    return GovernanceTally(
        campaign_public_id=campaign.public_id,
        status=campaign.governance_status,
        is_open=campaign.governance_status == GovernanceStatus.OPEN
        and (not campaign.governance_closes_at or utcnow() <= campaign.governance_closes_at),
        closes_at=campaign.governance_closes_at.isoformat() if campaign.governance_closes_at else None,
        total_eligible_voters=eligible,
        votes_cast=total_votes,
        participation_percentage=round(total_votes / eligible * 100, 1) if eligible else 0.0,
        results=results,
        leading_choice=leading,
        selected_outcome=campaign.outcome.selected_outcome if campaign.outcome else None,
        weight_mode=(
            campaign.outcome.voting_weight_mode
            if campaign.outcome
            else str(VotingWeightMode.ONE_PERSON_ONE_VOTE)
        ),
        options=options,
    )


def close_governance(db: Session, campaign: Campaign, actor_id: int | None = None) -> Campaign:
    """Close voting, apply the winning outcome, anchor the result."""
    from app.services import blockchain_service, campaign_service  # local import avoids a cycle

    if campaign.status != CampaignStatus.GOVERNANCE:
        raise ConflictError("This campaign has no open governance round.")
    if campaign.governance_status == GovernanceStatus.CLOSED:
        raise ConflictError("This governance round is already closed.")

    result = tally(db, campaign)
    campaign.governance_status = GovernanceStatus.CLOSED
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.VOTING_CLOSED,
        actor_id=actor_id,
        metadata={
            "votes_cast": result.votes_cast,
            "eligible": result.total_eligible_voters,
            "results": result.results,
        },
    )
    blockchain_service.close_voting_on_chain(db, campaign)

    # No votes cast: the platform does not invent a decision. The predefined
    # default (refund the contributors) applies.
    decision = result.leading_choice or str(VoteChoice.REFUND)
    if campaign.outcome:
        campaign.outcome.selected_outcome = decision
        campaign.outcome.executed_at = utcnow()

    if decision == str(VoteChoice.CONTINUE):
        campaign_state.transition(campaign, CampaignStatus.CONTINUED)
        db.flush()
        config = (campaign.outcome.configuration if campaign.outcome else None) or {}
        extension_days = int(config.get("extension_days") or settings.governance_extension_days)
        campaign_service.extend_deadline(db, campaign, extension_days, actor_id)
        # A continued campaign accepts contributions again for the extended window.
        campaign_state.transition(campaign, CampaignStatus.LIVE)
        db.flush()
        audit_service.record_both(
            db,
            campaign_id=campaign.id,
            action=EventType.CAMPAIGN_CONTINUED,
            actor_id=actor_id,
            metadata={"extension_days": extension_days, "decision": decision},
        )
    else:
        campaign_state.transition(campaign, CampaignStatus.REFUND_PENDING)
        db.flush()
        mark_contributions_refund_pending(db, campaign)
        audit_service.record_both(
            db,
            campaign_id=campaign.id,
            action=EventType.REFUND_REQUESTED,
            actor_id=actor_id,
            metadata={
                "decision": decision,
                "note": "Refunds are processed by payment infrastructure, not on chain.",
            },
        )

    blockchain_service.record_outcome_on_chain(db, campaign, decision)
    return campaign


def mark_contributions_refund_pending(db: Session, campaign: Campaign) -> int:
    """Flag contributions for refund. The money itself moves via PaymentService."""
    rows = list(
        db.execute(
            select(Contribution).where(
                Contribution.campaign_id == campaign.id,
                Contribution.status.in_(VERIFIED_CONTRIBUTION_STATUSES),
            )
        ).scalars().all()
    )
    for contribution in rows:
        contribution.status = ContributionStatus.REFUND_PENDING
    db.flush()
    return len(rows)


def process_refunds(db: Session, campaign: Campaign, actor_id: int | None = None) -> dict[str, Any]:
    """Execute refunds through the payment provider (never through the chain)."""
    from app.services import payment_service  # local import avoids a cycle

    rows = list(
        db.execute(
            select(Contribution).where(
                Contribution.campaign_id == campaign.id,
                Contribution.status == str(ContributionStatus.REFUND_PENDING),
            )
        ).scalars().all()
    )
    initiated, skipped, failed = 0, 0, 0
    for contribution in rows:
        try:
            result = payment_service.refund_contribution(db, contribution)
            # A refund already in flight or already settled is not a new one.
            # Counting it as initiated would overstate what this pass did.
            if result.status in ("already_in_flight", "already_refunded"):
                skipped += 1
            else:
                initiated += 1
        except Exception as exc:
            failed += 1
            logger.error("refund_failed", contribution_id=contribution.id, error=str(exc))
    db.flush()

    if initiated or failed:
        # REQUESTED, not COMPLETED: this pass asked the gateway. A real provider
        # settles asynchronously, and calling that "completed" would claim the
        # money is back when it is still in flight. REFUND_COMPLETED is recorded
        # once, by close_if_refunds_settled, when it actually is.
        audit_service.record_event(
            db,
            campaign_id=campaign.id,
            event_type=EventType.REFUND_REQUESTED,
            actor_id=actor_id,
            metadata={
                "initiated": initiated,
                "skipped": skipped,
                "failed": failed,
                "stage": "execution",
            },
        )
    close_if_refunds_settled(db, campaign)
    return {
        "initiated": initiated,
        "skipped": skipped,
        "failed": failed,
        "total": len(rows),
    }


def close_if_refunds_settled(db: Session, campaign: Campaign) -> bool:
    """Close a refunding campaign once every contributor has been made whole.

    Safe to call repeatedly and from anywhere a single refund settles, which is
    why it checks the remaining work rather than counting completions.
    """
    if campaign.status != CampaignStatus.REFUND_PENDING:
        return False
    outstanding = db.execute(
        select(func.count(Contribution.id)).where(
            Contribution.campaign_id == campaign.id,
            Contribution.status == str(ContributionStatus.REFUND_PENDING),
        )
    ).scalar_one()
    if int(outstanding) > 0:
        return False

    campaign_state.transition(campaign, CampaignStatus.CLOSED)
    db.flush()
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.REFUND_COMPLETED,
        metadata={"note": "Every contribution refunded; campaign closed."},
    )
    logger.info("campaign_closed_after_refunds", campaign_id=campaign.id)
    return True


def process_due_refunds(db: Session, limit: int = 50) -> int:
    """Worker pass: execute the refunds a decided outcome has already ordered.

    This is the only path that moves money outward without a human, so it is
    deliberately narrow: campaigns already in REFUND_PENDING, meaning the
    decision was made by a vote or by the campaign's own predefined rule.

    Serialised with an advisory lock because the API and the worker container
    both run this loop. `refund_contribution` guards each payment individually
    as well — the lock avoids the wasted contention, the per-payment guard is
    what actually makes a double refund impossible.
    """
    if not settings.auto_process_refunds:
        return 0

    with advisory_lock(REFUND_LOCK_KEY) as acquired:
        if not acquired:
            logger.debug("refund_sweep_skipped", reason="another worker holds the lock")
            return 0
        due = list(
            db.execute(
                select(Campaign)
                .where(Campaign.status == str(CampaignStatus.REFUND_PENDING))
                .limit(limit)
            ).scalars().all()
        )
        refunded = 0
        for campaign in due:
            try:
                refunded += process_refunds(db, campaign)["initiated"]
            except Exception as exc:  # pragma: no cover - defensive
                logger.error("refund_sweep_failed", campaign_id=campaign.id, error=str(exc))
                db.rollback()
        if due:
            db.commit()
        return refunded


def process_due_governance(db: Session, limit: int = 50) -> int:
    """Worker pass: close every governance round whose deadline has passed."""
    stmt = (
        select(Campaign)
        .where(
            Campaign.status == str(CampaignStatus.GOVERNANCE),
            Campaign.governance_status == str(GovernanceStatus.OPEN),
            Campaign.governance_closes_at <= utcnow(),
        )
        .limit(limit)
    )
    due = list(db.execute(stmt).scalars().all())
    for campaign in due:
        try:
            close_governance(db, campaign)
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("governance_close_failed", campaign_id=campaign.id, error=str(exc))
    if due:
        db.commit()
    return len(due)


def voter_context(db: Session, campaign: Campaign, user: User | None) -> dict[str, Any]:
    """What the current viewer may do in this governance round."""
    if user is None:
        return {"is_eligible": False, "has_voted": False, "vote": None, "reason": "not_signed_in"}
    eligible = is_eligible(db, campaign.id, user.id)
    vote = existing_vote(db, campaign.id, user.id)
    return {
        "is_eligible": eligible,
        "has_voted": vote is not None,
        "vote": (
            {
                "choice": vote.choice,
                "weight": float(vote.weight),
                "created_at": vote.created_at.isoformat(),
                "blockchain_tx": vote.blockchain_tx,
            }
            if vote
            else None
        ),
        "reason": None if eligible else "no_verified_contribution",
    }
