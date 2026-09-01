"""Blockchain anchoring service.

What this module is for: creating a tamper-evident record of the moments that
matter — a campaign was registered, a verified contribution happened, a vote was
cast, an outcome was selected.

What it is emphatically *not* for: holding money, deciding whether a payment
succeeded, or storing anything about a person. Only salted hashes, amounts,
timestamps and opaque references are ever sent on chain.

Failure isolation is the other half of the job. A verified payment stays verified
even when the RPC endpoint is down; the contribution simply sits in
BLOCKCHAIN_PENDING until a retry succeeds.
"""

from __future__ import annotations

import json
import queue
import secrets
import threading
import time
from abc import ABC, abstractmethod
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import advisory_lock, session_scope, utcnow
from app.core.enums import (
    BlockchainRecordType,
    BlockchainTxStatus,
    ContributionStatus,
    EventType,
    VoteChoice,
)
from app.core.errors import ExternalServiceError
from app.core.logging import get_logger
from app.core.security import salted_hash
from app.models.campaign import Campaign
from app.models.chain import BlockchainTransaction
from app.models.governance import Vote
from app.models.payment import Contribution
from app.services import audit_service

logger = get_logger(__name__)

MAX_ATTEMPTS = 5

# One private key means one nonce sequence, so only one sweeper may hold the
# wire at a time. Arbitrary but fixed: the key for the Postgres advisory lock
# that serialises anchoring across processes.
ANCHOR_LOCK_KEY = 0x43575F414E4348 % (2**63)

CONTRACT_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "registerCampaign",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "campaignRef", "type": "bytes32"},
            {"name": "targetAmount", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "recordContribution",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "campaignRef", "type": "bytes32"},
            {"name": "paymentRefHash", "type": "bytes32"},
            {"name": "amount", "type": "uint256"},
            {"name": "contributor", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "openVoting",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "campaignRef", "type": "bytes32"},
            {"name": "closesAt", "type": "uint64"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "recordVote",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "campaignRef", "type": "bytes32"},
            {"name": "voterRef", "type": "bytes32"},
            {"name": "choice", "type": "uint8"},
            {"name": "weight", "type": "uint256"},
        ],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "closeVoting",
        "stateMutability": "nonpayable",
        "inputs": [{"name": "campaignRef", "type": "bytes32"}],
        "outputs": [],
    },
    {
        "type": "function",
        "name": "recordOutcome",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "campaignRef", "type": "bytes32"},
            {"name": "outcome", "type": "uint8"},
        ],
        "outputs": [],
    },
]

_ARTIFACT_PATHS = [
    Path(__file__).resolve().parents[3]
    / "blockchain"
    / "artifacts"
    / "contracts"
    / "CrowdWiseRegistry.sol"
    / "CrowdWiseRegistry.json",
    Path("/app/blockchain/artifacts/contracts/CrowdWiseRegistry.sol/CrowdWiseRegistry.json"),
]


def load_abi() -> list[dict[str, Any]]:
    """Prefer the compiled Hardhat artifact; fall back to the pinned ABI above."""
    for path in _ARTIFACT_PATHS:
        try:
            if path.exists():
                return json.loads(path.read_text(encoding="utf-8"))["abi"]
        except (OSError, KeyError, json.JSONDecodeError):  # pragma: no cover
            continue
    return CONTRACT_ABI


@dataclass(slots=True)
class ChainReceipt:
    tx_hash: str
    block_number: int | None
    status: str
    network: str
    contract_address: str | None
    gas_used: int | None = None
    simulated: bool = False


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
def campaign_ref(public_id: str) -> str:
    """Deterministic 32-byte campaign reference derived from the public id."""
    return salted_hash(f"campaign:{public_id}")


def voter_ref(campaign_public_id: str, user_id: int) -> str:
    """Opaque, per-campaign voter reference.

    Salted and campaign-scoped so an on-chain vote cannot be linked back to a
    person, nor correlated across campaigns.
    """
    return salted_hash(f"voter:{campaign_public_id}:{user_id}")


def payment_ref_hash(payment_reference: str) -> str:
    """One-way hash of the gateway payment id — the raw id never goes on chain."""
    return salted_hash(f"payment:{payment_reference}")


