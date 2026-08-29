"""Payment routes: contribution orders, verification, webhook, demo simulation."""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Header, Request
from sqlalchemy import select

from app.api import serializers
from app.core.config import settings
from app.core.deps import CSRFProtected, CurrentUser, DbSession
from app.core.enums import FUNDABLE_CAMPAIGN_STATUSES, ContributionStatus, PaymentStatus
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.logging import get_logger
from app.models.payment import Contribution, Payment
from app.schemas.common import Page
from app.schemas.payment import (
    ContributeRequest,
    ContributionResponse,
    OrderResponse,
    PaymentResponse,
    VerificationProgress,
    VerifyPaymentRequest,
)
from app.services import blockchain_service, campaign_service, payment_service

logger = get_logger(__name__)

router = APIRouter(prefix="/api", tags=["Payments"])


def _order_response(payment: Payment, campaign_public_id: str | None) -> OrderResponse:
    provider = payment_service.get_provider()
    key_id = settings.razorpay_key_id if provider.name == "razorpay" else "rzp_test_demo_mode"
    return OrderResponse(
        payment_id=payment.id,
        order_id=payment.razorpay_order_id,
        amount=payment.amount,
        amount_paise=payment_service.rupees_to_paise(payment.amount),
        currency=payment.currency,
        key_id=key_id,
        provider=provider.name,
        payment_type=payment.payment_type,
        campaign_public_id=campaign_public_id,
        demo_mode=provider.name == "demo",
        notice=(
            "Demo payment provider — complete the payment with the simulate endpoint."
            if provider.name == "demo"
            else None
        ),
    )


@router.post(
    "/campaigns/{public_id}/contribute", response_model=OrderResponse, dependencies=[CSRFProtected]
)
def contribute(
    public_id: str, payload: ContributeRequest, user: CurrentUser, db: DbSession
) -> OrderResponse:
    """Create a payment order. No money state changes until verification."""
    campaign = campaign_service.get_public(db, public_id)
    if campaign.status not in FUNDABLE_CAMPAIGN_STATUSES:
        raise ConflictError(
            "This campaign is not currently accepting contributions.",
            details={"status": campaign.status},
        )
    if campaign.creator_id == user.id:
        raise ConflictError("You cannot contribute to your own campaign.")

    payment = payment_service.create_contribution_order(db, campaign, user, payload.amount)
    if payload.is_anonymous:
        payment.notes = {**(payment.notes or {}), "anonymous": True}
    db.commit()
    db.refresh(payment)
    return _order_response(payment, campaign.public_id)


