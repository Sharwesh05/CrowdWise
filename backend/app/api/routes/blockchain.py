"""Blockchain visibility routes.

These endpoints exist so the product can be honest about what is anchored, what
is pending, and what is simulated — rather than showing a green tick and hoping.
"""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import select

from app.api import serializers
from app.core.config import settings
from app.core.deps import CSRFProtected, CurrentUser, DbSession
from app.core.enums import ContributionStatus, UserRole
from app.core.errors import NotFoundError, PermissionDeniedError
from app.models.chain import BlockchainTransaction
from app.models.payment import Contribution
from app.schemas.payment import BlockchainRecord
from app.services import blockchain_service, campaign_service

router = APIRouter(prefix="/api", tags=["Blockchain"])


@router.get("/blockchain/status")
def chain_status(db: DbSession) -> dict:
    provider = blockchain_service.get_provider()
    pending = len(blockchain_service.pending_contributions(db, limit=500))
    total = len(db.execute(select(BlockchainTransaction.id)).scalars().all())
    return {
        "provider": provider.name,
        "network": settings.blockchain_network,
        "rpc_url": settings.blockchain_rpc_url if provider.name == "web3" else None,
        "contract_address": settings.contract_address or None,
        "chain_id": settings.blockchain_chain_id,
        "explorer_url": settings.blockchain_explorer_url or None,
        "simulated": provider.name == "mock",
        "records_total": total,
        "pending_records": pending,
        "note": (
            "Simulated local ledger — no external network is being written to."
            if provider.name == "mock"
            else "Transactions are written to the configured EVM network."
        ),
    }


@router.get("/campaigns/{public_id}/blockchain", response_model=list[BlockchainRecord])
def campaign_records(public_id: str, db: DbSession) -> list[BlockchainRecord]:
    campaign = campaign_service.get_public(db, public_id)
    rows = db.execute(
        select(BlockchainTransaction)
        .where(BlockchainTransaction.campaign_id == campaign.id)
        .order_by(BlockchainTransaction.id.desc())
        .limit(100)
    ).scalars().all()
    return [serializers.blockchain_record(row) for row in rows]


@router.get("/blockchain/transactions/{tx_hash}", response_model=BlockchainRecord)
def get_transaction(tx_hash: str, db: DbSession) -> BlockchainRecord:
    record = db.execute(
        select(BlockchainTransaction).where(BlockchainTransaction.tx_hash == tx_hash)
    ).scalars().first()
    if record is None:
        raise NotFoundError("No blockchain record found for that transaction hash.")
    return serializers.blockchain_record(record)


@router.post("/blockchain/contributions/{contribution_id}/retry", dependencies=[CSRFProtected])
def retry_contribution(contribution_id: int, user: CurrentUser, db: DbSession) -> dict:
    """Retry a failed anchor.

    The contribution's money state is untouched by this — it was verified when the
    payment was verified, and it stays verified whether or not the chain responds.
    """
    contribution = db.get(Contribution, contribution_id)
    if contribution is None:
        raise NotFoundError("Contribution not found.")
    if user.role != UserRole.ADMIN and contribution.contributor_id != user.id:
        raise PermissionDeniedError("This contribution belongs to another account.")

    record = blockchain_service.retry_contribution(db, contribution)
    db.commit()
    db.refresh(contribution)
    return {
        "contribution_id": contribution.id,
        "status": contribution.status,
        "recorded": record is not None,
        "tx_hash": contribution.blockchain_tx,
        "payment_state_unchanged": True,
    }


@router.get("/blockchain/pending")
def pending_records(user: CurrentUser, db: DbSession) -> dict:
    if user.role != UserRole.ADMIN:
        raise PermissionDeniedError("Administrator access required.")
    pending = blockchain_service.pending_contributions(db, limit=100)
    return {
        "count": len(pending),
        "items": [
            {
                "contribution_id": c.id,
                "campaign_id": c.campaign_id,
                "amount": str(c.amount),
                "status": c.status,
                "attempts": c.blockchain_attempts,
                "error": c.blockchain_error,
            }
            for c in pending
        ],
        "failed": sum(
            1 for c in pending if c.status == str(ContributionStatus.BLOCKCHAIN_FAILED)
        ),
    }