_CHOICE_CODES = {str(VoteChoice.REFUND): 1, str(VoteChoice.CONTINUE): 2}


class BlockchainProvider(ABC):
    name: str = "abstract"

    @abstractmethod
    def register_campaign(self, ref: str, target_amount_paise: int) -> ChainReceipt: ...

    @abstractmethod
    def record_contribution(
        self, ref: str, payment_hash: str, amount_paise: int, contributor: str
    ) -> ChainReceipt: ...

    @abstractmethod
    def open_voting(self, ref: str, closes_at: int) -> ChainReceipt: ...

    @abstractmethod
    def record_vote(
        self, ref: str, voter: str, choice_code: int, weight: int
    ) -> ChainReceipt: ...

    @abstractmethod
    def close_voting(self, ref: str) -> ChainReceipt: ...

    @abstractmethod
    def record_outcome(self, ref: str, outcome_code: int) -> ChainReceipt: ...


class Web3ChainProvider(BlockchainProvider):
    """Real EVM integration over web3.py (local Hardhat by default)."""

    name = "web3"
    ZERO_ADDRESS = "0x0000000000000000000000000000000000000000"

    def __init__(self):
        from web3 import Web3  # noqa: PLC0415

        if not settings.contract_address:
            raise ExternalServiceError(
                "BLOCKCHAIN_PROVIDER=web3 requires CONTRACT_ADDRESS to be set. "
                "Deploy the contract first: npx hardhat run scripts/deploy.ts --network localhost"
            )
        if not settings.blockchain_private_key:
            raise ExternalServiceError(
                "BLOCKCHAIN_PROVIDER=web3 requires BLOCKCHAIN_PRIVATE_KEY to be set."
            )
        self._w3 = Web3(Web3.HTTPProvider(settings.blockchain_rpc_url, request_kwargs={"timeout": 20}))
        self._account = self._w3.eth.account.from_key(settings.blockchain_private_key)
        self._contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(settings.contract_address), abi=load_abi()
        )
        self._lock = threading.Lock()

    def _send(self, fn_name: str, *args) -> ChainReceipt:
        # Serialise sends: concurrent transactions from one account would collide
        # on the nonce.
        with self._lock:
            function = getattr(self._contract.functions, fn_name)(*args)
            nonce = self._w3.eth.get_transaction_count(self._account.address, "pending")
            tx = function.build_transaction(
                {
                    "from": self._account.address,
                    "nonce": nonce,
                    "chainId": settings.blockchain_chain_id,
                    "gas": 500_000,
                    "gasPrice": self._w3.eth.gas_price,
                }
            )
            signed = self._account.sign_transaction(tx)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)
        return ChainReceipt(
            tx_hash=receipt["transactionHash"].hex()
            if hasattr(receipt["transactionHash"], "hex")
            else str(receipt["transactionHash"]),
            block_number=receipt.get("blockNumber"),
            status=(
                BlockchainTxStatus.CONFIRMED
                if receipt.get("status") == 1
                else BlockchainTxStatus.FAILED
            ),
            network=settings.blockchain_network,
            contract_address=settings.contract_address,
            gas_used=receipt.get("gasUsed"),
        )

    @staticmethod
    def _b32(value: str) -> bytes:
        return bytes.fromhex(value[2:] if value.startswith("0x") else value)[:32]

    def register_campaign(self, ref: str, target_amount_paise: int) -> ChainReceipt:
        return self._send("registerCampaign", self._b32(ref), int(target_amount_paise))

    def record_contribution(
        self, ref: str, payment_hash: str, amount_paise: int, contributor: str
    ) -> ChainReceipt:
        from web3 import Web3  # noqa: PLC0415

        address = (
            Web3.to_checksum_address(contributor)
            if contributor and contributor.startswith("0x") and len(contributor) == 42
            else self.ZERO_ADDRESS
        )
        return self._send(
            "recordContribution",
            self._b32(ref),
            self._b32(payment_hash),
            int(amount_paise),
            address,
        )

    def open_voting(self, ref: str, closes_at: int) -> ChainReceipt:
        return self._send("openVoting", self._b32(ref), int(closes_at))

    def record_vote(self, ref: str, voter: str, choice_code: int, weight: int) -> ChainReceipt:
        return self._send(
            "recordVote", self._b32(ref), self._b32(voter), int(choice_code), int(weight)
        )

    def close_voting(self, ref: str) -> ChainReceipt:
        return self._send("closeVoting", self._b32(ref))

    def record_outcome(self, ref: str, outcome_code: int) -> ChainReceipt:
        return self._send("recordOutcome", self._b32(ref), int(outcome_code))


