"""Payment service.

The single rule this module exists to enforce: **the client never decides that
money moved.** A browser callback is treated as an unverified *claim*; it is only
acted upon after the HMAC signature is verified server-side against the key
secret, and the signed Razorpay webhook is authoritative and sufficient on its own.

Both paths converge on one idempotent function, so whichever arrives first does
the work and the second is a no-op.

Amounts are rupees (`Decimal`) everywhere in the domain. Paise integers exist only
inside this module, at the Razorpay boundary.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.enums import (
    ApplicationStatus,
    ContributionStatus,
    EventType,
    PaymentStatus,
    PaymentType,
)
from app.core.errors import (
    ConflictError,
    ExternalServiceError,
    NotFoundError,
    PaymentVerificationError,
    ValidationError,
)
from app.core.logging import get_logger
from app.models.campaign import Campaign, CampaignApplication
from app.models.payment import Contribution, Payment, WebhookEvent
from app.models.user import User
from app.services import audit_service

logger = get_logger(__name__)


# --------------------------------------------------------------------------
# Money helpers — the only place paise exists
# --------------------------------------------------------------------------
def rupees_to_paise(amount: Decimal | float | str) -> int:
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return int(value * 100)


def paise_to_rupees(paise: int) -> Decimal:
    return (Decimal(paise) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class OrderResult:
    order_id: str
    amount: Decimal
    currency: str
    key_id: str
    provider: str
    receipt: str


@dataclass(slots=True)
class RefundResult:
    refund_id: str
    status: str
    provider: str


# --------------------------------------------------------------------------
# Provider interface
# --------------------------------------------------------------------------
class PaymentProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def create_order(self, amount: Decimal, receipt: str, notes: dict[str, Any]) -> OrderResult: ...

    @abstractmethod
    def verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> bool: ...

    @abstractmethod
    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool: ...

    @abstractmethod
    def fetch_payment(self, payment_id: str) -> dict[str, Any]: ...

    @abstractmethod
    def refund(self, payment_id: str, amount: Decimal | None = None) -> RefundResult: ...

    # Demo-only helper used by the local checkout simulator. Real providers
    # cannot and must not implement this.
    def simulate_success(self, order_id: str) -> tuple[str, str]:  # pragma: no cover
        raise ExternalServiceError("Payment simulation is not available for this provider.")


class RazorpayPaymentService(PaymentProvider):
    """Real Razorpay integration (test or live keys, identical code path)."""

    name = "razorpay"

    def __init__(self):
        if not settings.razorpay_key_id or not settings.razorpay_key_secret:
            raise ExternalServiceError(
                "Razorpay is selected but RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are not set."
            )
        import razorpay  # noqa: PLC0415

        self._client = razorpay.Client(
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
        )
        self._key_secret = settings.razorpay_key_secret

    def create_order(self, amount: Decimal, receipt: str, notes: dict[str, Any]) -> OrderResult:
        try:
            order = self._client.order.create(
                {
                    "amount": rupees_to_paise(amount),
                    "currency": settings.currency,
                    "receipt": receipt,
                    "payment_capture": 1,
                    "notes": {k: str(v) for k, v in notes.items()},
                }
            )
        except Exception as exc:
            logger.error("razorpay_order_failed", receipt=receipt, error=str(exc))
            raise ExternalServiceError(
                "Could not reach the payment gateway. Please retry in a moment."
            ) from exc
        return OrderResult(
            order_id=order["id"],
            amount=amount,
            currency=order.get("currency", settings.currency),
            key_id=settings.razorpay_key_id,
            provider=self.name,
            receipt=receipt,
        )

    def verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        expected = hmac.new(
            self._key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        secret = settings.razorpay_webhook_secret
        if not secret:
            logger.error("razorpay_webhook_secret_missing")
            return False
        expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        try:
            return self._client.payment.fetch(payment_id)
        except Exception as exc:
            raise ExternalServiceError("Could not fetch payment from the gateway.") from exc

    def refund(self, payment_id: str, amount: Decimal | None = None) -> RefundResult:
        try:
            payload = {"amount": rupees_to_paise(amount)} if amount is not None else {}
            refund = self._client.payment.refund(payment_id, payload)
        except Exception as exc:
            logger.error("razorpay_refund_failed", payment_id=payment_id, error=str(exc))
            raise ExternalServiceError("Refund request failed at the gateway.") from exc
        return RefundResult(
            refund_id=refund.get("id", ""), status=refund.get("status", "processing"),
            provider=self.name,
        )


class DemoPaymentService(PaymentProvider):
    """Credential-free provider for local development and the offline demo.

    It is not a stub that returns success: it issues real order ids and signs
    them with HMAC-SHA256 using the same construction Razorpay uses, so the
    verification code exercised in the demo is the exact code that runs in
    production. A wrong signature fails here just as it would live.
    """

    name = "demo"

    def __init__(self):
        # Derived from the cookie secret so it is environment-supplied, not hardcoded.
        self._key_secret = hashlib.sha256(
            f"demo-payments:{settings.cookie_secret}".encode()
        ).hexdigest()

    def create_order(self, amount: Decimal, receipt: str, notes: dict[str, Any]) -> OrderResult:
        return OrderResult(
            order_id=f"order_demo_{secrets.token_hex(10)}",
            amount=amount,
            currency=settings.currency,
            key_id="rzp_test_demo_mode",
            provider=self.name,
            receipt=receipt,
        )

    def _sign(self, message: str) -> str:
        return hmac.new(self._key_secret.encode(), message.encode(), hashlib.sha256).hexdigest()

    def verify_checkout_signature(self, order_id: str, payment_id: str, signature: str) -> bool:
        return hmac.compare_digest(self._sign(f"{order_id}|{payment_id}"), signature or "")

    def verify_webhook_signature(self, raw_body: bytes, signature: str) -> bool:
        expected = hmac.new(self._key_secret.encode(), raw_body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature or "")

    def fetch_payment(self, payment_id: str) -> dict[str, Any]:
        return {"id": payment_id, "status": "captured", "method": "demo"}

    def refund(self, payment_id: str, amount: Decimal | None = None) -> RefundResult:
        return RefundResult(
            refund_id=f"rfnd_demo_{secrets.token_hex(8)}", status="processed", provider=self.name
        )

    def simulate_success(self, order_id: str) -> tuple[str, str]:
        """Stand in for the Razorpay checkout sheet, producing a valid signature."""
        payment_id = f"pay_demo_{secrets.token_hex(10)}"
        return payment_id, self._sign(f"{order_id}|{payment_id}")

    def sign_webhook(self, raw_body: bytes) -> str:
        """Used by the local webhook simulator and by the test suite."""
        return hmac.new(self._key_secret.encode(), raw_body, hashlib.sha256).hexdigest()


_provider: PaymentProvider | None = None


def get_provider() -> PaymentProvider:
    global _provider
    if _provider is None:
        _provider = (
            RazorpayPaymentService()
            if settings.payment_provider == "razorpay"
            else DemoPaymentService()
        )
        logger.info("payment_provider_selected", provider=_provider.name)
    return _provider


def reset_provider() -> None:
    """Test hook so a settings change can re-select the provider."""
    global _provider
    _provider = None


# --------------------------------------------------------------------------
# Order creation
# --------------------------------------------------------------------------
def create_application_fee_order(db: Session, campaign: Campaign, user: User) -> Payment:
    application = campaign.application
    if application is None:
        raise NotFoundError("This campaign has no application record.")
    if application.status in (ApplicationStatus.FEE_PAID, ApplicationStatus.SUBMITTED):
        raise ConflictError("The application fee for this campaign is already paid.")

    amount = Decimal(str(settings.application_fee_amount))
    existing = _reusable_open_order(db, user.id, campaign.id, PaymentType.APPLICATION_FEE)
    if existing:
        return existing

    order = get_provider().create_order(
        amount,
        receipt=f"appfee-{campaign.public_id}",
        notes={"type": "APPLICATION_FEE", "campaign": campaign.public_id},
    )
    payment = Payment(
        user_id=user.id,
        campaign_id=campaign.id,
        payment_type=PaymentType.APPLICATION_FEE,
        razorpay_order_id=order.order_id,
        amount=amount,
        currency=order.currency,
        status=PaymentStatus.CREATED,
        provider=order.provider,
        notes={"receipt": order.receipt},
    )
    db.add(payment)
    application.razorpay_order_id = order.order_id
    application.status = ApplicationStatus.FEE_PENDING
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.APPLICATION_FEE_ORDER_CREATED,
        actor_id=user.id,
        metadata={"order_id": order.order_id, "amount": str(amount)},
    )
    return payment


def create_contribution_order(
    db: Session, campaign: Campaign, user: User, amount: Decimal
) -> Payment:
    if amount < Decimal(campaign.minimum_contribution or 0):
        raise ValidationError(
            f"The minimum contribution for this campaign is "
            f"INR {campaign.minimum_contribution}."
        )
    if amount <= 0:
        raise ValidationError("Contribution amount must be greater than zero.")

    order = get_provider().create_order(
        amount,
        receipt=f"contrib-{campaign.public_id}-{secrets.token_hex(4)}",
        notes={"type": "CONTRIBUTION", "campaign": campaign.public_id},
    )
    payment = Payment(
        user_id=user.id,
        campaign_id=campaign.id,
        payment_type=PaymentType.CONTRIBUTION,
        razorpay_order_id=order.order_id,
        amount=amount,
        currency=order.currency,
        status=PaymentStatus.CREATED,
        provider=order.provider,
        notes={"receipt": order.receipt},
    )
    db.add(payment)
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CONTRIBUTION_ORDER_CREATED,
        actor_id=user.id,
        metadata={"order_id": order.order_id, "amount": str(amount)},
    )
    return payment


def _reusable_open_order(
    db: Session, user_id: int, campaign_id: int, payment_type: str
) -> Payment | None:
    """Reuse an unpaid order rather than littering the gateway with duplicates."""
    stmt = (
        select(Payment)
        .where(
            Payment.user_id == user_id,
            Payment.campaign_id == campaign_id,
            Payment.payment_type == payment_type,
            Payment.status == PaymentStatus.CREATED,
        )
        .order_by(Payment.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def get_payment_by_order(db: Session, order_id: str) -> Payment | None:
    return db.execute(
        select(Payment).where(Payment.razorpay_order_id == order_id)
    ).scalars().first()


# --------------------------------------------------------------------------
# Verification — the single funnel both paths use
# --------------------------------------------------------------------------
def verify_checkout_callback(
    db: Session,
    *,
    order_id: str,
    payment_id: str,
    signature: str,
    actor_id: int | None = None,
) -> Payment:
    """Handle the browser's post-checkout claim.

    The claim is worthless on its own; it is the signature check below that
    decides anything. An invalid signature is a hard failure, never a warning.
    """
    payment = get_payment_by_order(db, order_id)
    if not payment:
        raise NotFoundError("Unknown payment order.")

    if not get_provider().verify_checkout_signature(order_id, payment_id, signature):
        payment.status = PaymentStatus.FAILED
        payment.failure_reason = "signature_verification_failed"
        db.flush()
        audit_service.record_audit(
            db,
            action=EventType.PAYMENT_FAILED,
            actor_id=actor_id,
            entity_type="payment",
            entity_id=payment.id,
            metadata={"reason": "signature_verification_failed", "order_id": order_id},
        )
        # Committed before raising: the request is about to abort, and a rejected
        # payment attempt is exactly the kind of thing that must survive it.
        db.commit()
        raise PaymentVerificationError(
            "Payment signature verification failed. This payment was not accepted."
        )

    payment.razorpay_signature = signature
    return _apply_capture(db, payment, payment_id, webhook_verified=False, actor_id=actor_id)


def _apply_capture(
    db: Session,
    payment: Payment,
    payment_id: str,
    *,
    webhook_verified: bool,
    actor_id: int | None = None,
) -> Payment:
    """Idempotently mark a payment captured and run its post-payment effects."""
    already_captured = payment.status == PaymentStatus.CAPTURED

    if not already_captured:
        payment.status = PaymentStatus.CAPTURED
        payment.razorpay_payment_id = payment_id
        payment.verified_at = utcnow()
    if webhook_verified:
        # A webhook upgrades the trust level even for an already-captured payment.
        payment.webhook_verified = True
    if not payment.razorpay_payment_id:
        payment.razorpay_payment_id = payment_id
    db.flush()

    if payment.payment_type == PaymentType.APPLICATION_FEE:
        _on_application_fee_captured(db, payment, actor_id=actor_id)
    else:
        _on_contribution_captured(db, payment, actor_id=actor_id)
    return payment


def _on_application_fee_captured(
    db: Session, payment: Payment, actor_id: int | None = None
) -> None:
    from app.services import campaign_service  # local import avoids a cycle

    application = db.execute(
        select(CampaignApplication).where(CampaignApplication.campaign_id == payment.campaign_id)
    ).scalars().first()
    if application is None:
        return
    if application.status in (ApplicationStatus.FEE_PAID, ApplicationStatus.SUBMITTED):
        return  # idempotent: a duplicate webhook changes nothing

    application.status = ApplicationStatus.FEE_PAID
    application.razorpay_payment_id = payment.razorpay_payment_id
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=payment.campaign_id,
        action=EventType.APPLICATION_FEE_PAID,
        actor_id=actor_id or payment.user_id,
        metadata={
            "payment_id": payment.razorpay_payment_id,
            "amount": str(payment.amount),
            "webhook_verified": payment.webhook_verified,
        },
    )
    campaign = db.get(Campaign, payment.campaign_id)
    if campaign:
        campaign_service.advance_after_fee(db, campaign, actor_id=actor_id or payment.user_id)


def _on_contribution_captured(db: Session, payment: Payment, actor_id: int | None = None) -> None:
    """Create the contribution and move raised_amount — the only place that happens."""
    from app.services import blockchain_service  # local import avoids a cycle

    existing = db.execute(
        select(Contribution).where(Contribution.payment_id == payment.id)
    ).scalars().first()
    if existing:
        logger.info("contribution_already_recorded", payment_id=payment.id)
        return

    campaign = db.get(Campaign, payment.campaign_id)
    if campaign is None:
        raise NotFoundError("Campaign for this payment no longer exists.")

    contribution = Contribution(
        campaign_id=campaign.id,
        contributor_id=payment.user_id,
        payment_id=payment.id,
        amount=payment.amount,
        status=ContributionStatus.PAYMENT_VERIFIED,
    )
    db.add(contribution)
    try:
        db.flush()
    except IntegrityError:
        # Two deliveries raced; the unique constraint on payment_id decided it.
        db.rollback()
        logger.info("contribution_race_resolved", payment_id=payment.id)
        return

    is_new_backer = (
        db.execute(
            select(Contribution).where(
                Contribution.campaign_id == campaign.id,
                Contribution.contributor_id == payment.user_id,
                Contribution.id != contribution.id,
            )
        ).scalars().first()
        is None
    )
    campaign.raised_amount = Decimal(campaign.raised_amount or 0) + Decimal(payment.amount)
    if is_new_backer:
        campaign.contributor_count = (campaign.contributor_count or 0) + 1
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.CONTRIBUTION_PAYMENT_VERIFIED,
        actor_id=actor_id or payment.user_id,
        metadata={
            "contribution_id": contribution.id,
            "amount": str(payment.amount),
            "raised_amount": str(campaign.raised_amount),
            "webhook_verified": payment.webhook_verified,
        },
    )
    # Anchoring is a separate, retryable concern: a chain outage must never
    # invalidate a payment that the gateway has already confirmed.
    contribution.status = ContributionStatus.BLOCKCHAIN_PENDING
    db.flush()
    blockchain_service.enqueue_contribution_record(contribution.id)


# --------------------------------------------------------------------------
# Webhooks
# --------------------------------------------------------------------------
def handle_webhook(db: Session, raw_body: bytes, signature: str) -> dict[str, Any]:
    """Process a gateway webhook. Signature first, parsing second."""
    provider = get_provider()
    if not provider.verify_webhook_signature(raw_body, signature):
        logger.warning("webhook_signature_invalid", provider=provider.name)
        raise PaymentVerificationError("Invalid webhook signature.")

    try:
        event = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Webhook body is not valid JSON.") from exc

    event_type = event.get("event", "unknown")
    entity = _extract_payment_entity(event)
    payment_ref = entity.get("id") if entity else None
    order_id = entity.get("order_id") if entity else None
    # Razorpay sends x-razorpay-event-id; fall back to a deterministic key so
    # idempotency still holds if the header is absent.
    event_id = event.get("id") or f"{event_type}:{payment_ref or order_id or 'none'}"

    record = WebhookEvent(
        provider=provider.name,
        event_id=str(event_id),
        event_type=event_type,
        payment_reference=payment_ref,
        status="PROCESSING",
    )
    db.add(record)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        logger.info("webhook_duplicate_ignored", event_id=str(event_id), event_type=event_type)
        return {"status": "duplicate", "event_id": str(event_id), "processed": False}

    logger.info(
        "webhook_received",
        event_id=str(event_id),
        event_type=event_type,
        payment_id=payment_ref,
        provider=provider.name,
    )

    try:
        result = _dispatch_webhook(db, event_type, entity, order_id, payment_ref)
        record.status = "PROCESSED"
        db.flush()
        return result
    except Exception as exc:
        record.status = "FAILED"
        record.error = str(exc)[:500]
        db.flush()
        logger.error("webhook_processing_failed", event_id=str(event_id), error=str(exc))
        raise


def _extract_payment_entity(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload") or {}
    for key in ("payment", "order", "refund"):
        section = payload.get(key) or {}
        entity = section.get("entity")
        if entity:
            return entity
    return {}


def _dispatch_webhook(
    db: Session,
    event_type: str,
    entity: dict[str, Any],
    order_id: str | None,
    payment_ref: str | None,
) -> dict[str, Any]:
    if event_type in ("payment.captured", "order.paid") and order_id and payment_ref:
        payment = get_payment_by_order(db, order_id)
        if not payment:
            logger.warning("webhook_unknown_order", order_id=order_id)
            return {"status": "ignored", "reason": "unknown_order", "processed": False}
        _apply_capture(db, payment, payment_ref, webhook_verified=True)
        return {"status": "processed", "event": event_type, "processed": True}

    if event_type == "payment.failed" and order_id:
        payment = get_payment_by_order(db, order_id)
        if payment and payment.status != PaymentStatus.CAPTURED:
            payment.status = PaymentStatus.FAILED
            payment.failure_reason = (entity.get("error_description") or "gateway_failure")[:255]
            db.flush()
            audit_service.record_audit(
                db,
                action=EventType.PAYMENT_FAILED,
                entity_type="payment",
                entity_id=payment.id,
                metadata={"order_id": order_id, "reason": payment.failure_reason},
            )
        return {"status": "processed", "event": event_type, "processed": True}

    if event_type.startswith("refund."):
        payment = db.execute(
            select(Payment).where(Payment.razorpay_payment_id == entity.get("payment_id"))
        ).scalars().first()
        if payment:
            payment.status = PaymentStatus.REFUNDED
            db.flush()
        return {"status": "processed", "event": event_type, "processed": True}

    return {"status": "ignored", "reason": "unhandled_event", "processed": False}


# --------------------------------------------------------------------------
# Refunds — payment infrastructure, never the blockchain
# --------------------------------------------------------------------------
def refund_contribution(db: Session, contribution: Contribution) -> RefundResult:
    payment = db.get(Payment, contribution.payment_id)
    if payment is None or not payment.razorpay_payment_id:
        raise ConflictError("This contribution has no captured payment to refund.")
    if payment.status == PaymentStatus.REFUNDED:
        return RefundResult(refund_id="", status="already_refunded", provider=get_provider().name)

    result = get_provider().refund(payment.razorpay_payment_id, Decimal(payment.amount))
    payment.status = PaymentStatus.REFUND_INITIATED
    contribution.status = ContributionStatus.REFUND_PENDING
    db.flush()

    audit_service.record_audit(
        db,
        action=EventType.REFUND_REQUESTED,
        actor_id=contribution.contributor_id,
        entity_type="contribution",
        entity_id=contribution.id,
        metadata={"refund_id": result.refund_id, "status": result.status},
    )
    return result
