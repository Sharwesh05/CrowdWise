"""Feedback and community intelligence routes."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Query

from app.api import serializers
from app.core.db import session_scope
from app.core.deps import CSRFProtected, CurrentUser, DbSession
from app.core.errors import NotFoundError
from app.schemas.campaign import (
    CampaignUpdateCreateRequest,
    CampaignUpdateEditRequest,
    CampaignUpdateResponse,
    CommunityInsightResponse,
    SentimentSummary,
)
from app.schemas.common import MessageResponse, Page
from app.schemas.payment import FeedbackCreateRequest, FeedbackResponse
from app.services import (
    ai_service,
    campaign_service,
    feedback_service,
    sentiment_service,
    update_service,
)

router = APIRouter(prefix="/api/campaigns", tags=["Feedback"])


def _analyze_then_refresh(feedback_id: int, campaign_id: int) -> None:
    """Background: classify the new feedback, then refresh insights if warranted."""
    from app.models.campaign import Campaign
    from app.models.community import Feedback

    db = session_scope()
    try:
        feedback = db.get(Feedback, feedback_id)
        if feedback:
            sentiment_service.analyze_feedback(db, feedback)
            db.commit()
        campaign = db.get(Campaign, campaign_id)
        if campaign and ai_service.should_refresh_insights(db, campaign):
            ai_service.generate_community_insights(db, campaign)
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@router.post(
    "/{public_id}/feedback", response_model=FeedbackResponse, status_code=201, dependencies=[CSRFProtected]
)
def create_feedback(
    public_id: str,
    payload: FeedbackCreateRequest,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> FeedbackResponse:
    """Submit a rating and comment. Sentiment is classified in the background."""
    campaign = campaign_service.get_public(db, public_id)
    feedback = feedback_service.create_feedback(db, campaign, user, payload.text, payload.rating)
    db.commit()
    db.refresh(feedback)
    background.add_task(_analyze_then_refresh, feedback.id, campaign.id)
    return serializers.feedback_response(feedback, include_author=True)


@router.get("/{public_id}/feedback", response_model=Page[FeedbackResponse])
def list_feedback(
    public_id: str,
    db: DbSession,
    sentiment: str | None = None,
    aspect: str | None = None,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> Page[FeedbackResponse]:
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


@router.get("/{public_id}/sentiment", response_model=SentimentSummary)
def campaign_sentiment(public_id: str, db: DbSession) -> SentimentSummary:
    campaign = campaign_service.get_public(db, public_id)
    return serializers.sentiment_summary(db, campaign.id)


@router.get("/{public_id}/community-insights", response_model=CommunityInsightResponse, tags=["AI"])
def community_insights(public_id: str, db: DbSession) -> CommunityInsightResponse:
    campaign = campaign_service.get_public(db, public_id)
    insight = ai_service.latest_insight(db, campaign.id)
    if insight is None:
        raise NotFoundError(
            "Community insights are generated once the campaign has received feedback."
        )
    return serializers.insight_response(insight)


@router.post(
    "/{public_id}/community-insights/refresh",
    response_model=CommunityInsightResponse,
    tags=["AI"],
    dependencies=[CSRFProtected],
)
def refresh_community_insights(
    public_id: str, user: CurrentUser, db: DbSession
) -> CommunityInsightResponse:
    """Force regeneration. Normally the cached insight is reused until enough
    new feedback arrives — one LLM call per community, not per comment."""
    campaign = campaign_service.get_public(db, public_id)
    insight = ai_service.generate_community_insights(db, campaign, actor_id=user.id)
    if insight is None:
        raise NotFoundError("There is no feedback to analyse for this campaign yet.")
    db.commit()
    db.refresh(insight)
    return serializers.insight_response(insight)


# --------------------------------------------------------------------------
# Campaign updates — the creator's side of the conversation
# --------------------------------------------------------------------------
@router.get("/{public_id}/updates", response_model=Page[CampaignUpdateResponse], tags=["Updates"])
def list_updates(
    public_id: str,
    db: DbSession,
    limit: int = Query(default=10, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
) -> Page[CampaignUpdateResponse]:
    """Public: anyone looking at the campaign can read its updates."""
    campaign = campaign_service.get_public(db, public_id)
    rows, total = update_service.list_updates(db, campaign.id, limit=limit, offset=offset)
    return Page(
        items=[serializers.campaign_update_response(u) for u in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{public_id}/updates",
    response_model=CampaignUpdateResponse,
    status_code=201,
    tags=["Updates"],
    dependencies=[CSRFProtected],
)
def post_update(
    public_id: str,
    payload: CampaignUpdateCreateRequest,
    user: CurrentUser,
    db: DbSession,
) -> CampaignUpdateResponse:
    campaign = campaign_service.get_by_public_id(db, public_id)
    update = update_service.create_update(db, campaign, user, payload.title, payload.body)
    db.commit()
    db.refresh(update)
    return serializers.campaign_update_response(update)


@router.patch(
    "/{public_id}/updates/{update_id}",
    response_model=CampaignUpdateResponse,
    tags=["Updates"],
    dependencies=[CSRFProtected],
)
def edit_update(
    public_id: str,
    update_id: int,
    payload: CampaignUpdateEditRequest,
    user: CurrentUser,
    db: DbSession,
) -> CampaignUpdateResponse:
    campaign = campaign_service.get_by_public_id(db, public_id)
    update = update_service.edit_update(
        db,
        campaign,
        user,
        update_id,
        title=payload.title,
        body=payload.body,
        is_pinned=payload.is_pinned,
    )
    db.commit()
    db.refresh(update)
    return serializers.campaign_update_response(update)


@router.delete(
    "/{public_id}/updates/{update_id}",
    response_model=MessageResponse,
    tags=["Updates"],
    dependencies=[CSRFProtected],
)
def delete_update(
    public_id: str, update_id: int, user: CurrentUser, db: DbSession
) -> MessageResponse:
    campaign = campaign_service.get_by_public_id(db, public_id)
    update_service.delete_update(db, campaign, user, update_id)
    db.commit()
    return MessageResponse(message="Update deleted.")