class MockChainProvider(BlockchainProvider):
    """In-process simulated chain for when no node is running.

    It keeps an append-only ledger with monotonic block numbers and rejects a
    duplicate vote exactly as the Solidity contract does, so the demo exercises
    the same invariants. Everything it returns is flagged `simulated: true` and
    the UI labels it as such — it never pretends to be a real network.
    """

    name = "mock"

    def __init__(self):
        self._block = 1_000_000
        self._lock = threading.Lock()
        self.ledger: list[dict[str, Any]] = []
        self._votes: set[tuple[str, str]] = set()

    def _mine(self, record_type: str, payload: dict[str, Any]) -> ChainReceipt:
        with self._lock:
            self._block += 1
            tx_hash = "0x" + secrets.token_hex(32)
            self.ledger.append(
                {
                    "tx_hash": tx_hash,
                    "block": self._block,
                    "type": record_type,
                    "payload": payload,
                    "at": utcnow().isoformat(),
                }
            )
            block = self._block
        return ChainReceipt(
            tx_hash=tx_hash,
            block_number=block,
            status=str(BlockchainTxStatus.CONFIRMED),
            network=f"{settings.blockchain_network}-simulated",
            contract_address=settings.contract_address or "0xSIMULATED",
            gas_used=52_000,
            simulated=True,
        )

    def register_campaign(self, ref: str, target_amount_paise: int) -> ChainReceipt:
        return self._mine("CampaignRegistered", {"ref": ref, "target": target_amount_paise})

    def record_contribution(
        self, ref: str, payment_hash: str, amount_paise: int, contributor: str
    ) -> ChainReceipt:
        return self._mine(
            "ContributionRecorded",
            {"ref": ref, "payment": payment_hash, "amount": amount_paise},
        )

    def open_voting(self, ref: str, closes_at: int) -> ChainReceipt:
        return self._mine("VotingOpened", {"ref": ref, "closesAt": closes_at})

    def record_vote(self, ref: str, voter: str, choice_code: int, weight: int) -> ChainReceipt:
        key = (ref, voter)
        with self._lock:
            if key in self._votes:
                raise ExternalServiceError("Vote already recorded on chain for this voter.")
            self._votes.add(key)
        return self._mine("VoteRecorded", {"ref": ref, "choice": choice_code, "weight": weight})

    def close_voting(self, ref: str) -> ChainReceipt:
        return self._mine("VotingClosed", {"ref": ref})

    def record_outcome(self, ref: str, outcome_code: int) -> ChainReceipt:
        return self._mine("OutcomeRecorded", {"ref": ref, "outcome": outcome_code})


_provider: BlockchainProvider | None = None


def get_provider() -> BlockchainProvider:
    global _provider
    if _provider is None:
        if settings.blockchain_provider == "web3":
            try:
                _provider = Web3ChainProvider()
            except Exception as exc:
                # Misconfiguration must not take the API down; anchoring degrades
                # to simulated and says so loudly.
                logger.error("web3_provider_unavailable", error=str(exc))
                _provider = MockChainProvider()
        else:
            _provider = MockChainProvider()
        logger.info("blockchain_provider_selected", provider=_provider.name)
    return _provider


def reset_provider() -> None:
    global _provider
    _provider = None


def explorer_url(tx_hash: str) -> str | None:
    base = settings.blockchain_explorer_url.strip()
    if not base:
        return None
    return f"{base.rstrip('/')}/tx/{tx_hash}"


