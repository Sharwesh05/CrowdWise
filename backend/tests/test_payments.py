"""Payment verification, contribution creation, webhook idempotency, anchoring.

The invariant under test throughout: money state moves only on a verified
signature, and it moves exactly once.
"""

from __future__ import annotations

import json
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.campaign import Campaign
from app.models.payment import Contribution, Payment
from app.services import payment_service
from tests.conftest import KYC_PAYLOAD, campaign_payload


@pytest.fixture
def live_campaign(creator, admin) -> dict:
    """A campaign taken all the way to LIVE through the real gates."""
    creator.post("/api/kyc/submit", json=KYC_PAYLOAD)
    creator.post("/api/kyc/complete")
    campaign = creator.post("/api/campaigns", json=campaign_payload()).json()
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    order = creator.post(f"/api/campaigns/{campaign['id']}/application-fee/order").json()
    creator.post(f"/api/payments/{order['payment_id']}/simulate")
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    return admin.post(f"/api/admin/campaigns/{campaign['public_id']}/approve", json={}).json()


def make_order(contributor, public_id: str, amount: str = "500.00") -> dict:
    response = contributor.post(
        f"/api/campaigns/{public_id}/contribute", json={"amount": amount}
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_order_creation_does_not_move_money(contributor, live_campaign, db):
    order = make_order(contributor, live_campaign["public_id"])
    assert order["amount_paise"] == 50000

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    assert Decimal(campaign.raised_amount) == Decimal("0.00")
    assert db.execute(select(Contribution)).scalars().first() is None


def test_forged_signature_is_rejected_and_nothing_is_recorded(contributor, live_campaign, db):
    """A client claiming success proves nothing without a valid signature."""
    order = make_order(contributor, live_campaign["public_id"])
    response = contributor.post(
        "/api/payments/verify",
        json={
            "razorpay_order_id": order["order_id"],
            "razorpay_payment_id": "pay_forged_00000000",
            "razorpay_signature": "0" * 64,
        },
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "payment_verification_failed"

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    assert Decimal(campaign.raised_amount) == Decimal("0.00")
    assert db.execute(select(Contribution)).scalars().first() is None

    payment = db.execute(
        select(Payment).where(Payment.razorpay_order_id == order["order_id"])
    ).scalars().first()
    db.refresh(payment)
    assert payment.status == "FAILED"


def test_valid_signature_records_contribution_and_updates_raised_amount(
    contributor, live_campaign, db
):
    order = make_order(contributor, live_campaign["public_id"])
    result = contributor.post(f"/api/payments/{order['payment_id']}/simulate").json()

    assert result["payment_verified"] is True
    assert result["contribution_recorded"] is True
    assert result["contribution_id"]

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    assert Decimal(campaign.raised_amount) == Decimal("500.00")
    assert campaign.contributor_count == 1


def test_repeated_verification_is_idempotent(contributor, live_campaign, db):
    order = make_order(contributor, live_campaign["public_id"])
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    assert Decimal(campaign.raised_amount) == Decimal("500.00"), "amount must not double"
    assert len(db.execute(select(Contribution)).scalars().all()) == 1


def _webhook(client, event: dict) -> tuple[int, dict]:
    body = json.dumps(event).encode()
    signature = payment_service.get_provider().sign_webhook(body)
    response = client.post(
        "/api/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": signature, "Content-Type": "application/json"},
    )
    return response.status_code, response.json()


def _captured_event(order_id: str, payment_id: str, event_id: str) -> dict:
    return {
        "id": event_id,
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {"id": payment_id, "order_id": order_id, "status": "captured"}
            }
        },
    }


def test_webhook_alone_creates_the_contribution(client, contributor, live_campaign, db):
    """The browser can vanish after paying; the signed webhook still settles it."""
    order = make_order(contributor, live_campaign["public_id"])
    status, body = _webhook(
        client, _captured_event(order["order_id"], "pay_webhook_001", "evt_001")
    )
    assert status == 200 and body["processed"] is True

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    assert Decimal(campaign.raised_amount) == Decimal("500.00")

    payment = db.execute(
        select(Payment).where(Payment.razorpay_order_id == order["order_id"])
    ).scalars().first()
    db.refresh(payment)
    assert payment.webhook_verified is True


def test_duplicate_webhook_delivery_is_ignored(client, contributor, live_campaign, db):
    order = make_order(contributor, live_campaign["public_id"])
    event = _captured_event(order["order_id"], "pay_webhook_002", "evt_duplicate")

    first_status, first = _webhook(client, event)
    second_status, second = _webhook(client, event)

    assert first_status == second_status == 200
    assert first["processed"] is True
    assert second["status"] == "duplicate"
    assert second["processed"] is False

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    assert Decimal(campaign.raised_amount) == Decimal("500.00")
    assert len(db.execute(select(Contribution)).scalars().all()) == 1