@router.post("/payments/verify", response_model=VerificationProgress, dependencies=[CSRFProtected])
def verify_payment(
    payload: VerifyPaymentRequest,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> VerificationProgress:
    """Verify the checkout callback server-side.

    The request body is a *claim* from the browser. It is acted on only after the
    HMAC signature is verified against the key secret.
    """
    payment = payment_service.verify_checkout_callback(
        db,
        order_id=payload.razorpay_order_id,
        payment_id=payload.razorpay_payment_id,
        signature=payload.razorpay_signature,
        actor_id=user.id,
    )
    if payment.user_id != user.id:
        raise PermissionDeniedError("This payment belongs to another account.")
    db.commit()
    db.refresh(payment)

    contribution = db.execute(
        select(Contribution).where(Contribution.payment_id == payment.id)
    ).scalars().first()
    # Anchoring runs after the response so the contributor is never blocked on a chain call.
    background.add_task(blockchain_service.sync_pending_contributions_task)
    return _progress(payment, contribution)


def _progress(payment: Payment, contribution: Contribution | None) -> VerificationProgress:
    captured = payment.status == PaymentStatus.CAPTURED
    return VerificationProgress(
        payment_received=payment.status in (PaymentStatus.CAPTURED, PaymentStatus.PENDING),
        payment_verified=captured,
        webhook_verified=payment.webhook_verified,
        contribution_recorded=contribution is not None,
        blockchain_status=(
            contribution.status if contribution else str(ContributionStatus.BLOCKCHAIN_PENDING)
        ),
        blockchain_tx=contribution.blockchain_tx if contribution else None,
        contribution_id=contribution.id if contribution else None,
        message=(
            "Payment verified and contribution recorded."
            if contribution
            else "Payment verification failed."
            if not captured
            else "Payment verified."
        ),
    )


@router.get("/payments/{payment_id}", response_model=PaymentResponse)
def get_payment(payment_id: int, user: CurrentUser, db: DbSession) -> PaymentResponse:
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.user_id != user.id and user.role != "ADMIN":
        raise PermissionDeniedError("This payment belongs to another account.")
    return PaymentResponse.model_validate(payment)


@router.get("/payments/{payment_id}/progress", response_model=VerificationProgress)
def payment_progress(payment_id: int, user: CurrentUser, db: DbSession) -> VerificationProgress:
    """Polled by the payment verification screen so the UI shows each real step."""
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.user_id != user.id and user.role != "ADMIN":
        raise PermissionDeniedError("This payment belongs to another account.")
    contribution = db.execute(
        select(Contribution).where(Contribution.payment_id == payment.id)
    ).scalars().first()
    return _progress(payment, contribution)


# --------------------------------------------------------------------------
# Demo checkout simulation
# --------------------------------------------------------------------------
@router.post(
    "/payments/{payment_id}/simulate", response_model=VerificationProgress, dependencies=[CSRFProtected]
)
def simulate_payment(
    payment_id: int, user: CurrentUser, db: DbSession, background: BackgroundTasks
) -> VerificationProgress:
    """Stand-in for the Razorpay checkout sheet when PAYMENT_PROVIDER=demo.

    It produces a genuine HMAC signature and then goes through the *same*
    verification path as a real payment — nothing is short-circuited.
    """
    provider = payment_service.get_provider()
    if provider.name != "demo":
        raise ConflictError(
            "Payment simulation is only available with the demo payment provider."
        )
    payment = db.get(Payment, payment_id)
    if payment is None:
        raise NotFoundError("Payment not found.")
    if payment.user_id != user.id:
        raise PermissionDeniedError("This payment belongs to another account.")
    if payment.status == PaymentStatus.CAPTURED:
        contribution = db.execute(
            select(Contribution).where(Contribution.payment_id == payment.id)
        ).scalars().first()
        return _progress(payment, contribution)

    gateway_payment_id, signature = provider.simulate_success(payment.razorpay_order_id)
    payment_service.verify_checkout_callback(
        db,
        order_id=payment.razorpay_order_id,
        payment_id=gateway_payment_id,
        signature=signature,
        actor_id=user.id,
    )
    db.commit()
    db.refresh(payment)
    contribution = db.execute(
        select(Contribution).where(Contribution.payment_id == payment.id)
    ).scalars().first()
    background.add_task(blockchain_service.sync_pending_contributions_task)
    return _progress(payment, contribution)


# --------------------------------------------------------------------------
# Webhook — the authoritative path
# --------------------------------------------------------------------------
webhook_router = APIRouter(prefix="/api/webhooks", tags=["Payments"])


@webhook_router.post("/razorpay")
async def razorpay_webhook(
    request: Request,
    db: DbSession,
    background: BackgroundTasks,
    x_razorpay_signature: str | None = Header(default=None),
) -> dict:
    """Razorpay webhook endpoint.

    Signature is verified against the raw body before anything is parsed, and the
    handler is idempotent: a redelivered event never creates a second contribution.
    """
    raw_body = await request.body()
    signature = x_razorpay_signature or request.headers.get("x-razorpay-signature", "")
    result = payment_service.handle_webhook(db, raw_body, signature)
    db.commit()
    if result.get("processed"):
        background.add_task(blockchain_service.sync_pending_contributions_task)
    return result


@router.get("/contributions/my", response_model=Page[ContributionResponse], tags=["Contributions"])
def my_contributions(
    user: CurrentUser,
    db: DbSession,
    limit: int = 20,
    offset: int = 0,
) -> Page[ContributionResponse]:
    stmt = select(Contribution).where(Contribution.contributor_id == user.id)
    total = len(db.execute(stmt).scalars().all())
    rows = db.execute(
        stmt.order_by(Contribution.id.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return Page[ContributionResponse](
        items=[serializers.contribution_response(db, row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/contributions/{contribution_id}", response_model=ContributionResponse, tags=["Contributions"])
def get_contribution(
    contribution_id: int, user: CurrentUser, db: DbSession
) -> ContributionResponse:
    contribution = db.get(Contribution, contribution_id)
    if contribution is None:
        raise NotFoundError("Contribution not found.")
    if contribution.contributor_id != user.id and user.role != "ADMIN":
        raise PermissionDeniedError("This contribution belongs to another account.")
    return serializers.contribution_response(db, contribution)