# --------------------------------------------------------------------------
# Persistence helpers
# --------------------------------------------------------------------------
def _persist(
    db: Session,
    *,
    campaign_id: int,
    record_type: str,
    receipt: ChainReceipt,
    contribution_id: int | None = None,
    vote_id: int | None = None,
    payload: dict[str, Any] | None = None,
) -> BlockchainTransaction:
    record = BlockchainTransaction(
        campaign_id=campaign_id,
        contribution_id=contribution_id,
        vote_id=vote_id,
        record_type=record_type,
        tx_hash=receipt.tx_hash,
        network=receipt.network,
        contract_address=receipt.contract_address,
        status=receipt.status,
        block_number=receipt.block_number,
        gas_used=receipt.gas_used,
        payload=payload,
        confirmed_at=utcnow() if receipt.status == BlockchainTxStatus.CONFIRMED else None,
    )
    db.add(record)
    db.flush()
    return record


# --------------------------------------------------------------------------
# Operations
# --------------------------------------------------------------------------
def _anchor_campaign(
    db: Session, campaign: Campaign
) -> tuple[bool, BlockchainTransaction | None]:
    """Put the campaign reference on chain.

    Returns `(anchored, record)`. `anchored` says the registry now knows the
    reference — true both for a fresh registration and for one that was already
    there; `record` is set only when this call actually wrote a transaction.
    """
    ref = campaign_ref(campaign.public_id)
    try:
        receipt = get_provider().register_campaign(
            ref, int(Decimal(campaign.target_amount) * 100)
        )
    except Exception as exc:
        # `CampaignExists` is not a failure: the reference is already anchored,
        # which is exactly the desired end state. This happens whenever the
        # database is reset while the chain keeps its history, since the campaign
        # reference is derived deterministically from the public id.
        if "CampaignExists" in str(exc):
            logger.info(
                "chain_campaign_already_registered",
                campaign_id=campaign.id,
                campaign_ref=ref,
                note="Chain retains state across a database reset; nothing to do.",
            )
            return True, None
        logger.error("chain_register_failed", campaign_id=campaign.id, error=str(exc))
        return False, None
    record = _persist(
        db,
        campaign_id=campaign.id,
        record_type=str(BlockchainRecordType.CAMPAIGN_REGISTERED),
        receipt=receipt,
        payload={"campaign_ref": ref, "simulated": receipt.simulated},
    )
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.BLOCKCHAIN_CONTRIBUTION_RECORDED,
        metadata={"tx_hash": receipt.tx_hash, "record_type": "CAMPAIGN_REGISTERED"},
    )
    return True, record


def register_campaign(db: Session, campaign: Campaign) -> BlockchainTransaction | None:
    return _anchor_campaign(db, campaign)[1]


def ensure_campaign_registered(db: Session, campaign: Campaign) -> bool:
    """Re-anchor a campaign the registry has forgotten.

    A campaign is registered once, when it is published. A local chain, though,
    is disposable: restarting the node wipes its storage and redeploys the
    registry to the same deterministic address, so `CONTRACT_ADDRESS` still
    resolves while every campaign published against the previous instance has
    silently ceased to exist. Every later contribution then reverts with
    `CampaignUnknown`, which is not something an operator should have to notice
    and repair by hand.
    """
    anchored, record = _anchor_campaign(db, campaign)
    if anchored and record is not None:
        logger.info(
            "chain_campaign_reregistered",
            campaign_id=campaign.id,
            campaign_ref=campaign_ref(campaign.public_id),
            tx_hash=record.tx_hash,
            note="Registry did not know this campaign; re-anchored before retrying.",
        )
    return anchored


def ensure_voting_open(db: Session, campaign: Campaign) -> bool:
    """Replay `openVoting` for a campaign the registry has forgotten.

    Only meaningful after a re-registration: a freshly re-anchored campaign is
    registered but not yet in voting, so a vote cast against it would revert
    with `VotingNotOpen` even though governance is genuinely open in Postgres.
    """
    if campaign.governance_closes_at is None:
        return False
    try:
        get_provider().open_voting(
            campaign_ref(campaign.public_id), int(campaign.governance_closes_at.timestamp())
        )
    except Exception as exc:
        return "VotingAlreadyOpen" in str(exc)
    return True


