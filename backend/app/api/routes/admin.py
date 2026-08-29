"""Admin routes: review queue, decisions, dashboard, audit log, demo controls."""

from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Query
from sqlalchemy import func, select

from app.api import serializers
from app.core.config import settings
from app.core.deps import AdminUser, CSRFProtected, DbSession
from app.core.enums import (
    ApplicationStatus,
    ApprovalStatus,
    CampaignStatus,
    ContributionStatus,
    EventType,
    KYCStatus,
    PaymentStatus,
    PaymentType,
    UserRole,
)
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError, ValidationError
from app.models.campaign import Campaign
from app.models.chain import BlockchainTransaction
from app.models.community import Feedback
from app.models.payment import Contribution, Payment
from app.models.user import KYCVerification, User
from app.schemas.admin import (
    AdminCampaignReview,
    AdminDashboard,
    ApproveRequest,
    AuditLogResponse,
    DemoControlRequest,
    DemoControlResponse,
    DocumentResponse,
    RejectRequest,
    RequestChangesRequest,
    ReviewCreator,
)
from app.schemas.campaign import ApplicationResponse, CampaignSummary, CreatorCampaign
from app.schemas.common import Page
from app.services import (
    ai_service,
    audit_service,
    blockchain_service,
    campaign_service,
    governance_service,
    kyc_service,
    sentiment_service,
    storage_service,
)

router = APIRouter(prefix="/api/admin", tags=["Admin"])


