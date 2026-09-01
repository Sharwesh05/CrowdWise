"""Creator campaign routes: create, edit, submit, fee, analysis, documents, QR."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, Response, UploadFile

from app.api import serializers
from app.core.deps import CSRFProtected, CreatorOrAdmin, CurrentUser, DbSession
from app.core.enums import (
    ApplicationStatus,
    CampaignStatus,
    DocumentVisibility,
    EventType,
    UserRole,
)
from app.core.errors import (
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from app.schemas.campaign import (
    AIAnalysisResponse,
    CampaignCreateRequest,
    CampaignUpdateRequest,
    CreatorCampaign,
    DocumentResponse,
    QRResponse,
    SentimentSummary,
)
from app.schemas.common import MessageResponse
from app.schemas.payment import OrderResponse
from app.services import (
    ai_service,
    audit_service,
    campaign_service,
    document_service,
    payment_service,
    qr_service,
    sentiment_service,
    storage_service,
)
from app.services.campaign_service import CampaignDraft

router = APIRouter(prefix="/api/campaigns", tags=["Campaigns"])


def _owned(db, campaign_id: int, user):
    campaign = campaign_service.get_by_id(db, campaign_id)
    if user.role != UserRole.ADMIN:
        campaign_service.assert_owner(campaign, user)
    return campaign


@router.post("", response_model=CreatorCampaign, status_code=201, dependencies=[CSRFProtected])
def create_campaign(
    payload: CampaignCreateRequest, user: CreatorOrAdmin, db: DbSession
) -> CreatorCampaign:
    campaign = campaign_service.create_campaign(
        db,
        user,
        CampaignDraft(
            title=payload.title,
            short_description=payload.short_description,
            description=payload.description,
            problem_statement=payload.problem_statement,
            proposed_solution=payload.proposed_solution,
            expected_impact=payload.expected_impact,
            category=str(payload.category),
            target_amount=payload.target_amount,
            minimum_contribution=payload.minimum_contribution,
            deadline=payload.deadline,
            cover_image_url=payload.cover_image_url,
            outcome_type=str(payload.outcome_type),
            voting_weight_mode=str(payload.voting_weight_mode),
        ),
    )
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


@router.get("/my", response_model=list[CreatorCampaign])
def my_campaigns(user: CreatorOrAdmin, db: DbSession) -> list[CreatorCampaign]:
    return [
        serializers.creator_campaign(db, campaign)
        for campaign in campaign_service.list_creator_campaigns(db, user.id)
    ]


@router.get("/{campaign_id}", response_model=CreatorCampaign)
def get_campaign(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> CreatorCampaign:
    return serializers.creator_campaign(db, _owned(db, campaign_id, user))


@router.patch("/{campaign_id}", response_model=CreatorCampaign, dependencies=[CSRFProtected])
def update_campaign(
    campaign_id: int, payload: CampaignUpdateRequest, user: CreatorOrAdmin, db: DbSession
) -> CreatorCampaign:
    campaign = _owned(db, campaign_id, user)
    campaign_service.update_campaign(
        db, campaign, payload.model_dump(exclude_unset=True, exclude_none=True)
    )
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


@router.post("/{campaign_id}/submit", response_model=CreatorCampaign, dependencies=[CSRFProtected])
def submit_campaign(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> CreatorCampaign:
    """DRAFT → KYC_PENDING → FEE_PENDING. Blocked unless KYC is verified."""
    campaign = _owned(db, campaign_id, user)
    campaign_service.submit_application(db, campaign, campaign.creator)
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


# --------------------------------------------------------------------------
# Application fee
# --------------------------------------------------------------------------
@router.post(
    "/{campaign_id}/application-fee/order",
    response_model=OrderResponse,
    dependencies=[CSRFProtected],
)
def create_application_fee_order(
    campaign_id: int, user: CreatorOrAdmin, db: DbSession
) -> OrderResponse:
    campaign = _owned(db, campaign_id, user)
    if campaign.status != CampaignStatus.FEE_PENDING:
        raise ConflictError(
            "Submit the campaign for review before paying the application fee.",
            details={"status": campaign.status},
        )
    payment = payment_service.create_application_fee_order(db, campaign, campaign.creator)
    db.commit()
    db.refresh(payment)
    provider = payment_service.get_provider()
    return OrderResponse(
        payment_id=payment.id,
        order_id=payment.razorpay_order_id,
        amount=payment.amount,
        amount_paise=payment_service.rupees_to_paise(payment.amount),
        currency=payment.currency,
        key_id=(payment.notes or {}).get("key_id", "")
        or ("rzp_test_demo_mode" if provider.name == "demo" else ""),
        provider=provider.name,
        payment_type=payment.payment_type,
        campaign_public_id=campaign.public_id,
        demo_mode=provider.name == "demo",
        notice=(
            "Demo payment provider: use the simulate endpoint instead of the Razorpay sheet."
            if provider.name == "demo"
            else None
        ),
    )


@router.get("/{campaign_id}/application-fee/status")
def application_fee_status(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> dict:
    campaign = _owned(db, campaign_id, user)
    application = campaign.application
    if application is None:
        raise NotFoundError("This campaign has no application record.")
    return {
        "status": application.status,
        "paid": application.status
        in (ApplicationStatus.FEE_PAID, ApplicationStatus.SUBMITTED, ApplicationStatus.APPROVED),
        "amount": str(application.application_fee),
        "razorpay_order_id": application.razorpay_order_id,
        "campaign_status": campaign.status,
    }


# --------------------------------------------------------------------------
# AI analysis
# --------------------------------------------------------------------------
@router.post("/{campaign_id}/analyze", response_model=CreatorCampaign, dependencies=[CSRFProtected])
def analyze_campaign(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> CreatorCampaign:
    """Run AI analysis, then advance ANALYSIS_PENDING → UNDER_REVIEW."""
    campaign = _owned(db, campaign_id, user)
    campaign_service.run_analysis_and_advance(db, campaign, actor_id=user.id)
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


@router.get("/{campaign_id}/analysis", response_model=AIAnalysisResponse)
def get_analysis(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> AIAnalysisResponse:
    campaign = _owned(db, campaign_id, user)
    analysis = ai_service.latest_analysis(db, campaign.id)
    if analysis is None:
        raise NotFoundError("No AI analysis has been generated for this campaign yet.")
    return serializers.analysis_response(analysis)


# --------------------------------------------------------------------------
# Documents
# --------------------------------------------------------------------------
@router.post(
    "/{campaign_id}/documents",
    response_model=DocumentResponse,
    status_code=201,
    dependencies=[CSRFProtected],
)
async def upload_document(
    campaign_id: int,
    user: CreatorOrAdmin,
    db: DbSession,
    file: UploadFile = File(...),
    visibility: str = Form(default=str(DocumentVisibility.AI_ONLY)),
) -> DocumentResponse:
    """Attach a supporting document.

    `visibility` is SHARED (any signed-in user can open it once the campaign is
    public) or AI_ONLY (the creator, a reviewing admin and the AI). It defaults
    to AI_ONLY: a creator who does not choose has not agreed to publish.
    """
    campaign = _owned(db, campaign_id, user)
    content = await file.read()
    document = document_service.upload(
        db,
        campaign,
        user,
        filename=file.filename or "document",
        content=content,
        declared_mime=file.content_type,
        visibility=document_service.parse_visibility(visibility),
    )
    db.commit()
    db.refresh(document)
    return serializers.document_response(document)


@router.get("/{campaign_id}/documents", response_model=list[DocumentResponse])
def list_documents(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> list[DocumentResponse]:
    campaign = _owned(db, campaign_id, user)
    return [serializers.document_response(document) for document in campaign.documents]


@router.delete(
    "/{campaign_id}/documents/{document_id}",
    response_model=MessageResponse,
    dependencies=[CSRFProtected],
)
def delete_document(
    campaign_id: int, document_id: int, user: CreatorOrAdmin, db: DbSession
) -> MessageResponse:
    campaign = _owned(db, campaign_id, user)
    document = next((d for d in campaign.documents if d.id == document_id), None)
    if document is None:
        raise NotFoundError("Document not found.")
    document_service.delete(db, document)
    db.commit()
    return MessageResponse(message="Document removed.")


@router.get("/{campaign_id}/documents/{document_id}/download")
def download_document(
    campaign_id: int, document_id: int, user: CurrentUser, db: DbSession
) -> Response:
    """Serve a document's bytes to a reader entitled to them.

    Documents never travel as raw storage URLs. `/api/files` is unauthenticated,
    so handing one out would turn a file the creator marked private into a
    permanent public link for anyone who saw the key once.
    """
    _campaign, document = document_service.get_for_reader(db, campaign_id, document_id, user)
    return Response(
        content=document_service.read_bytes(document),
        media_type=document.mime_type,
        headers={
            # Private to this reader: never cached by a shared proxy.
            "Cache-Control": "private, no-store",
            "Content-Disposition": f'inline; filename="{_ascii_filename(document.file_name)}"',
            "X-Content-Type-Options": "nosniff",
            "Content-Security-Policy": "default-src \'none\'; sandbox",
        },
    )


def _ascii_filename(name: str) -> str:
    """A Content-Disposition-safe rendering of a user-supplied filename."""
    cleaned = "".join(ch for ch in name if ch.isprintable() and ch not in '"\\')
    return cleaned.encode("ascii", "ignore").decode() or "document"


@router.post(
    "/{campaign_id}/cover-image",
    response_model=CreatorCampaign,
    dependencies=[CSRFProtected],
)
async def upload_cover_image(
    campaign_id: int, user: CreatorOrAdmin, db: DbSession, file: UploadFile = File(...)
) -> CreatorCampaign:
    """Replace the campaign's cover image with an uploaded one.

    Stored under `covers/`, not `campaigns/`: a cover is meant to be public, and
    keeping the two prefixes apart is what lets the unauthenticated file route
    serve one while refusing the other.
    """
    campaign = _owned(db, campaign_id, user)
    content = await file.read()
    mime = storage_service.validate_upload(file.filename or "cover", content, file.content_type)
    if not mime.startswith("image/"):
        raise ValidationError("A cover image must be a JPEG, PNG or WebP image.")
    stored = storage_service.store_upload(
        file.filename or "cover", content, file.content_type, prefix="covers"
    )
    campaign.cover_image_url = stored.url
    db.flush()
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.CAMPAIGN_UPDATED,
        actor_id=user.id,
        metadata={"cover_image": stored.storage_key},
    )
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


# --------------------------------------------------------------------------
# QR
# --------------------------------------------------------------------------
@router.get("/{campaign_id}/qr", response_model=QRResponse)
def campaign_qr(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> QRResponse:
    campaign = _owned(db, campaign_id, user)
    if not campaign.qr_token:
        raise ConflictError("A QR code is issued when the campaign is approved and published.")
    return QRResponse(
        public_id=campaign.public_id,
        campaign_url=qr_service.campaign_url(campaign.public_id),
        qr_token=campaign.qr_token,
        qr_image_data_uri=qr_service.qr_data_uri(campaign.public_id),
        download_url=f"/api/public/campaigns/{campaign.public_id}/qr.png",
    )


@router.delete("/{campaign_id}", response_model=MessageResponse, dependencies=[CSRFProtected])
def close_campaign(campaign_id: int, user: CreatorOrAdmin, db: DbSession) -> MessageResponse:
    """Close a campaign that has not yet gone live."""
    from app.services import campaign_state

    campaign = _owned(db, campaign_id, user)
    if campaign.status in (CampaignStatus.LIVE, CampaignStatus.GOVERNANCE):
        raise PermissionDeniedError("A live or in-governance campaign cannot be closed here.")
    campaign_state.transition(campaign, CampaignStatus.CLOSED)
    audit_service.record_both(
        db, campaign_id=campaign.id, action=EventType.CAMPAIGN_CLOSED, actor_id=user.id
    )
    db.commit()
    return MessageResponse(message="Campaign closed.")


@router.post(
    "/{public_id}/analysis/refresh",
    response_model=AIAnalysisResponse,
    tags=["AI"],
    dependencies=[CSRFProtected],
)
def refresh_analysis(
    public_id: str, user: CreatorOrAdmin, db: DbSession
) -> AIAnalysisResponse:
    """Re-run the campaign analysis and return the fresh result.

    Distinct from `/{id}/analyze`, which is a lifecycle step: that one refuses
    outside ANALYSIS_PENDING/UNDER_REVIEW because it also advances the campaign.
    This one only writes a new analysis row, so a live campaign can be
    re-analysed — after the proposal is edited, or after a model call degraded
    to the heuristic fallback and the operator wants the real thing.
    """
    campaign = campaign_service.get_by_public_id(db, public_id)
    if user.role != UserRole.ADMIN:
        campaign_service.assert_owner(campaign, user)

    analysis = ai_service.analyze_campaign(db, campaign, actor_id=user.id)
    db.commit()
    db.refresh(analysis)
    return serializers.analysis_response(analysis)


@router.post(
    "/{public_id}/sentiment/refresh",
    response_model=SentimentSummary,
    tags=["AI"],
    dependencies=[CSRFProtected],
)
def refresh_sentiment(public_id: str, user: CreatorOrAdmin, db: DbSession) -> SentimentSummary:
    """Re-classify this campaign's unprocessed feedback and return the summary.

    Sentiment is normally classified in the background as each comment arrives.
    This is the manual recovery path for the case that background pass failed —
    without it a FAILED item waits for the worker's next sweep with nothing in
    the UI to trigger it.
    """
    campaign = campaign_service.get_by_public_id(db, public_id)
    if user.role != UserRole.ADMIN:
        campaign_service.assert_owner(campaign, user)

    sentiment_service.reanalyze_campaign(db, campaign.id)
    db.commit()
    return serializers.sentiment_summary(db, campaign.id)
