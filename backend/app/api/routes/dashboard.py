"""Creator and contributor dashboard aggregates."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter
from sqlalchemy import func, or_, select

from app.api import serializers
from app.core.deps import ContributorUser, CreatorOrAdmin, CurrentUser, DbSession
from app.core.enums import CampaignStatus, ContributionStatus, GovernanceStatus
from app.models.campaign import Campaign
from app.models.community import Feedback
from app.models.governance import Vote
from app.models.payment import Contribution
from app.services import campaign_service, sentiment_service

router = APIRouter(prefix="/api", tags=["Campaigns"])

VERIFIED = [
    str(ContributionStatus.PAYMENT_VERIFIED),
    str(ContributionStatus.BLOCKCHAIN_PENDING),
    str(ContributionStatus.BLOCKCHAIN_RECORDED),
]


@router.get("/creator/dashboard")
def creator_dashboard(user: CreatorOrAdmin, db: DbSession) -> dict:
    campaigns = campaign_service.list_creator_campaigns(db, user.id)
    campaign_ids = [c.id for c in campaigns]

    total_raised = Decimal("0")
    contributors = 0
    if campaign_ids:
        total_raised = Decimal(
            db.execute(
                select(func.sum(Contribution.amount)).where(
                    Contribution.campaign_id.in_(campaign_ids),
                    Contribution.status.in_(VERIFIED),
                )
            ).scalar_one_or_none()
            or 0
        )
        contributors = int(
            db.execute(
                select(func.count(func.distinct(Contribution.contributor_id))).where(
                    Contribution.campaign_id.in_(campaign_ids),
                    Contribution.status.in_(VERIFIED),
                )
            ).scalar_one()
        )

    average_rating = None
    positive_percentage = 0.0
    if campaign_ids:
        average_rating = db.execute(
            select(func.avg(Feedback.rating)).where(Feedback.campaign_id.in_(campaign_ids))
        ).scalar_one_or_none()
        totals = [sentiment_service.aggregate_campaign_sentiment(db, cid) for cid in campaign_ids]
        analysed = [t for t in totals if t.analyzed_count]
        if analysed:
            positive_percentage = round(
                sum(t.positive_percentage for t in analysed) / len(analysed), 1
            )

    rows = []
    health_scores: list[int] = []
    risk_levels: list[str] = []
    for campaign in campaigns:
        summary = serializers.campaign_summary(db, campaign, with_health=True)
        stats = sentiment_service.aggregate_campaign_sentiment(db, campaign.id)
        if summary.health_score is not None:
            health_scores.append(summary.health_score)
        health = campaign_service.campaign_health(db, campaign)
        if health.signals.get("ai_risk_level"):
            risk_levels.append(health.signals["ai_risk_level"])
        rows.append(
            {
                **summary.model_dump(mode="json"),
                "positive_percentage": stats.positive_percentage,
                "feedback_count": stats.feedback_count,
                "approval_status": campaign.approval_status,
                "governance_status": campaign.governance_status,
            }
        )

    def dominant_risk() -> str | None:
        if not risk_levels:
            return None
        for level in ("High", "Medium", "Low"):
            if level in risk_levels:
                return level
        return None

    return {
        "cards": {
            "active_campaigns": sum(
                1
                for c in campaigns
                if c.status in (CampaignStatus.LIVE, CampaignStatus.CONTINUED)
            ),
            "total_campaigns": len(campaigns),
            "total_raised": str(total_raised),
            "contributors": contributors,
            "average_rating": round(float(average_rating), 2) if average_rating else None,
            "positive_sentiment": positive_percentage,
            "average_health": int(sum(health_scores) / len(health_scores)) if health_scores else None,
            "ai_risk_level": dominant_risk(),
        },
        "campaigns": rows,
    }


@router.get("/creator/campaigns/{public_id}/analytics")
def campaign_analytics(public_id: str, user: CreatorOrAdmin, db: DbSession) -> dict:
    """Funding series, contribution history and community signals for one campaign."""
    campaign = campaign_service.get_by_public_id(db, public_id)
    if campaign.creator_id != user.id and user.role != "ADMIN":
        campaign_service.assert_owner(campaign, user)

    contributions = db.execute(
        select(Contribution)
        .where(Contribution.campaign_id == campaign.id, Contribution.status.in_(VERIFIED))
        .order_by(Contribution.created_at.asc())
    ).scalars().all()

    running = Decimal("0")
    series = []
    for contribution in contributions:
        running += Decimal(contribution.amount)
        series.append(
            {
                "date": contribution.created_at.date().isoformat(),
                "amount": float(contribution.amount),
                "cumulative": float(running),
            }
        )

    health = campaign_service.campaign_health(db, campaign)
    return {
        "campaign": serializers.campaign_summary(db, campaign, with_health=True).model_dump(mode="json"),
        "funding_series": series,
        "contribution_count": len(contributions),
        "sentiment": serializers.sentiment_summary(db, campaign.id).model_dump(mode="json"),
        "health": {
            "score": health.score,
            "label": health.label,
            "financial_score": health.financial_score,
            "community_score": health.community_score,
            "ai_score": health.ai_score,
            "signals": health.signals,
        },
        "blockchain": serializers.blockchain_summary(db, campaign).model_dump(mode="json"),
    }


@router.get("/contributor/dashboard")
def contributor_dashboard(user: CurrentUser, db: DbSession) -> dict:
    contributions = db.execute(
        select(Contribution)
        .where(Contribution.contributor_id == user.id)
        .order_by(Contribution.id.desc())
    ).scalars().all()

    total = sum(
        (Decimal(c.amount) for c in contributions if c.status in VERIFIED), Decimal("0")
    )
    campaign_ids = {c.campaign_id for c in contributions}

    open_votes = db.execute(
        select(Campaign)
        .where(
            Campaign.id.in_(campaign_ids or {0}),
            Campaign.status == str(CampaignStatus.GOVERNANCE),
            Campaign.governance_status == str(GovernanceStatus.OPEN),
        )
    ).scalars().all()
    votes = db.execute(
        select(Vote).where(Vote.contributor_id == user.id).order_by(Vote.id.desc())
    ).scalars().all()
    voted_campaigns = {v.campaign_id for v in votes}

    return {
        "cards": {
            "total_contributed": str(total),
            "campaigns_supported": len(campaign_ids),
            "contributions": len(contributions),
            "blockchain_recorded": sum(
                1
                for c in contributions
                if c.status == str(ContributionStatus.BLOCKCHAIN_RECORDED)
            ),
            "open_votes": sum(1 for c in open_votes if c.id not in voted_campaigns),
        },
        "recent_contributions": [
            serializers.contribution_response(db, c).model_dump(mode="json")
            for c in contributions[:10]
        ],
        "active_votes": [
            {
                "public_id": c.public_id,
                "title": c.title,
                "closes_at": c.governance_closes_at.isoformat() if c.governance_closes_at else None,
                "has_voted": c.id in voted_campaigns,
                "raised_amount": str(c.raised_amount),
                "target_amount": str(c.target_amount),
            }
            for c in open_votes
        ],
        "past_votes": [
            serializers.vote_response(v, v.campaign).model_dump(mode="json") for v in votes[:10]
        ],
    }


@router.get("/profile")
def profile(user: CurrentUser, db: DbSession) -> dict:
    """Everything one account owns: identity, money, and its on-chain trail.

    The contributor dashboard answers "what should I do next"; this answers
    "what has been recorded about me". It therefore joins the three stores the
    platform writes to — Postgres for the contribution, the gateway reference on
    the payment, and the anchoring transaction — so a contributor can follow one
    payment from rupees to block number without trusting a summary.
    """
    from app.models.chain import BlockchainTransaction  # noqa: PLC0415
    from app.models.user import KYCVerification  # noqa: PLC0415

    contributions = list(
        db.execute(
            select(Contribution)
            .where(Contribution.contributor_id == user.id)
            .order_by(Contribution.id.desc())
        ).scalars().all()
    )
    votes = list(
        db.execute(
            select(Vote).where(Vote.contributor_id == user.id).order_by(Vote.id.desc())
        ).scalars().all()
    )

    verified_total = sum(
        (Decimal(c.amount) for c in contributions if c.status in VERIFIED), Decimal("0")
    )
    anchored = [
        c for c in contributions if c.status == str(ContributionStatus.BLOCKCHAIN_RECORDED)
    ]
    awaiting = [
        c
        for c in contributions
        if c.status
        in (str(ContributionStatus.BLOCKCHAIN_PENDING), str(ContributionStatus.PAYMENT_VERIFIED))
    ]

    # Every anchoring transaction this user caused: their contributions and
    # their votes. Campaign-level records (registration, voting opened/closed)
    # belong to the campaign, not to a person, so they are deliberately absent.
    contribution_ids = [c.id for c in contributions]
    vote_ids = [v.id for v in votes]
    records: list[BlockchainTransaction] = []
    if contribution_ids or vote_ids:
        clauses = []
        if contribution_ids:
            clauses.append(BlockchainTransaction.contribution_id.in_(contribution_ids))
        if vote_ids:
            clauses.append(BlockchainTransaction.vote_id.in_(vote_ids))
        records = list(
            db.execute(
                select(BlockchainTransaction)
                .where(or_(*clauses))
                .order_by(BlockchainTransaction.id.desc())
            ).scalars().all()
        )

    kyc = db.execute(
        select(KYCVerification)
        .where(KYCVerification.user_id == user.id)
        .order_by(KYCVerification.id.desc())
        .limit(1)
    ).scalars().first()

    campaign_titles = {
        c.id: (c.public_id, c.title)
        for c in db.execute(
            select(Campaign).where(
                Campaign.id.in_({r.campaign_id for r in records} or {0})
            )
        ).scalars().all()
    }

    return {
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "wallet_address": user.wallet_address,
            "is_active": user.is_active,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "kyc_status": kyc.status if kyc else None,
            "kyc_verified_at": (
                kyc.verified_at.isoformat() if kyc and kyc.verified_at else None
            ),
        },
        "stats": {
            "total_contributed": str(verified_total),
            "contributions": len(contributions),
            "campaigns_supported": len({c.campaign_id for c in contributions}),
            "votes_cast": len(votes),
            "anchored_on_chain": len(anchored),
            "awaiting_anchor": len(awaiting),
            "chain_records": len(records),
            "first_contribution_at": (
                contributions[-1].created_at.isoformat() if contributions else None
            ),
            "last_contribution_at": (
                contributions[0].created_at.isoformat() if contributions else None
            ),
        },
        "contributions": [
            serializers.contribution_response(db, c).model_dump(mode="json")
            for c in contributions
        ],
        "chain_records": [
            {
                **serializers.blockchain_record(record).model_dump(mode="json"),
                "campaign_public_id": campaign_titles.get(record.campaign_id, (None, None))[0],
                "campaign_title": campaign_titles.get(record.campaign_id, (None, None))[1],
            }
            for record in records
        ],
        "votes": [
            serializers.vote_response(v, v.campaign).model_dump(mode="json") for v in votes
        ],
    }
