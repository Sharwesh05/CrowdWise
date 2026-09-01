"""Supporting documents: upload, reader authorisation, and what the AI reads.

Two tiers, and the difference between them is only about *human* readers. The
AI analyst is given both, because a creator who attaches a vendor quote or a
budget to justify a claim wants that claim assessed against the evidence — the
tier says who else gets to look, not whether the model does.

Authorisation lives here rather than in the routers so that a document reachable
from the creator screen, the admin review panel and the public campaign page
cannot end up with three subtly different rules. And no route ever hands out a
raw storage URL for a document: `/api/files` is unauthenticated, so a leaked key
would be a permanent public link to something a creator marked private.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.enums import (
    PUBLIC_CAMPAIGN_STATUSES,
    CampaignStatus,
    DocumentVisibility,
    EventType,
    UserRole,
)
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.logging import get_logger
from app.models.campaign import Campaign, CampaignDocument
from app.models.user import User
from app.services import audit_service, storage_service

logger = get_logger(__name__)

# Enough for a real application; low enough that the prompt cannot be flooded.
MAX_DOCUMENTS_PER_CAMPAIGN = 12


def parse_visibility(raw: str | None) -> str:
    """Resolve the requested tier, defaulting to the more private one."""
    if raw is None or raw == "":
        return str(DocumentVisibility.AI_ONLY)
    try:
        return str(DocumentVisibility(raw.strip().upper()))
    except ValueError as exc:
        raise ValidationError(
            "Visibility must be SHARED (signed-in users can open it) or "
            "AI_ONLY (only you, a reviewing admin and the AI).",
            details={"received": raw},
        ) from exc


def upload(
    db: Session,
    campaign: Campaign,
    user: User,
    *,
    filename: str,
    content: bytes,
    declared_mime: str | None,
    visibility: str,
) -> CampaignDocument:
    if len(campaign.documents) >= MAX_DOCUMENTS_PER_CAMPAIGN:
        raise ValidationError(
            f"A campaign can carry at most {MAX_DOCUMENTS_PER_CAMPAIGN} supporting "
            "documents. Remove one before adding another."
        )

    stored = storage_service.store_upload(
        filename or "document",
        content,
        declared_mime,
        prefix=f"campaigns/{campaign.public_id}",
    )
    text, note = storage_service.extract_text(stored.mime_type, content)

    document = CampaignDocument(
        campaign_id=campaign.id,
        file_name=stored.original_name,
        storage_key=stored.storage_key,
        mime_type=stored.mime_type,
        size=stored.size,
        visibility=visibility,
        extracted_text=text,
        extraction_note=note,
    )
    db.add(document)
    db.flush()

    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.DOCUMENT_UPLOADED,
        actor_id=user.id,
        metadata={
            "document_id": document.id,
            "mime_type": stored.mime_type,
            "visibility": visibility,
            "machine_readable": bool(text),
        },
    )
    logger.info(
        "document_uploaded",
        campaign_id=campaign.id,
        document_id=document.id,
        visibility=visibility,
        extracted_chars=len(text or ""),
    )
    return document


def delete(db: Session, document: CampaignDocument) -> None:
    """Remove the record and the stored bytes.

    Storage failure is logged, not raised: an orphaned blob is a housekeeping
    problem, while a row the creator was told is gone but is not is a lie.
    """
    try:
        storage_service.get_storage().delete(document.storage_key)
    except Exception as exc:  # pragma: no cover - storage backend specific
        logger.warning(
            "document_blob_delete_failed", document_id=document.id, error=str(exc)
        )
    db.delete(document)
    db.flush()


# --------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------
def is_owner_or_admin(campaign: Campaign, user: User | None) -> bool:
    if user is None:
        return False
    return user.role == UserRole.ADMIN or campaign.creator_id == user.id


def can_read(campaign: Campaign, document: CampaignDocument, user: User | None) -> bool:
    """Who may open the file itself.

    A signed-in visitor may open a SHARED document, but only once the campaign is
    public: before then the proposal is still under review and nothing about it
    has been published to anyone.
    """
    if is_owner_or_admin(campaign, user):
        return True
    if user is None:
        return False
    if document.visibility != DocumentVisibility.SHARED:
        return False
    return CampaignStatus(campaign.status) in PUBLIC_CAMPAIGN_STATUSES


def get_for_reader(
    db: Session, campaign_id: int, document_id: int, user: User | None
) -> tuple[Campaign, CampaignDocument]:
    """Fetch a document the caller is allowed to read, or refuse.

    A document that exists but may not be read is a permission error, not a 404:
    the caller already holds the campaign and document ids, so hiding existence
    buys nothing and an accurate message is worth more.
    """
    document = db.get(CampaignDocument, document_id)
    if document is None or document.campaign_id != campaign_id:
        raise NotFoundError("Document not found.")
    campaign = db.get(Campaign, campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign not found.")
    if not can_read(campaign, document, user):
        raise PermissionDeniedError(
            "This document is private to the creator, the reviewing admin and the AI."
        )
    return campaign, document


def read_bytes(document: CampaignDocument) -> bytes:
    return storage_service.get_storage().get(document.storage_key)


def shared_documents(campaign: Campaign) -> list[CampaignDocument]:
    return [
        document
        for document in campaign.documents
        if document.visibility == DocumentVisibility.SHARED
    ]


def download_path(campaign_id: int, document_id: int) -> str:
    return f"/api/campaigns/{campaign_id}/documents/{document_id}/download"


# --------------------------------------------------------------------------
# What the AI analyst reads
# --------------------------------------------------------------------------
# The whole document section is capped too, independently of the per-file cap:
# twelve long files would otherwise bury the proposal itself.
MAX_PROMPT_CHARS = 40_000


def prompt_section(campaign: Campaign) -> str:
    """Render the uploaded documents for the analysis prompt.

    Files the model could not read are still listed, with the reason. Telling the
    analyst "a budget was attached but could not be parsed" is materially
    different from letting it conclude no budget was ever provided.
    """
    documents = list(campaign.documents)
    if not documents:
        return "None attached."

    parts: list[str] = []
    budget = MAX_PROMPT_CHARS
    for document in documents:
        header = f"--- {document.file_name} ({document.visibility}) ---"
        if not document.extracted_text:
            reason = document.extraction_note or "Not machine-readable."
            parts.append(f"{header}\n[No readable text. {reason}]")
            continue
        body = document.extracted_text[:budget]
        budget -= len(body)
        truncated = "\n[Truncated.]" if len(body) < len(document.extracted_text) else ""
        parts.append(f"{header}\n{body}{truncated}")
        if budget <= 0:
            remaining = len(documents) - len(parts)
            if remaining > 0:
                parts.append(f"[{remaining} further document(s) omitted for length.]")
            break
    return "\n\n".join(parts)
