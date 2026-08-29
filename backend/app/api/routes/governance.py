"""Governance routes: view the round, cast a vote, close the round."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import select

from app.api import serializers
from app.core.deps import CSRFProtected, CurrentUser, DbSession, OptionalUser
from app.core.enums import BlockchainRecordType, UserRole
from app.core.errors import PermissionDeniedError
from app.models.chain import BlockchainTransaction
from app.models.governance import Vote
from app.schemas.common import Page
from app.schemas.payment import GovernanceResponse, VoteRequest, VoteResponse
from app.services import campaign_service, governance_service

router = APIRouter(prefix="/api", tags=["Governance"])

_GOVERNANCE_RECORD_TYPES = [
    str(BlockchainRecordType.VOTING_OPENED),
    str(BlockchainRecordType.VOTE),
    str(BlockchainRecordType.VOTING_CLOSED),
    str(BlockchainRecordType.OUTCOME),
]


def _governance_response(db, campaign, user) -> GovernanceResponse:
    tally = governance_service.tally(db, campaign)
    records = db.execute(
        select(BlockchainTransaction)
        .where(
            BlockchainTransaction.campaign_id == campaign.id,
            BlockchainTransaction.record_type.in_(_GOVERNANCE_RECORD_TYPES),
        )
        .order_by(BlockchainTransaction.id.desc())
        .limit(25)
    ).scalars().all()
    return GovernanceResponse(
        campaign_public_id=campaign.public_id,
        campaign_title=campaign.title,
        campaign_status=campaign.status,
        status=tally.status,
        is_open=tally.is_open,
        closes_at=tally.closes_at,
        total_eligible_voters=tally.total_eligible_voters,
        votes_cast=tally.votes_cast,
        participation_percentage=tally.participation_percentage,
        results=tally.results,
        leading_choice=tally.leading_choice,
        selected_outcome=tally.selected_outcome,
        weight_mode=tally.weight_mode,
        options=tally.options,
        target_amount=campaign.target_amount,
        raised_amount=campaign.raised_amount,
        shortfall=max(
            Decimal(campaign.target_amount) - Decimal(campaign.raised_amount), Decimal("0")
        ),
        viewer=governance_service.voter_context(db, campaign, user),
        blockchain_records=[serializers.blockchain_record(r) for r in records],
    )


@router.get("/campaigns/{public_id}/governance", response_model=GovernanceResponse)
def get_governance(public_id: str, db: DbSession, user: OptionalUser) -> GovernanceResponse:
    campaign = campaign_service.get_public(db, public_id)
    return _governance_response(db, campaign, user)


@router.post(
    "/campaigns/{public_id}/vote", response_model=GovernanceResponse, dependencies=[CSRFProtected]
)
def cast_vote(
    public_id: str, payload: VoteRequest, user: CurrentUser, db: DbSession
) -> GovernanceResponse:
    """Cast one vote.

    Rejected for: non-contributors, a second vote, a closed or expired round, and
    any choice outside the campaign's predefined options.
    """
    campaign = campaign_service.get_public(db, public_id)
    governance_service.cast_vote(db, campaign, user, str(payload.choice))
    db.commit()
    db.refresh(campaign)
    return _governance_response(db, campaign, user)


@router.post(
    "/campaigns/{public_id}/governance/close",
    response_model=GovernanceResponse,
    dependencies=[CSRFProtected],
)
def close_governance(public_id: str, user: CurrentUser, db: DbSession) -> GovernanceResponse:
    """Close the round and apply the winning outcome. Admin only."""
    if user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Only an administrator can close a governance round.")
    campaign = campaign_service.get_public(db, public_id)
    governance_service.close_governance(db, campaign, actor_id=user.id)
    db.commit()
    db.refresh(campaign)
    return _governance_response(db, campaign, user)


@router.get("/votes/my", response_model=Page[VoteResponse])
def my_votes(user: CurrentUser, db: DbSession, limit: int = 20, offset: int = 0) -> Page[VoteResponse]:
    stmt = select(Vote).where(Vote.contributor_id == user.id)
    total = len(db.execute(stmt).scalars().all())
    rows = db.execute(stmt.order_by(Vote.id.desc()).limit(limit).offset(offset)).scalars().all()
    return Page[VoteResponse](
        items=[serializers.vote_response(vote, vote.campaign) for vote in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
