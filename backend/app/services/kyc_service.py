"""KYC service.

DEMO MODE ONLY. `DemoKYCProvider` simulates SUBMITTED → PROCESSING → VERIFIED with
fake data. No real identity document is ever required, and nothing stored here is
sent to the blockchain, to the LLM, or to any log line.

The provider interface exists so a real KYC vendor can be added later without any
change to campaign or application business logic.
"""

from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import utcnow
from app.core.enums import EventType, KYCStatus
from app.core.errors import ConflictError, ValidationError
from app.core.logging import get_logger
from app.models.user import KYCVerification, User
from app.services import audit_service

logger = get_logger(__name__)


@dataclass(slots=True)
class KYCSubmission:
    full_name: str
    date_of_birth: str
    pan_number: str
    address: str
    bank_account_number: str
    bank_ifsc: str
    document_storage_key: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class KYCResult:
    reference: str
    status: str
    provider: str
    metadata: dict[str, Any]


class KYCProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def submit(self, submission: KYCSubmission) -> KYCResult: ...

    @abstractmethod
    def poll(self, reference: str) -> KYCResult: ...


class DemoKYCProvider(KYCProvider):
    """Simulated provider for the hackathon.

    Deterministic and instant, but it still moves through the real states so the
    UI, the audit trail and the campaign gate all behave exactly as they would
    against a live vendor.
    """

    name = "demo"

    def submit(self, submission: KYCSubmission) -> KYCResult:
        _validate_demo_submission(submission)
        reference = f"DEMOKYC-{secrets.token_hex(8).upper()}"
        # Only masked, non-identifying fragments are retained.
        metadata = {
            "demo": True,
            "notice": "DEMO KYC MODE — simulated verification with test data only.",
            "name_on_record": submission.full_name,
            "pan_masked": _mask(submission.pan_number),
            "bank_account_masked": _mask(submission.bank_account_number),
            "ifsc": submission.bank_ifsc,
            "document_provided": bool(submission.document_storage_key),
            "checks": {
                "identity_match": "PASS",
                "document_readable": "PASS",
                "bank_account_format": "PASS",
                "sanctions_screening": "NOT_PERFORMED_IN_DEMO",
            },
        }
        return KYCResult(
            reference=reference,
            status=KYCStatus.PROCESSING,
            provider=self.name,
            metadata=metadata,
        )

    def poll(self, reference: str) -> KYCResult:
        # A real provider would be queried here; the demo settles immediately.
        return KYCResult(
            reference=reference,
            status=KYCStatus.VERIFIED,
            provider=self.name,
            metadata={"demo": True, "settled": True},
        )


def _mask(value: str) -> str:
    cleaned = (value or "").strip()
    if len(cleaned) <= 4:
        return "*" * len(cleaned)
    return "*" * (len(cleaned) - 4) + cleaned[-4:]


def _validate_demo_submission(submission: KYCSubmission) -> None:
    if len(submission.full_name.strip()) < 3:
        raise ValidationError("Full name is required.")
    pan = submission.pan_number.strip().upper()
    if len(pan) != 10 or not pan[:5].isalpha() or not pan[5:9].isdigit():
        raise ValidationError("Demo PAN must look like ABCDE1234F (test values only).")
    if len(submission.bank_account_number.strip()) < 6:
        raise ValidationError("Demo bank account number looks invalid.")
    if len(submission.bank_ifsc.strip()) != 11:
        raise ValidationError("Demo IFSC must be 11 characters.")
    if len(submission.address.strip()) < 10:
        raise ValidationError("Address is required.")


_provider: KYCProvider | None = None


def get_provider() -> KYCProvider:
    global _provider
    if _provider is None:
        _provider = DemoKYCProvider()
        logger.info("kyc_provider_selected", provider=_provider.name, demo_mode=settings.demo_mode)
    return _provider


# --------------------------------------------------------------------------
# Service operations
# --------------------------------------------------------------------------
def get_latest(db: Session, user_id: int) -> KYCVerification | None:
    stmt = (
        select(KYCVerification)
        .where(KYCVerification.user_id == user_id)
        .order_by(KYCVerification.id.desc())
        .limit(1)
    )
    return db.execute(stmt).scalars().first()


def submit_kyc(db: Session, user: User, submission: KYCSubmission) -> KYCVerification:
    existing = get_latest(db, user.id)
    if existing and existing.status == KYCStatus.VERIFIED:
        raise ConflictError("Identity verification is already complete for this account.")

    result = get_provider().submit(submission)
    record = KYCVerification(
        user_id=user.id,
        provider=result.provider,
        verification_reference=result.reference,
        status=KYCStatus.SUBMITTED,
        submitted_at=utcnow(),
        verification_metadata=result.metadata,
    )
    # Appended to the relationship rather than added to the session directly, so
    # `user.kyc_status` is correct immediately for callers that already hold the
    # user object (the campaign gate reads it in the same transaction).
    user.kyc_verifications.append(record)
    db.flush()

    audit_service.record_audit(
        db,
        action=EventType.KYC_SUBMITTED,
        actor_id=user.id,
        entity_type="kyc",
        entity_id=record.id,
        metadata={"provider": result.provider, "reference": result.reference},
    )
    # Move straight to PROCESSING so the UI shows the real intermediate state.
    record.status = KYCStatus.PROCESSING
    db.flush()
    return record


def finalize_kyc(db: Session, user: User, actor_id: int | None = None) -> KYCVerification:
    """Complete verification (demo settles instantly; a real provider would call back)."""
    record = get_latest(db, user.id)
    if not record:
        raise ConflictError("No identity verification has been submitted yet.")
    if record.status == KYCStatus.VERIFIED:
        return record
    if record.status not in (KYCStatus.SUBMITTED, KYCStatus.PROCESSING):
        raise ConflictError(f"Verification cannot be completed from state {record.status}.")

    result = get_provider().poll(record.verification_reference)
    record.status = result.status
    record.verified_at = utcnow() if result.status == KYCStatus.VERIFIED else None
    merged = dict(record.verification_metadata or {})
    merged.update(result.metadata)
    record.verification_metadata = merged
    db.flush()

    audit_service.record_audit(
        db,
        action=EventType.KYC_VERIFIED,
        actor_id=actor_id or user.id,
        entity_type="kyc",
        entity_id=record.id,
        metadata={"reference": record.verification_reference, "status": record.status},
    )
    return record


def require_verified(user: User) -> None:
    if not user.is_kyc_verified:
        raise ConflictError(
            "Identity verification must be completed before a campaign can proceed.",
            details={"kyc_status": user.kyc_status},
        )