def _replay_chain_context(
    db: Session, campaign: Campaign, exc: Exception, *, voting: bool = False
) -> bool:
    """Rebuild the chain state a restarted local node lost.

    A campaign is registered once, at publication, and voting is opened once, at
    the start of governance. Neither is ever replayed — which is correct against
    a durable chain and wrong against a disposable one, where the node comes
    back with the same contract address and none of the history. Rather than
    leave every later write reverting, treat exactly the two errors that say
    "the chain has forgotten" as a cue to re-establish the precondition.

    Returns True when something was repaired and the write is worth retrying.
    """
    message = str(exc)
    unknown = "CampaignUnknown" in message
    if unknown and not ensure_campaign_registered(db, campaign):
        return False
    if voting and (unknown or "VotingNotOpen" in message):
        return ensure_voting_open(db, campaign)
    return unknown


def _fail_contribution(
    db: Session, contribution: Contribution, campaign: Campaign, exc: Exception
) -> None:
    """Park a contribution that could not be anchored. The payment stands."""
    contribution.status = ContributionStatus.BLOCKCHAIN_FAILED
    contribution.blockchain_error = str(exc)[:500]
    db.flush()
    logger.error(
        "chain_contribution_failed",
        contribution_id=contribution.id,
        attempts=contribution.blockchain_attempts,
        error=str(exc),
    )
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.BLOCKCHAIN_RECORD_FAILED,
        metadata={
            "contribution_id": contribution.id,
            "attempts": contribution.blockchain_attempts,
            "note": "Payment remains verified; anchoring will be retried.",
        },
    )
    return None


def record_contribution_on_chain(db: Session, contribution: Contribution) -> BlockchainTransaction | None:
    """Anchor one verified contribution. Never raises into the payment path."""
    if contribution.status == ContributionStatus.BLOCKCHAIN_RECORDED:
        return None

    campaign = db.get(Campaign, contribution.campaign_id)
    if campaign is None:
        return None

    payment = contribution.payment
    reference = (payment.razorpay_payment_id or payment.razorpay_order_id) if payment else str(
        contribution.id
    )
    ref = campaign_ref(campaign.public_id)
    payment_hash = payment_ref_hash(reference)
    amount_paise = int(Decimal(contribution.amount) * 100)
    wallet = contribution.contributor.wallet_address or ""
    contribution.blockchain_attempts = (contribution.blockchain_attempts or 0) + 1

    def send() -> ChainReceipt:
        return get_provider().record_contribution(ref, payment_hash, amount_paise, wallet)

    try:
        receipt = send()
    except Exception as exc:
        # The registry not knowing the campaign is recoverable and says nothing
        # about this contribution: re-anchor the campaign and try once more,
        # rather than burning the attempt budget on every contribution until an
        # admin intervenes.
        if not _replay_chain_context(db, campaign, exc):
            return _fail_contribution(db, contribution, campaign, exc)
        try:
            receipt = send()
        except Exception as retry_exc:
            return _fail_contribution(db, contribution, campaign, retry_exc)

    record = _persist(
        db,
        campaign_id=campaign.id,
        contribution_id=contribution.id,
        record_type=str(BlockchainRecordType.CONTRIBUTION),
        receipt=receipt,
        payload={
            "campaign_ref": ref,
            "payment_ref_hash": payment_hash,
            "amount_paise": int(Decimal(contribution.amount) * 100),
            "simulated": receipt.simulated,
        },
    )
    contribution.blockchain_tx = receipt.tx_hash
    contribution.blockchain_record_id = record.id
    contribution.blockchain_error = None
    contribution.status = ContributionStatus.BLOCKCHAIN_RECORDED
    db.flush()

    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.BLOCKCHAIN_CONTRIBUTION_RECORDED,
        metadata={
            "contribution_id": contribution.id,
            "tx_hash": receipt.tx_hash,
            "block_number": receipt.block_number,
            "network": receipt.network,
        },
    )
    return record


