"""Community feedback.

Feedback is created synchronously; classification happens in the background so a
contributor is never left waiting on a model. The list endpoint is paginated —
a campaign with 500 comments must never be loaded in one response.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.enums import PUBLIC_CAMPAIGN_STATUSES, EventType, Sentiment
from app.core.errors import ConflictError, ValidationError
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.community import Feedback
from app.models.user import User
from app.services import audit_service

logger = get_logger(__name__)

MIN_LENGTH = 10
MAX_LENGTH = 2000


def create_feedback(
    db: Session, campaign: Campaign, user: User, text: str, rating: int
) -> Feedback:
    if campaign.status not in PUBLIC_CAMPAIGN_STATUSES:
        raise ConflictError("Feedback can only be left on a published campaign.")
    if not 1 <= int(rating) <= 5:
        raise ValidationError("Rating must be between 1 and 5.")
    cleaned = (text or "").strip()
    if len(cleaned) < MIN_LENGTH:
        raise ValidationError(f"Feedback must be at least {MIN_LENGTH} characters.")
    if len(cleaned) > MAX_LENGTH:
        raise ValidationError(f"Feedback must be at most {MAX_LENGTH} characters.")
    if campaign.creator_id == user.id:
        raise ConflictError("A creator cannot leave feedback on their own campaign.")

    feedback = Feedback(
        campaign_id=campaign.id,
        contributor_id=user.id,
        text=cleaned,
        rating=int(rating),
        sentiment=str(Sentiment.PENDING),  # classified by the background task
    )
    db.add(feedback)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise ConflictError("You have already left feedback on this campaign.") from exc

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.FEEDBACK_CREATED,
        actor_id=user.id,
        metadata={"feedback_id": feedback.id, "rating": rating},
    )
    return feedback


def list_feedback(
    db: Session,
    campaign_id: int,
    *,
    sentiment: str | None = None,
    aspect: str | None = None,
    limit: int = 10,
    offset: int = 0,
) -> tuple[list[Feedback], int]:
    stmt = select(Feedback).where(Feedback.campaign_id == campaign_id)
    if sentiment:
        stmt = stmt.where(Feedback.sentiment == sentiment)
    if aspect:
        stmt = stmt.where(Feedback.aspect == aspect)
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = list(
        db.execute(stmt.order_by(Feedback.id.desc()).limit(limit).offset(offset)).scalars().all()
    )
    return rows, total


def get_user_feedback(db: Session, campaign_id: int, user_id: int) -> Feedback | None:
    return db.execute(
        select(Feedback).where(
            Feedback.campaign_id == campaign_id, Feedback.contributor_id == user_id
        )
    ).scalars().first()