def test_webhook_after_client_verification_does_not_double_count(
    client, contributor, live_campaign, db
):
    """Both paths converge on one idempotent function."""
    order = make_order(contributor, live_campaign["public_id"])
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")

    payment = db.execute(
        select(Payment).where(Payment.razorpay_order_id == order["order_id"])
    ).scalars().first()
    db.refresh(payment)
    _webhook(
        client,
        _captured_event(order["order_id"], payment.razorpay_payment_id, "evt_late"),
    )

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    assert Decimal(campaign.raised_amount) == Decimal("500.00")
    assert len(db.execute(select(Contribution)).scalars().all()) == 1
    db.refresh(payment)
    # A late webhook still upgrades the trust level of an already-captured payment.
    assert payment.webhook_verified is True


def test_webhook_with_bad_signature_is_rejected(client, contributor, live_campaign, db):
    order = make_order(contributor, live_campaign["public_id"])
    body = json.dumps(_captured_event(order["order_id"], "pay_x", "evt_bad")).encode()
    response = client.post(
        "/api/webhooks/razorpay",
        content=body,
        headers={"X-Razorpay-Signature": "deadbeef", "Content-Type": "application/json"},
    )
    assert response.status_code == 400
    assert db.execute(select(Contribution)).scalars().first() is None


def test_payment_failed_webhook_marks_failure(client, contributor, live_campaign, db):
    order = make_order(contributor, live_campaign["public_id"])
    status, _ = _webhook(
        client,
        {
            "id": "evt_failed",
            "event": "payment.failed",
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_failed",
                        "order_id": order["order_id"],
                        "error_description": "Card declined",
                    }
                }
            },
        },
    )
    assert status == 200
    payment = db.execute(
        select(Payment).where(Payment.razorpay_order_id == order["order_id"])
    ).scalars().first()
    db.refresh(payment)
    assert payment.status == "FAILED"
    assert payment.failure_reason == "Card declined"


def test_below_minimum_contribution_rejected(contributor, live_campaign):
    response = contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/contribute", json={"amount": "10.00"}
    )
    assert response.status_code == 422


def test_creator_cannot_fund_own_campaign(creator, live_campaign):
    response = creator.post(
        f"/api/campaigns/{live_campaign['public_id']}/contribute", json={"amount": "500.00"}
    )
    assert response.status_code == 409


def test_blockchain_anchoring_after_verified_payment(contributor, live_campaign, db):
    """Verified contributions get anchored, and the record is queryable."""
    from app.services import blockchain_service

    order = make_order(contributor, live_campaign["public_id"])
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")

    # The route schedules anchoring as a background task; this sweep is the
    # safety net that also runs periodically in production.
    blockchain_service.sync_pending_contributions(db)

    contribution = db.execute(select(Contribution)).scalars().first()
    db.refresh(contribution)
    assert contribution.status == "BLOCKCHAIN_RECORDED"
    assert contribution.blockchain_tx.startswith("0x")

    detail = contributor.get(f"/api/contributions/{contribution.id}").json()
    assert detail["blockchain_record"]["tx_hash"] == contribution.blockchain_tx
    assert detail["blockchain_record"]["block_number"] > 0


def test_chain_outage_does_not_invalidate_a_verified_payment(
    monkeypatch, contributor, live_campaign, db
):
    """The core failure-isolation rule, asserted directly."""
    from app.services import blockchain_service

    def explode(*args, **kwargs):
        raise RuntimeError("rpc unreachable")

    monkeypatch.setattr(
        blockchain_service.get_provider(), "record_contribution", explode, raising=False
    )

    order = make_order(contributor, live_campaign["public_id"])
    result = contributor.post(f"/api/payments/{order['payment_id']}/simulate").json()
    assert result["payment_verified"] is True
    assert result["contribution_recorded"] is True

    blockchain_service.sync_pending_contributions(db)

    contribution = db.execute(select(Contribution)).scalars().first()
    db.refresh(contribution)
    assert contribution.status == "BLOCKCHAIN_FAILED"
    assert contribution.blockchain_tx is None

    campaign = db.get(Campaign, live_campaign["id"])
    db.refresh(campaign)
    # The money is still real. Only the anchor is missing.
    assert Decimal(campaign.raised_amount) == Decimal("500.00")

    # And a retry recovers once the chain is back.
    monkeypatch.undo()
    blockchain_service.reset_provider()
    retry = contributor.post(f"/api/blockchain/contributions/{contribution.id}/retry").json()
    assert retry["recorded"] is True
    assert retry["payment_state_unchanged"] is True


def test_on_chain_payload_contains_no_personal_data(contributor, live_campaign, db):
    """Privacy rule: only hashes, amounts and timestamps are anchored."""
    from app.models.chain import BlockchainTransaction
    from app.services import blockchain_service

    order = make_order(contributor, live_campaign["public_id"])
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")
    blockchain_service.sync_pending_contributions(db)

    record = db.execute(
        select(BlockchainTransaction).where(
            BlockchainTransaction.record_type == "CONTRIBUTION"
        )
    ).scalars().first()
    payload = json.dumps(record.payload).lower()

    for forbidden in ("backer@example.com", "ravi", "kumar", order["order_id"].lower()):
        assert forbidden not in payload, f"{forbidden} must never be anchored on chain"
    assert payload.count("0x") >= 2  # campaign ref + payment ref hash