def record_vote_on_chain(db: Session, vote: Vote) -> BlockchainTransaction | None:
    campaign = db.get(Campaign, vote.campaign_id)
    if campaign is None:
        return None
    ref = campaign_ref(campaign.public_id)
    voter = voter_ref(campaign.public_id, vote.contributor_id)

    def send() -> ChainReceipt:
        return get_provider().record_vote(
            ref, voter, _CHOICE_CODES.get(vote.choice, 0), int(Decimal(vote.weight) * 100)
        )

    def failed(exc: Exception) -> None:
        vote.blockchain_status = str(BlockchainTxStatus.FAILED)
        db.flush()
        logger.error("chain_vote_failed", vote_id=vote.id, error=str(exc))
        return None

    try:
        receipt = send()
    except Exception as exc:
        if not _replay_chain_context(db, campaign, exc, voting=True):
            return failed(exc)
        try:
            receipt = send()
        except Exception as retry_exc:
            return failed(retry_exc)

    record = _persist(
        db,
        campaign_id=campaign.id,
        vote_id=vote.id,
        record_type=str(BlockchainRecordType.VOTE),
        receipt=receipt,
        payload={"campaign_ref": ref, "voter_ref": voter, "choice": vote.choice},
    )
    vote.blockchain_tx = receipt.tx_hash
    vote.blockchain_status = str(BlockchainTxStatus.CONFIRMED)
    db.flush()
    audit_service.record_event(
        db,
        campaign_id=campaign.id,
        event_type=EventType.VOTE_CAST,
        actor_id=vote.contributor_id,
        metadata={"tx_hash": receipt.tx_hash, "choice": vote.choice},
    )
    return record


def open_voting_on_chain(
    db: Session, campaign: Campaign, closes_at_ts: int
) -> BlockchainTransaction | None:
    try:
        receipt = get_provider().open_voting(campaign_ref(campaign.public_id), closes_at_ts)
    except Exception as exc:
        logger.error("chain_open_voting_failed", campaign_id=campaign.id, error=str(exc))
        return None
    return _persist(
        db,
        campaign_id=campaign.id,
        record_type=str(BlockchainRecordType.VOTING_OPENED),
        receipt=receipt,
        payload={"closes_at": closes_at_ts},
    )


def close_voting_on_chain(db: Session, campaign: Campaign) -> BlockchainTransaction | None:
    def send() -> ChainReceipt:
        return get_provider().close_voting(campaign_ref(campaign.public_id))

    try:
        receipt = send()
    except Exception as exc:
        if not _replay_chain_context(db, campaign, exc, voting=True):
            logger.error("chain_close_voting_failed", campaign_id=campaign.id, error=str(exc))
            return None
        try:
            receipt = send()
        except Exception as retry_exc:
            logger.error(
                "chain_close_voting_failed", campaign_id=campaign.id, error=str(retry_exc)
            )
            return None
    return _persist(
        db,
        campaign_id=campaign.id,
        record_type=str(BlockchainRecordType.VOTING_CLOSED),
        receipt=receipt,
    )


def record_outcome_on_chain(
    db: Session, campaign: Campaign, outcome: str
) -> BlockchainTransaction | None:
    def send() -> ChainReceipt:
        return get_provider().record_outcome(
            campaign_ref(campaign.public_id), _CHOICE_CODES.get(outcome, 0)
        )

    try:
        receipt = send()
    except Exception as exc:
        if not _replay_chain_context(db, campaign, exc, voting=True):
            logger.error("chain_outcome_failed", campaign_id=campaign.id, error=str(exc))
            return None
        try:
            receipt = send()
        except Exception as retry_exc:
            logger.error("chain_outcome_failed", campaign_id=campaign.id, error=str(retry_exc))
            return None
    record = _persist(
        db,
        campaign_id=campaign.id,
        record_type=str(BlockchainRecordType.OUTCOME),
        receipt=receipt,
        payload={"outcome": outcome},
    )
    audit_service.record_both(
        db,
        campaign_id=campaign.id,
        action=EventType.OUTCOME_SELECTED,
        metadata={"outcome": outcome, "tx_hash": receipt.tx_hash},
    )
    return record


