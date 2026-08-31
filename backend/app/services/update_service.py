"""Campaign updates: the creator's running account of what they are doing.

Feedback flows from the community to the creator and is scored for sentiment.
Updates flow the other way — outreach, milestones, setbacks — and are never
classified or fed to a model, because an update is not evidence *about* the
campaign, it is the campaign speaking. Keeping the two apart is what stops a
creator's own words inflating the sentiment their campaign is judged by.
"""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import utcnow
from app.core.enums import PUBLIC_CAMPAIGN_STATUSES, EventType, UserRole
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.models.campaign import Campaign
from app.models.community import CampaignUpdate
from app.models.user import User
from app.services import audit_service

logger = get_logger(__name__)

TITLE_MIN = 4
TITLE_MAX = 140
BODY_MIN = 20
BODY_MAX = 5000


def _clean(title: str, body: str) -> tuple[str, str]:
    title = (title or "").strip()
    body = (body or "").strip()
    if not TITLE_MIN <= len(title) <= TITLE_MAX:
        raise ValidationError(
            f"Title must be between {TITLE_MIN} and {TITLE_MAX} characters."
        )
    if not BODY_MIN <= len(body) <= BODY_MAX:
        raise ValidationError(
            f"Update must be between {BODY_MIN} and {BODY_MAX} characters."
        )
    return title, body


def assert_can_write(campaign: Campaign, user: User) -> None:
    """Only the campaign's own creator, or an admin acting for them."""
    if user.role == UserRole.ADMIN:
        return
    if campaign.creator_id != user.id:
        raise PermissionDeniedError("Only the campaign creator can post updates.")


def create_update(
    db: Session, campaign: Campaign, user: User, title: str, body: str
) -> CampaignUpdate:
    assert_can_write(campaign, user)
    # Posting before publication would be shouting into an empty room, and the
    # public list would leak an unapproved campaign's activity.
    if campaign.status not in PUBLIC_CAMPAIGN_STATUSES:
        raise ConflictError(
            "Updates can only be posted once the campaign is published.",
            details={"status": campaign.status},
        )
    title, body = _clean(title, body)

    update = CampaignUpdate(
        campaign_id=campaign.id, author_id=user.id, title=title, body=body
    )
    db.add(update)
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_UPDATE_POSTED,
        actor_id=user.id,
        metadata={"update_id": update.id, "title": title},
    )
    logger.info("campaign_update_posted", campaign_id=campaign.id, update_id=update.id)
    return update


def get_update(db: Session, campaign_id: int, update_id: int) -> CampaignUpdate:
    update = db.execute(
        select(CampaignUpdate).where(
            CampaignUpdate.id == update_id, CampaignUpdate.campaign_id == campaign_id
        )
    ).scalars().first()
    if update is None:
        raise NotFoundError("Update not found.")
    return update


def edit_update(
    db: Session,
    campaign: Campaign,
    user: User,
    update_id: int,
    *,
    title: str | None = None,
    body: str | None = None,
    is_pinned: bool | None = None,
) -> CampaignUpdate:
    assert_can_write(campaign, user)
    update = get_update(db, campaign.id, update_id)

    if title is not None or body is not None:
        new_title, new_body = _clean(
            title if title is not None else update.title,
            body if body is not None else update.body,
        )
        update.title, update.body = new_title, new_body
        # Only a content change counts as an edit; pinning is not a rewrite, and
        # showing "edited" for it would wrongly suggest the text moved.
        update.updated_at = utcnow()

    if is_pinned is not None:
        if is_pinned:
            # At most one pinned update: a second pin silently demoting the first
            # would be indistinguishable from the pin not working.
            for other in db.execute(
                select(CampaignUpdate).where(
                    CampaignUpdate.campaign_id == campaign.id,
                    CampaignUpdate.is_pinned.is_(True),
                    CampaignUpdate.id != update.id,
                )
            ).scalars().all():
                other.is_pinned = False
        update.is_pinned = bool(is_pinned)

    db.flush()
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_UPDATE_EDITED,
        actor_id=user.id,
        metadata={"update_id": update.id, "pinned": update.is_pinned},
    )
    return update


def delete_update(db: Session, campaign: Campaign, user: User, update_id: int) -> None:
    assert_can_write(campaign, user)
    update = get_update(db, campaign.id, update_id)
    title = update.title
    db.delete(update)
    db.flush()
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CAMPAIGN_UPDATE_DELETED,
        actor_id=user.id,
        metadata={"update_id": update_id, "title": title},
    )


def list_updates(
    db: Session, campaign_id: int, *, limit: int = 10, offset: int = 0
) -> tuple[list[CampaignUpdate], int]:
    """Newest first, with any pinned update held at the top."""
    stmt = select(CampaignUpdate).where(CampaignUpdate.campaign_id == campaign_id)
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = list(
        db.execute(
            stmt.order_by(CampaignUpdate.is_pinned.desc(), CampaignUpdate.id.desc())
            .limit(limit)
            .offset(offset)
        ).scalars().all()
    )
    return rows, total


def count_updates(db: Session, campaign_id: int) -> int:
    return int(
        db.execute(
            select(func.count(CampaignUpdate.id)).where(
                CampaignUpdate.campaign_id == campaign_id
            )
        ).scalar_one()
    )
