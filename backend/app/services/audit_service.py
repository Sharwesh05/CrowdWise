"""Audit logging.

Two surfaces, deliberately separate:
  * `campaign_events` — the campaign's own timeline, shown to creators/contributors.
  * `audit_logs`      — the platform-wide actor-oriented record, shown to admins.

Both are written through here so no caller can invent an unlogged state change.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.logging import get_logger, redact
from app.models.campaign import CampaignEvent
from app.models.chain import AuditLog

logger = get_logger(__name__)


def record_event(
    db: Session,
    *,
    campaign_id: int,
    event_type: str,
    actor_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    flush: bool = True,
) -> CampaignEvent:
    event = CampaignEvent(
        campaign_id=campaign_id,
        event_type=str(event_type),
        actor_id=actor_id,
        event_metadata=redact(metadata) if metadata else None,
    )
    db.add(event)
    if flush:
        db.flush()
    logger.info("campaign_event", campaign_id=campaign_id, event_type=str(event_type))
    return event


def record_audit(
    db: Session,
    *,
    action: str,
    actor_id: int | None = None,
    entity_type: str | None = None,
    entity_id: str | int | None = None,
    metadata: dict[str, Any] | None = None,
    ip_address: str | None = None,
    request_id: str | None = None,
    flush: bool = True,
) -> AuditLog:
    log = AuditLog(
        actor_id=actor_id,
        action=str(action),
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        audit_metadata=redact(metadata) if metadata else None,
        ip_address=ip_address,
        request_id=request_id,
    )
    db.add(log)
    if flush:
        db.flush()
    logger.info("audit", action=str(action), entity_type=entity_type, entity_id=str(entity_id))
    return log


def record_both(
    db: Session,
    *,
    campaign_id: int,
    action: str,
    actor_id: int | None = None,
    metadata: dict[str, Any] | None = None,
    request_id: str | None = None,
) -> None:
    """Convenience for state transitions, which belong on both surfaces."""
    record_event(
        db, campaign_id=campaign_id, event_type=action, actor_id=actor_id, metadata=metadata
    )
    record_audit(
        db,
        action=action,
        actor_id=actor_id,
        entity_type="campaign",
        entity_id=campaign_id,
        metadata=metadata,
        request_id=request_id,
    )


def list_audit_logs(
    db: Session,
    *,
    action: str | None = None,
    actor_id: int | None = None,
    entity_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[AuditLog], int]:
    stmt = select(AuditLog)
    if action:
        stmt = stmt.where(AuditLog.action == action)
    if actor_id:
        stmt = stmt.where(AuditLog.actor_id == actor_id)
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    total = len(db.execute(stmt).scalars().all())
    rows = (
        db.execute(stmt.order_by(AuditLog.id.desc()).limit(limit).offset(offset)).scalars().all()
    )
    return list(rows), total


def list_campaign_events(db: Session, campaign_id: int, limit: int = 100) -> list[CampaignEvent]:
    stmt = (
        select(CampaignEvent)
        .where(CampaignEvent.campaign_id == campaign_id)
        .order_by(CampaignEvent.id.desc())
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())