# --------------------------------------------------------------------------
# Retry / sync
# --------------------------------------------------------------------------
def pending_contributions(db: Session, limit: int = 50) -> list[Contribution]:
    stmt = (
        select(Contribution)
        .where(
            Contribution.status.in_(
                [
                    str(ContributionStatus.PAYMENT_VERIFIED),
                    str(ContributionStatus.BLOCKCHAIN_PENDING),
                    str(ContributionStatus.BLOCKCHAIN_FAILED),
                ]
            ),
            Contribution.blockchain_attempts < MAX_ATTEMPTS,
        )
        .order_by(Contribution.id)
        .limit(limit)
    )
    return list(db.execute(stmt).scalars().all())


@contextmanager
def anchor_lock() -> Iterator[bool]:
    """Hold the right to write to the chain, across processes.

    Every anchor is signed by the one `BLOCKCHAIN_PRIVATE_KEY`, so there is a
    single nonce sequence to share. The API sweeps after each captured payment
    and the worker container sweeps on its own timer; two of those overlapping
    means one transaction is rejected with "nonce too low" and a contribution
    spends an attempt on a collision that had nothing to do with it. The
    in-process `threading.Lock` around `_send` cannot see another process, so
    the coordination point has to be the database.
    """
    with advisory_lock(ANCHOR_LOCK_KEY) as acquired:
        yield acquired


def sync_pending_contributions(db: Session, limit: int = 50) -> int:
    with anchor_lock() as acquired:
        if not acquired:
            logger.debug("chain_sync_skipped", reason="another sweeper holds the lock")
            return 0
        recorded = 0
        for contribution in pending_contributions(db, limit):
            if record_contribution_on_chain(db, contribution):
                recorded += 1
        db.commit()
        return recorded


def sync_pending_contributions_task() -> int:
    """Entry point for FastAPI BackgroundTasks and the sweeper thread."""
    db = session_scope()
    try:
        return sync_pending_contributions(db)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("chain_sync_failed", error=str(exc))
        db.rollback()
        return 0
    finally:
        db.close()


def retry_contribution(db: Session, contribution: Contribution) -> BlockchainTransaction | None:
    """Admin-triggered retry; resets the attempt budget for one record."""
    contribution.blockchain_attempts = 0
    contribution.status = ContributionStatus.BLOCKCHAIN_PENDING
    db.flush()
    audit_service.record_event(
        db,
        campaign_id=contribution.campaign_id,
        event_type=EventType.BLOCKCHAIN_RETRY_TRIGGERED,
        metadata={"contribution_id": contribution.id},
    )
    return record_contribution_on_chain(db, contribution)


# --------------------------------------------------------------------------
# Background sweeper
# --------------------------------------------------------------------------
_signal: queue.Queue[int] = queue.Queue()
_worker: threading.Thread | None = None
_stop = threading.Event()


def enqueue_contribution_record(contribution_id: int) -> None:
    """Signal that a contribution is waiting to be anchored.

    Deliberately does not perform the write: the caller's transaction has not
    committed yet, so the sweeper picks it up a moment later (and the periodic
    pass is the safety net if this signal is ever lost).
    """
    try:
        _signal.put_nowait(contribution_id)
    except queue.Full:  # pragma: no cover - unbounded queue
        pass


def _sweep_loop(interval: float) -> None:  # pragma: no cover - thread body
    while not _stop.is_set():
        try:
            _signal.get(timeout=interval)
            # Let the originating transaction commit before we read it.
            time.sleep(0.5)
            while not _signal.empty():
                _signal.get_nowait()
        except queue.Empty:
            pass
        try:
            sync_pending_contributions_task()
        except Exception as exc:
            logger.error("chain_sweeper_error", error=str(exc))


def start_worker(interval: float = 15.0) -> None:  # pragma: no cover - thread mgmt
    global _worker
    if _worker and _worker.is_alive():
        return
    _stop.clear()
    _worker = threading.Thread(
        target=_sweep_loop, args=(interval,), name="chain-sweeper", daemon=True
    )
    _worker.start()
    logger.info("chain_sweeper_started", interval=interval)


def stop_worker() -> None:  # pragma: no cover - thread mgmt
    _stop.set()