def test_contribution_belongs_to_its_owner(contributor, second_contributor, live_campaign, db):
    order = make_order(contributor, live_campaign["public_id"])
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")
    contribution = db.execute(select(Contribution)).scalars().first()

    assert second_contributor.get(f"/api/contributions/{contribution.id}").status_code == 403
    assert second_contributor.post(f"/api/payments/{order['payment_id']}/simulate").status_code == 403


# --------------------------------------------------------------------------
# Refund settlement over the webhook (the asynchronous, Razorpay-shaped path)
# --------------------------------------------------------------------------
def _refund_event(payment_id: str, event_id: str) -> dict:
    return {
        "id": event_id,
        "event": "refund.processed",
        "payload": {
            "refund": {
                "entity": {"id": f"rfnd_{event_id}", "payment_id": payment_id, "status": "processed"}
            }
        },
    }


def test_refund_webhook_settles_the_contribution_and_closes_the_campaign(
    client, contributor, live_campaign, db, monkeypatch
):
    """A gateway that finishes asynchronously must still close the loop.

    Before this, the webhook advanced only `Payment.status`: the contributor's
    own record stayed REFUND_PENDING for good and the campaign never closed.
    """
    from app.core.enums import CampaignStatus, ContributionStatus, PaymentStatus
    from app.services import governance_service

    order = make_order(contributor, live_campaign["public_id"])
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")

    campaign = db.get(Campaign, live_campaign["id"])
    contribution = db.execute(select(Contribution)).scalars().one()
    payment = db.get(Payment, contribution.payment_id)
    gateway_payment_id = payment.razorpay_payment_id

    # Force the asynchronous provider answer so settlement can only arrive by webhook.
    provider = payment_service.get_provider()
    monkeypatch.setattr(
        provider,
        "refund",
        lambda pid, amount=None: payment_service.RefundResult(
            refund_id="rfnd_async", status="processing", provider=provider.name
        ),
    )

    campaign.status = str(CampaignStatus.REFUND_PENDING)
    governance_service.mark_contributions_refund_pending(db, campaign)
    db.commit()
    governance_service.process_refunds(db, campaign)
    db.commit()

    db.expire_all()
    assert db.get(Payment, payment.id).status == str(PaymentStatus.REFUND_INITIATED)
    assert db.get(Campaign, campaign.id).status == str(CampaignStatus.REFUND_PENDING)

    status, _ = _webhook(client, _refund_event(gateway_payment_id, "evt_refund_1"))
    assert status == 200

    db.expire_all()
    assert db.get(Payment, payment.id).status == str(PaymentStatus.REFUNDED)
    assert db.get(Contribution, contribution.id).status == str(ContributionStatus.REFUNDED)
    assert db.get(Campaign, campaign.id).status == str(CampaignStatus.CLOSED)


def test_replayed_refund_webhook_changes_nothing(
    client, contributor, live_campaign, db, monkeypatch
):
    from app.core.enums import CampaignStatus, EventType
    from app.models.campaign import CampaignEvent
    from app.services import governance_service

    order = make_order(contributor, live_campaign["public_id"])
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")

    campaign = db.get(Campaign, live_campaign["id"])
    contribution = db.execute(select(Contribution)).scalars().one()
    gateway_payment_id = db.get(Payment, contribution.payment_id).razorpay_payment_id

    provider = payment_service.get_provider()
    monkeypatch.setattr(
        provider,
        "refund",
        lambda pid, amount=None: payment_service.RefundResult(
            refund_id="rfnd_async", status="processing", provider=provider.name
        ),
    )
    campaign.status = str(CampaignStatus.REFUND_PENDING)
    governance_service.mark_contributions_refund_pending(db, campaign)
    db.commit()
    governance_service.process_refunds(db, campaign)
    db.commit()

    # Two deliveries of the same refund, distinct event ids so neither is caught
    # by the WebhookEvent dedupe — the settlement itself must be idempotent.
    _webhook(client, _refund_event(gateway_payment_id, "evt_refund_a"))
    _webhook(client, _refund_event(gateway_payment_id, "evt_refund_b"))

    db.expire_all()
    completions = (
        db.query(CampaignEvent)
        .filter(
            CampaignEvent.campaign_id == campaign.id,
            CampaignEvent.event_type == str(EventType.REFUND_COMPLETED),
        )
        .count()
    )
    assert completions == 1, "a redelivered webhook must not re-settle the refund"
    assert db.get(Campaign, campaign.id).status == str(CampaignStatus.CLOSED)
