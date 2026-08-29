"""Demo KYC routes.

DEMO KYC MODE: every submission is simulated with test data. The service layer
is provider-shaped so a real vendor slots in without touching these routes.
"""

from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks

from app.core.config import settings
from app.core.deps import CSRFProtected, CurrentUser, DbSession
from app.core.enums import KYCStatus
from app.schemas.campaign import KYCStatusResponse, KYCSubmitRequest
from app.services import kyc_service
from app.services.kyc_service import KYCSubmission

router = APIRouter(prefix="/api/kyc", tags=["KYC"])


def _status_response(record) -> KYCStatusResponse:
    if record is None:
        return KYCStatusResponse(status=str(KYCStatus.NOT_STARTED), demo_mode=settings.demo_mode)
    metadata = record.verification_metadata or {}
    return KYCStatusResponse(
        status=record.status,
        provider=record.provider,
        reference=record.verification_reference,
        submitted_at=record.submitted_at,
        verified_at=record.verified_at,
        demo_mode=settings.demo_mode,
        checks=metadata.get("checks"),
    )


@router.post("/submit", response_model=KYCStatusResponse, dependencies=[CSRFProtected])
def submit_kyc(
    payload: KYCSubmitRequest,
    user: CurrentUser,
    db: DbSession,
    background: BackgroundTasks,
) -> KYCStatusResponse:
    """Submit demo KYC. Moves SUBMITTED → PROCESSING, then settles to VERIFIED."""
    record = kyc_service.submit_kyc(
        db,
        user,
        KYCSubmission(
            full_name=payload.full_name,
            date_of_birth=payload.date_of_birth,
            pan_number=payload.pan_number,
            address=payload.address,
            bank_account_number=payload.bank_account_number,
            bank_ifsc=payload.bank_ifsc,
            document_storage_key=payload.document_storage_key,
        ),
    )
    db.commit()
    db.refresh(record)
    # Settling happens after the response so the client observes PROCESSING first,
    # exactly as it would against a real provider.
    background.add_task(_settle_kyc, user.id)
    return _status_response(record)


def _settle_kyc(user_id: int) -> None:
    from app.core.db import session_scope
    from app.services import auth_service

    db = session_scope()
    try:
        user = auth_service.get_active_user(db, user_id)
        kyc_service.finalize_kyc(db, user)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


@router.get("/status", response_model=KYCStatusResponse)
def kyc_status(user: CurrentUser, db: DbSession) -> KYCStatusResponse:
    return _status_response(kyc_service.get_latest(db, user.id))


@router.post("/complete", response_model=KYCStatusResponse, dependencies=[CSRFProtected])
def complete_kyc(user: CurrentUser, db: DbSession) -> KYCStatusResponse:
    """Force settlement — used by the demo when the client polls impatiently."""
    record = kyc_service.finalize_kyc(db, user)
    db.commit()
    db.refresh(record)
    return _status_response(record)
