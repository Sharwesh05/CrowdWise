"""Public campaign discovery and the campaign page.

Everything here is reachable without authentication, so every response goes
through the `public_campaign` projection — creator contact details, payment
identifiers and KYC data are structurally unable to appear.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, Response
from sqlalchemy import select

from app.api import serializers
from app.core.deps import DbSession, OptionalUser
from app.core.enums import CampaignCategory, ContributionStatus
from app.core.errors import NotFoundError
from app.models.chain import BlockchainTransaction
from app.models.payment import Contribution
from app.schemas.campaign import CampaignSummary, PublicCampaign, QRResponse
from app.schemas.common import Page
from app.schemas.payment import BlockchainRecord, ContributionPublic, FeedbackResponse
from app.services import campaign_service, feedback_service, qr_service

router = APIRouter(prefix="/api/public", tags=["Public"])


@router.get("/campaigns", response_model=Page[CampaignSummary])
def list_campaigns(
    db: DbSession,
    search: str | None = Query(default=None, max_length=120),
    category: CampaignCategory | None = None,
    status: str | None = None,
    sort: str = Query(default="trending", pattern="^(trending|newest|progress|most_supported|ending_soon)$"),
    limit: int = Query(default=12, ge=1, le=48),
    offset: int = Query(default=0, ge=0),
) -> Page[CampaignSummary]:
    campaigns, total = campaign_service.list_public_campaigns(
        db,
        search=search,
        category=str(category) if category else None,
        status=status,
        sort=sort,
        limit=limit,
        offset=offset,
    )
    return Page[CampaignSummary](
        items=[serializers.campaign_summary(db, c, with_health=True) for c in campaigns],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/campaigns/{public_id}", response_model=PublicCampaign)
def get_campaign(public_id: str, db: DbSession, user: OptionalUser) -> PublicCampaign:
    return serializers.public_campaign(db, campaign_service.get_public(db, public_id))


@router.get("/campaigns/{public_id}/qr.png", response_class=Response)
def campaign_qr_png(public_id: str, db: DbSession) -> Response:
    """Downloadable, print-ready QR pointing at the public campaign URL."""
    campaign = campaign_service.get_public(db, public_id)
    _, png = qr_service.build_campaign_qr(campaign.public_id)
    return Response(
        content=png,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="crowdwise-{campaign.public_id}-qr.png"',
            "Cache-Control": "public, max-age=3600",
        },
    )


@router.get("/campaigns/{public_id}/qr", response_model=QRResponse)
def campaign_qr(public_id: str, db: DbSession) -> QRResponse:
    campaign = campaign_service.get_public(db, public_id)
    return QRResponse(
        public_id=campaign.public_id,
        campaign_url=qr_service.campaign_url(campaign.public_id),
        qr_token=None,  # the token is owner-only; the URL is what the QR carries
        qr_image_data_uri=qr_service.qr_data_uri(campaign.public_id),
        download_url=f"/api/public/campaigns/{campaign.public_id}/qr.png",
    )


@router.get("/campaigns/{public_id}/feedback", response_model=Page[FeedbackResponse])
def list_feedback(
    public_id: str,
    db: DbSession,
    sentiment: str | None = None,
    aspect: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> Page[FeedbackResponse]:
    """Paginated: a campaign with 500 comments is never loaded in one response."""
    campaign = campaign_service.get_public(db, public_id)
    rows, total = feedback_service.list_feedback(
        db, campaign.id, sentiment=sentiment, aspect=aspect, limit=limit, offset=offset
    )
    return Page[FeedbackResponse](
        items=[serializers.feedback_response(row, include_author=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/campaigns/{public_id}/contributions", response_model=Page[ContributionPublic])
def list_contributions(
    public_id: str,
    db: DbSession,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> Page[ContributionPublic]:
    campaign = campaign_service.get_public(db, public_id)
    stmt = select(Contribution).where(
        Contribution.campaign_id == campaign.id,
        Contribution.status.in_(
            [
                str(ContributionStatus.PAYMENT_VERIFIED),
                str(ContributionStatus.BLOCKCHAIN_PENDING),
                str(ContributionStatus.BLOCKCHAIN_RECORDED),
            ]
        ),
    )
    total = len(db.execute(stmt).scalars().all())
    rows = db.execute(
        stmt.order_by(Contribution.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page[ContributionPublic](
        items=[serializers.contribution_public(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/campaigns/{public_id}/blockchain", response_model=list[BlockchainRecord])
def campaign_blockchain(public_id: str, db: DbSession) -> list[BlockchainRecord]:
    campaign = campaign_service.get_public(db, public_id)
    rows = db.execute(
        select(BlockchainTransaction)
        .where(BlockchainTransaction.campaign_id == campaign.id)
        .order_by(BlockchainTransaction.id.desc())
        .limit(50)
    ).scalars().all()
    return [serializers.blockchain_record(row) for row in rows]


@router.get("/scan/{qr_token}", response_model=PublicCampaign)
def resolve_qr_token(qr_token: str, db: DbSession) -> PublicCampaign:
    """Resolve a scanned QR token to its campaign (fallback for scanner flows)."""
    from app.models.campaign import Campaign

    campaign = db.execute(
        select(Campaign).where(Campaign.qr_token == qr_token)
    ).scalars().first()
    if campaign is None:
        raise NotFoundError("That QR code does not match any campaign.")
    return serializers.public_campaign(db, campaign)


@router.get("/stats")
def platform_stats(db: DbSession) -> dict:
    """Headline numbers for the homepage. Observed values only — nothing invented."""
    from sqlalchemy import func

    from app.models.campaign import Campaign
    from app.models.user import User

    live = int(
        db.execute(
            select(func.count(Campaign.id)).where(Campaign.status.in_(["LIVE", "CONTINUED"]))
        ).scalar_one()
    )
    raised = db.execute(
        select(func.sum(Contribution.amount)).where(
            Contribution.status.in_(
                [
                    str(ContributionStatus.PAYMENT_VERIFIED),
                    str(ContributionStatus.BLOCKCHAIN_PENDING),
                    str(ContributionStatus.BLOCKCHAIN_RECORDED),
                ]
            )
        )
    ).scalar_one_or_none()
    contributors = int(
        db.execute(
            select(func.count(func.distinct(Contribution.contributor_id)))
        ).scalar_one()
    )
    creators = int(
        db.execute(select(func.count(User.id)).where(User.role == "CREATOR")).scalar_one()
    )
    anchored = int(
        db.execute(select(func.count(BlockchainTransaction.id))).scalar_one()
    )
    return {
        "live_campaigns": live,
        "total_raised": str(raised or 0),
        "contributors": contributors,
        "verified_creators": creators,
        "blockchain_records": anchored,
    }