# --------------------------------------------------------------------------
# Review queue
# --------------------------------------------------------------------------
@router.get("/campaigns/pending", response_model=Page[CampaignSummary])
def pending_campaigns(
    admin: AdminUser,
    db: DbSession,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[CampaignSummary]:
    stmt = select(Campaign).where(Campaign.status == str(CampaignStatus.UNDER_REVIEW))
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = db.execute(stmt.order_by(Campaign.id.asc()).limit(limit).offset(offset)).scalars().all()
    return Page[CampaignSummary](
        items=[serializers.campaign_summary(db, c) for c in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/campaigns", response_model=Page[CampaignSummary])
def all_campaigns(
    admin: AdminUser,
    db: DbSession,
    status: str | None = None,
    search: str | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[CampaignSummary]:
    stmt = select(Campaign)
    if status:
        stmt = stmt.where(Campaign.status == status)
    if search:
        stmt = stmt.where(Campaign.title.ilike(f"%{search}%"))
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = db.execute(stmt.order_by(Campaign.id.desc()).limit(limit).offset(offset)).scalars().all()
    return Page[CampaignSummary](
        items=[serializers.campaign_summary(db, c) for c in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _risk_indicators(db, campaign: Campaign, analysis) -> list[str]:
    """Concrete, checkable flags — not vibes."""
    flags: list[str] = []
    if analysis and (analysis.risk_score or 0) >= 70:
        flags.append(f"AI risk score is high ({analysis.risk_score}/100).")
    if analysis and (analysis.feasibility_score or 100) < 45:
        flags.append(f"AI feasibility score is low ({analysis.feasibility_score}/100).")
    if analysis and analysis.status == "DEGRADED":
        flags.append("AI analysis ran in fallback mode — treat scores as indicative only.")
    if not campaign.creator.is_kyc_verified:
        flags.append("Creator identity verification is not complete.")
    if Decimal(campaign.target_amount) >= Decimal("5000000"):
        flags.append("Funding target exceeds INR 50,00,000.")
    if not campaign.documents:
        flags.append("No supporting documents were uploaded.")
    application = campaign.application
    if application and application.status not in (
        ApplicationStatus.FEE_PAID,
        ApplicationStatus.SUBMITTED,
        ApplicationStatus.APPROVED,
    ):
        flags.append("Application fee is not verified.")
    other_campaigns = db.execute(
        select(func.count(Campaign.id)).where(Campaign.creator_id == campaign.creator_id)
    ).scalar_one()
    if int(other_campaigns) > 3:
        flags.append(f"Creator has {other_campaigns} campaigns on the platform.")
    return flags


@router.get("/campaigns/{public_id}", response_model=AdminCampaignReview)
def review_campaign(public_id: str, admin: AdminUser, db: DbSession) -> AdminCampaignReview:
    """The full review panel: creator, KYC, fee, proposal, AI, risk, documents."""
    campaign = campaign_service.get_by_public_id(db, public_id)
    creator = campaign.creator
    kyc = kyc_service.get_latest(db, creator.id)
    analysis = ai_service.latest_analysis(db, campaign.id)
    application = campaign.application
    fee_payment = db.execute(
        select(Payment).where(
            Payment.campaign_id == campaign.id,
            Payment.payment_type == str(PaymentType.APPLICATION_FEE),
            Payment.status == str(PaymentStatus.CAPTURED),
        )
    ).scalars().first()
    storage = storage_service.get_storage()
    campaigns_created = int(
        db.execute(
            select(func.count(Campaign.id)).where(Campaign.creator_id == creator.id)
        ).scalar_one()
    )

    allowed: list[str] = []
    if campaign.status == CampaignStatus.UNDER_REVIEW:
        allowed = ["approve", "reject", "request_changes"]

    return AdminCampaignReview(
        campaign=serializers.campaign_summary(db, campaign, with_health=True),
        description=campaign.description,
        problem_statement=campaign.problem_statement,
        proposed_solution=campaign.proposed_solution,
        expected_impact=campaign.expected_impact,
        creator=ReviewCreator(
            id=creator.id,
            name=creator.name,
            email=creator.email,
            phone=creator.phone,
            kyc_status=creator.kyc_status,
            kyc_verified_at=kyc.verified_at if kyc else None,
            kyc_reference=kyc.verification_reference if kyc else None,
            campaigns_created=campaigns_created,
        ),
        application=ApplicationResponse.model_validate(application) if application else None,
        application_fee_paid=fee_payment is not None,
        application_fee_webhook_verified=bool(fee_payment and fee_payment.webhook_verified),
        analysis=serializers.analysis_response(analysis),
        risk_indicators=_risk_indicators(db, campaign, analysis),
        recommended_questions=(analysis.questions_for_creator if analysis else []) or [],
        documents=[
            DocumentResponse(
                id=doc.id,
                file_name=doc.file_name,
                mime_type=doc.mime_type,
                size=doc.size,
                created_at=doc.created_at,
                url=storage.url_for(doc.storage_key),
            )
            for doc in campaign.documents
        ],
        review_notes=campaign.review_notes,
        allowed_actions=allowed,
    )


# --------------------------------------------------------------------------
# Decisions
# --------------------------------------------------------------------------
@router.post(
    "/campaigns/{public_id}/approve", response_model=CreatorCampaign, dependencies=[CSRFProtected]
)
def approve(
    public_id: str, payload: ApproveRequest, admin: AdminUser, db: DbSession
) -> CreatorCampaign:
    """Approve and publish. Issues the QR and locks the outcome rules."""
    campaign = campaign_service.get_by_public_id(db, public_id)
    campaign_service.approve_campaign(db, campaign, admin, payload.notes)
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


@router.post(
    "/campaigns/{public_id}/reject", response_model=CreatorCampaign, dependencies=[CSRFProtected]
)
def reject(
    public_id: str, payload: RejectRequest, admin: AdminUser, db: DbSession
) -> CreatorCampaign:
    campaign = campaign_service.get_by_public_id(db, public_id)
    campaign_service.reject_campaign(db, campaign, admin, payload.reason)
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


@router.post(
    "/campaigns/{public_id}/request-changes",
    response_model=CreatorCampaign,
    dependencies=[CSRFProtected],
)
def request_changes(
    public_id: str, payload: RequestChangesRequest, admin: AdminUser, db: DbSession
) -> CreatorCampaign:
    campaign = campaign_service.get_by_public_id(db, public_id)
    campaign_service.request_changes(db, campaign, admin, payload.notes)
    db.commit()
    db.refresh(campaign)
    return serializers.creator_campaign(db, campaign)


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@router.get("/dashboard", response_model=AdminDashboard)
def dashboard(admin: AdminUser, db: DbSession) -> AdminDashboard:
    def count(model, *where) -> int:
        stmt = select(func.count(model.id))
        for clause in where:
            stmt = stmt.where(clause)
        return int(db.execute(stmt).scalar_one())

    verified = [
        str(ContributionStatus.PAYMENT_VERIFIED),
        str(ContributionStatus.BLOCKCHAIN_PENDING),
        str(ContributionStatus.BLOCKCHAIN_RECORDED),
    ]
    total_amount = db.execute(
        select(func.sum(Contribution.amount)).where(Contribution.status.in_(verified))
    ).scalar_one_or_none()

    kyc_summary = {
        str(status): count(KYCVerification, KYCVerification.status == str(status))
        for status in (
            KYCStatus.SUBMITTED,
            KYCStatus.PROCESSING,
            KYCStatus.VERIFIED,
            KYCStatus.REJECTED,
        )
    }

    return AdminDashboard(
        total_campaigns=count(Campaign),
        pending_reviews=count(Campaign, Campaign.status == str(CampaignStatus.UNDER_REVIEW)),
        active_campaigns=count(
            Campaign,
            Campaign.status.in_([str(CampaignStatus.LIVE), str(CampaignStatus.CONTINUED)]),
        ),
        completed_campaigns=count(
            Campaign,
            Campaign.status.in_(
                [
                    str(CampaignStatus.TARGET_MET),
                    str(CampaignStatus.TARGET_MISSED),
                    str(CampaignStatus.CLOSED),
                ]
            ),
        ),
        rejected_campaigns=count(Campaign, Campaign.status == str(CampaignStatus.REJECTED)),
        governance_campaigns=count(Campaign, Campaign.status == str(CampaignStatus.GOVERNANCE)),
        total_contributions_amount=Decimal(total_amount or 0),
        total_contributions_count=count(Contribution, Contribution.status.in_(verified)),
        total_contributors=int(
            db.execute(
                select(func.count(func.distinct(Contribution.contributor_id)))
            ).scalar_one()
        ),
        total_creators=count(User, User.role == str(UserRole.CREATOR)),
        kyc_summary=kyc_summary,
        failed_payments=count(Payment, Payment.status == str(PaymentStatus.FAILED)),
        unverified_payments=count(
            Payment,
            Payment.status == str(PaymentStatus.CAPTURED),
            Payment.webhook_verified.is_(False),
        ),
        blockchain_pending=count(
            Contribution, Contribution.status == str(ContributionStatus.BLOCKCHAIN_PENDING)
        ),
        blockchain_failed=count(
            Contribution, Contribution.status == str(ContributionStatus.BLOCKCHAIN_FAILED)
        ),
        demo_mode=settings.demo_mode,
    )


@router.get("/payments", response_model=Page[dict])
def list_payments(
    admin: AdminUser,
    db: DbSession,
    status: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[dict]:
    stmt = select(Payment)
    if status:
        stmt = stmt.where(Payment.status == status)
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = db.execute(stmt.order_by(Payment.id.desc()).limit(limit).offset(offset)).scalars().all()
    return Page[dict](
        items=[
            {
                "id": p.id,
                "user_id": p.user_id,
                "campaign_id": p.campaign_id,
                "payment_type": p.payment_type,
                "amount": str(p.amount),
                "status": p.status,
                "webhook_verified": p.webhook_verified,
                "razorpay_order_id": p.razorpay_order_id,
                "provider": p.provider,
                "created_at": p.created_at.isoformat(),
            }
            for p in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/audit-logs", response_model=Page[AuditLogResponse])
def audit_logs(
    admin: AdminUser,
    db: DbSession,
    action: str | None = None,
    entity_type: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> Page[AuditLogResponse]:
    rows, total = audit_service.list_audit_logs(
        db, action=action, entity_type=entity_type, limit=limit, offset=offset
    )
    return Page[AuditLogResponse](
        items=[AuditLogResponse.model_validate(row, from_attributes=True) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


# --------------------------------------------------------------------------
# DEMO CONTROLS — admin-only, DEMO_MODE-only
# --------------------------------------------------------------------------
demo_router = APIRouter(prefix="/api/admin/demo", tags=["Admin"])


@demo_router.get("/controls")
def list_controls(admin: AdminUser) -> dict:
    return {
        "demo_mode": settings.demo_mode,
        "label": "DEMO CONTROL",
        "warning": "These controls are admin-only and disabled outside DEMO_MODE.",
        "actions": [
            {"action": "complete_kyc", "needs": ["user_email"], "label": "Complete KYC simulation"},
            {"action": "run_analysis", "needs": ["campaign_public_id"], "label": "Trigger AI analysis"},
            {"action": "simulate_deadline", "needs": ["campaign_public_id"], "label": "Simulate deadline"},
            {"action": "mark_target_missed", "needs": ["campaign_public_id"], "label": "Mark target missed"},
            {"action": "open_governance", "needs": ["campaign_public_id"], "label": "Open governance"},
            {"action": "close_governance", "needs": ["campaign_public_id"], "label": "Close governance"},
            {"action": "retry_blockchain", "needs": ["campaign_public_id"], "label": "Retry blockchain sync"},
            {"action": "refresh_insights", "needs": ["campaign_public_id"], "label": "Refresh community insights"},
            {"action": "process_refunds", "needs": ["campaign_public_id"], "label": "Process refunds"},
            {"action": "analyze_pending_feedback", "needs": [], "label": "Classify pending feedback"},
        ],
    }


@demo_router.post("/control", response_model=DemoControlResponse, dependencies=[CSRFProtected])
def demo_control(
    payload: DemoControlRequest, admin: AdminUser, db: DbSession
) -> DemoControlResponse:
    """Run one demo control action.

    Guarded twice: the caller must be an admin *and* DEMO_MODE must be on. These
    shortcuts compress time (a deadline, a settlement) — they never fabricate a
    payment or bypass signature verification.
    """
    if not settings.demo_mode:
        raise PermissionDeniedError("Demo controls are disabled outside DEMO_MODE.")

    action = payload.action
    campaign = (
        campaign_service.get_by_public_id(db, payload.campaign_public_id)
        if payload.campaign_public_id
        else None
    )

    def need_campaign() -> Campaign:
        if campaign is None:
            raise ValidationError("campaign_public_id is required for this action.")
        return campaign

    detail: dict = {}

    if action == "complete_kyc":
        if not payload.user_email:
            raise ValidationError("user_email is required for complete_kyc.")
        user = db.execute(
            select(User).where(func.lower(User.email) == payload.user_email.lower())
        ).scalars().first()
        if user is None:
            raise NotFoundError("No account with that email.")
        record = kyc_service.finalize_kyc(db, user, actor_id=admin.id)
        detail = {"kyc_status": record.status, "user": user.email}
        message = f"KYC for {user.email} is now {record.status}."

    elif action == "run_analysis":
        target = need_campaign()
        campaign_service.run_analysis_and_advance(db, target, actor_id=admin.id)
        analysis = ai_service.latest_analysis(db, target.id)
        detail = {
            "status": target.status,
            "risk_score": analysis.risk_score if analysis else None,
            "feasibility_score": analysis.feasibility_score if analysis else None,
        }
        message = "AI analysis completed; campaign moved to review."

    elif action == "simulate_deadline":
        target = need_campaign()
        from app.core.db import utcnow

        target.deadline = utcnow()
        db.flush()
        campaign_service.complete_campaign(db, target, actor_id=admin.id)
        detail = {"status": target.status, "raised": str(target.raised_amount)}
        message = f"Deadline simulated; campaign is now {target.status}."

    elif action == "mark_target_missed":
        target = need_campaign()
        if target.status in (CampaignStatus.LIVE, CampaignStatus.CONTINUED):
            from app.core.db import utcnow

            target.deadline = utcnow()
            db.flush()
            campaign_service.complete_campaign(db, target, actor_id=admin.id)
        if target.status not in (
            CampaignStatus.TARGET_MISSED,
            CampaignStatus.GOVERNANCE,
            CampaignStatus.REFUND_PENDING,
        ):
            raise ConflictError(
                f"Campaign reached {target.status}; the target was met, so it cannot be "
                "marked missed."
            )
        detail = {"status": target.status}
        message = f"Campaign is {target.status}."

    elif action == "open_governance":
        target = need_campaign()
        governance_service.open_governance(db, target, actor_id=admin.id)
        detail = {
            "status": target.status,
            "closes_at": target.governance_closes_at.isoformat()
            if target.governance_closes_at
            else None,
            "eligible_voters": governance_service.count_eligible_voters(db, target.id),
        }
        message = "Governance round opened."

    elif action == "close_governance":
        target = need_campaign()
        governance_service.close_governance(db, target, actor_id=admin.id)
        detail = {
            "status": target.status,
            "selected_outcome": target.outcome.selected_outcome if target.outcome else None,
        }
        message = "Governance round closed and outcome applied."

    elif action == "retry_blockchain":
        target = need_campaign()
        recorded = 0
        for contribution in blockchain_service.pending_contributions(db, limit=100):
            if contribution.campaign_id == target.id and blockchain_service.retry_contribution(
                db, contribution
            ):
                recorded += 1
        detail = {"recorded": recorded}
        message = f"Retried blockchain sync; {recorded} record(s) anchored."

    elif action == "refresh_insights":
        target = need_campaign()
        sentiment_service.analyze_pending(db, limit=200)
        insight = ai_service.generate_community_insights(db, target, actor_id=admin.id)
        detail = {"feedback_count": insight.feedback_count if insight else 0}
        message = "Community insights regenerated." if insight else "No feedback to analyse yet."

    elif action == "process_refunds":
        target = need_campaign()
        detail = governance_service.process_refunds(db, target, actor_id=admin.id)
        message = (
            "Refunds initiated through the payment provider. "
            "Settlement is handled by payment infrastructure, not the blockchain."
        )

    elif action == "analyze_pending_feedback":
        processed = sentiment_service.analyze_pending(db, limit=500)
        detail = {"processed": processed}
        message = f"Classified {processed} pending feedback item(s)."

    else:
        raise ValidationError(f"Unknown demo action: {action}")

    audit_service.record_audit(
        db,
        action=EventType.DEMO_CONTROL_USED,
        actor_id=admin.id,
        entity_type="demo",
        entity_id=payload.campaign_public_id or payload.user_email,
        metadata={"demo_action": action, "detail": detail},
    )
    db.commit()
    return DemoControlResponse(action=action, status="ok", message=message, detail=detail)


# --------------------------------------------------------------------------
# Platform browsing helpers
# --------------------------------------------------------------------------
@router.get("/users", response_model=Page[dict])
def list_users(
    admin: AdminUser,
    db: DbSession,
    role: str | None = None,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[dict]:
    stmt = select(User)
    if role:
        stmt = stmt.where(User.role == role)
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = db.execute(stmt.order_by(User.id.desc()).limit(limit).offset(offset)).scalars().all()
    return Page[dict](
        items=[
            {
                "id": u.id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "kyc_status": u.kyc_status,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat(),
            }
            for u in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/blockchain/transactions", response_model=Page[dict])
def list_chain_transactions(
    admin: AdminUser,
    db: DbSession,
    limit: int = Query(default=25, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> Page[dict]:
    stmt = select(BlockchainTransaction)
    total = int(db.execute(select(func.count()).select_from(stmt.subquery())).scalar_one())
    rows = db.execute(
        stmt.order_by(BlockchainTransaction.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page[dict](
        items=[
            {
                "id": r.id,
                "campaign_id": r.campaign_id,
                "record_type": r.record_type,
                "tx_hash": r.tx_hash,
                "network": r.network,
                "status": r.status,
                "block_number": r.block_number,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/feedback/pending")
def pending_feedback(admin: AdminUser, db: DbSession) -> dict:
    count = int(
        db.execute(
            select(func.count(Feedback.id)).where(Feedback.sentiment.in_(["PENDING", "FAILED"]))
        ).scalar_one()
    )
    return {"pending": count}
