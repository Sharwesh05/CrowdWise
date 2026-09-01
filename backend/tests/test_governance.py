"""Campaign completion, governance eligibility, voting and outcomes."""

from __future__ import annotations

import pytest

from app.core.enums import CampaignStatus
from app.services import campaign_state
from tests.conftest import KYC_PAYLOAD, campaign_payload


@pytest.fixture
def funded_campaign(creator, admin, contributor, second_contributor) -> dict:
    """A LIVE campaign with two verified contributions, well short of target."""
    creator.post("/api/kyc/submit", json=KYC_PAYLOAD)
    creator.post("/api/kyc/complete")
    campaign = creator.post("/api/campaigns", json=campaign_payload()).json()
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    fee = creator.post(f"/api/campaigns/{campaign['id']}/application-fee/order").json()
    creator.post(f"/api/payments/{fee['payment_id']}/simulate")
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    live = admin.post(f"/api/admin/campaigns/{campaign['public_id']}/approve", json={}).json()

    for backer in (contributor, second_contributor):
        order = backer.post(
            f"/api/campaigns/{live['public_id']}/contribute", json={"amount": "500.00"}
        ).json()
        backer.post(f"/api/payments/{order['payment_id']}/simulate")
    return live


def demo(admin, action: str, public_id: str | None = None, **extra):
    payload = {"action": action, "campaign_public_id": public_id, **extra}
    return admin.post("/api/admin/demo/control", json=payload)


# --------------------------------------------------------------------------
# State machine
# --------------------------------------------------------------------------
def test_state_machine_allows_only_declared_transitions():
    assert campaign_state.can_transition(CampaignStatus.DRAFT, CampaignStatus.KYC_PENDING)
    assert campaign_state.can_transition(CampaignStatus.UNDER_REVIEW, CampaignStatus.APPROVED)
    assert campaign_state.can_transition(CampaignStatus.APPROVED, CampaignStatus.LIVE)
    assert campaign_state.can_transition(CampaignStatus.GOVERNANCE, CampaignStatus.CONTINUED)

    # The shortcuts a careless endpoint might otherwise allow:
    assert not campaign_state.can_transition(CampaignStatus.DRAFT, CampaignStatus.LIVE)
    assert not campaign_state.can_transition(CampaignStatus.FEE_PENDING, CampaignStatus.APPROVED)
    assert not campaign_state.can_transition(CampaignStatus.LIVE, CampaignStatus.GOVERNANCE)
    assert not campaign_state.can_transition(CampaignStatus.CLOSED, CampaignStatus.LIVE)


def test_invalid_transition_raises():
    from app.core.errors import InvalidTransitionError

    with pytest.raises(InvalidTransitionError):
        campaign_state.assert_transition(CampaignStatus.DRAFT, CampaignStatus.LIVE)


# --------------------------------------------------------------------------
# Completion
# --------------------------------------------------------------------------
def test_deadline_below_target_enters_governance(admin, funded_campaign):
    response = demo(admin, "simulate_deadline", funded_campaign["public_id"])
    assert response.status_code == 200, response.text
    assert response.json()["detail"]["status"] == "GOVERNANCE"


def test_deadline_at_or_above_target_is_target_met(creator, admin, contributor):
    """A met target must not be routed into a governance vote."""
    creator.post("/api/kyc/submit", json=KYC_PAYLOAD)
    creator.post("/api/kyc/complete")
    campaign = creator.post(
        "/api/campaigns",
        json=campaign_payload(target_amount="1000.00", minimum_contribution="500.00"),
    ).json()
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    fee = creator.post(f"/api/campaigns/{campaign['id']}/application-fee/order").json()
    creator.post(f"/api/payments/{fee['payment_id']}/simulate")
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    live = admin.post(f"/api/admin/campaigns/{campaign['public_id']}/approve", json={}).json()

    order = contributor.post(
        f"/api/campaigns/{live['public_id']}/contribute", json={"amount": "1000.00"}
    ).json()
    contributor.post(f"/api/payments/{order['payment_id']}/simulate")

    result = demo(admin, "simulate_deadline", live["public_id"]).json()
    assert result["detail"]["status"] == "TARGET_MET"


# --------------------------------------------------------------------------
# Voting
# --------------------------------------------------------------------------
def test_governance_view_reports_eligibility_and_shortfall(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    body = contributor.get(f"/api/campaigns/{funded_campaign['public_id']}/governance").json()

    assert body["is_open"] is True
    assert body["options"] == ["REFUND", "CONTINUE"]
    assert body["total_eligible_voters"] == 2
    assert body["votes_cast"] == 0
    assert float(body["shortfall"]) == 999000.0
    assert body["viewer"]["is_eligible"] is True
    assert body["viewer"]["has_voted"] is False
    assert "payment infrastructure" in body["note"]


def test_contributor_can_vote_and_vote_is_anchored(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    response = contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["votes_cast"] == 1
    assert body["results"]["REFUND"]["percentage"] == 100.0
    assert body["participation_percentage"] == 50.0
    assert body["viewer"]["has_voted"] is True
    assert body["viewer"]["vote"]["blockchain_tx"].startswith("0x")


def test_duplicate_vote_is_rejected(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    first = contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    assert first.status_code == 200
    second = contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "CONTINUE"}
    )
    assert second.status_code == 409
    assert "already voted" in second.json()["error"]["message"].lower()


def test_non_contributor_cannot_vote(admin, client, funded_campaign):
    from tests.conftest import make_user

    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    outsider = make_user(client, "outsider@example.com", "CONTRIBUTOR", "Outsider")
    response = outsider.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    assert response.status_code == 403
    assert "verified contribution" in response.json()["error"]["message"].lower()


def test_cannot_vote_before_governance_opens(contributor, funded_campaign):
    response = contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    assert response.status_code == 409


def test_cannot_vote_after_governance_closes(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    demo(admin, "close_governance", funded_campaign["public_id"])
    response = contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    assert response.status_code == 409


def test_invalid_choice_rejected(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    response = contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "STEAL_THE_MONEY"}
    )
    assert response.status_code == 422


def test_only_admin_can_close_governance(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    assert (
        contributor.post(
            f"/api/campaigns/{funded_campaign['public_id']}/governance/close"
        ).status_code
        == 403
    )


# --------------------------------------------------------------------------
# Outcomes
# --------------------------------------------------------------------------
def test_refund_outcome_moves_campaign_to_refund_pending(
    admin, contributor, second_contributor, funded_campaign
):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    second_contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    result = demo(admin, "close_governance", funded_campaign["public_id"]).json()

    assert result["detail"]["status"] == "REFUND_PENDING"
    assert result["detail"]["selected_outcome"] == "REFUND"

    contributions = contributor.get("/api/contributions/my").json()
    assert contributions["items"][0]["status"] == "REFUND_PENDING"


def test_continue_outcome_reopens_funding_with_extension(
    admin, contributor, second_contributor, funded_campaign
):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "CONTINUE"}
    )
    second_contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "CONTINUE"}
    )
    result = demo(admin, "close_governance", funded_campaign["public_id"]).json()

    assert result["detail"]["selected_outcome"] == "CONTINUE"
    page = contributor.get(f"/api/public/campaigns/{funded_campaign['public_id']}").json()
    assert page["status"] == "LIVE"
    assert page["days_remaining"] > 0


def test_outcome_is_anchored_on_chain(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    demo(admin, "close_governance", funded_campaign["public_id"])

    records = contributor.get(
        f"/api/campaigns/{funded_campaign['public_id']}/blockchain"
    ).json()
    types = {record["record_type"] for record in records}
    assert {"VOTING_OPENED", "VOTE", "VOTING_CLOSED", "OUTCOME"} <= types


def test_refunds_run_through_the_payment_provider(admin, contributor, funded_campaign):
    """Refunds are payment infrastructure, never a blockchain transaction."""
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    demo(admin, "close_governance", funded_campaign["public_id"])

    result = demo(admin, "process_refunds", funded_campaign["public_id"]).json()
    assert result["detail"]["initiated"] == 2
    assert result["detail"]["failed"] == 0
    assert "payment infrastructure" in result["message"]


def test_outcome_rules_are_locked_before_contributions(contributor, funded_campaign):
    page = contributor.get(f"/api/public/campaigns/{funded_campaign['public_id']}").json()
    rules = page["outcome_rules"]
    assert rules["locked_at"] is not None
    assert rules["options"] == ["REFUND", "CONTINUE"]
    assert rules["eligibility"] == "at_least_one_verified_contribution"


def test_demo_controls_require_admin(contributor, funded_campaign):
    response = contributor.post(
        "/api/admin/demo/control",
        json={"action": "open_governance", "campaign_public_id": funded_campaign["public_id"]},
    )
    assert response.status_code == 403


def test_contributor_dashboard_surfaces_open_votes(admin, contributor, funded_campaign):
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    dashboard = contributor.get("/api/contributor/dashboard").json()
    assert dashboard["cards"]["campaigns_supported"] == 1
    assert dashboard["cards"]["open_votes"] == 1
    assert dashboard["active_votes"][0]["public_id"] == funded_campaign["public_id"]

    contributor.post(
        f"/api/campaigns/{funded_campaign['public_id']}/vote", json={"choice": "REFUND"}
    )
    after = contributor.get("/api/contributor/dashboard").json()
    assert after["cards"]["open_votes"] == 0
    assert after["past_votes"][0]["choice"] == "REFUND"


# --------------------------------------------------------------------------
# Refund execution — the only path that moves money outward
# --------------------------------------------------------------------------
def _outcome_type(db, campaign_id: int, outcome_type: str) -> None:
    """Set the campaign's locked end-state rule directly.

    The rule is locked at publication and the service layer refuses edits, which
    is the behaviour under test elsewhere — so a test that needs a different rule
    reaches past the API rather than pretending the lock can be lifted.
    """
    from app.models.campaign import Campaign

    campaign = db.get(Campaign, campaign_id)
    campaign.outcome.outcome_type = outcome_type
    db.commit()


def _contributions(db, campaign_id: int):
    from app.models.payment import Contribution

    return (
        db.query(Contribution)
        .filter(Contribution.campaign_id == campaign_id)
        .order_by(Contribution.id)
        .all()
    )


def _payment_statuses(db, campaign_id: int) -> list[str]:
    from app.models.payment import Contribution, Payment

    rows = db.query(Payment).join(Contribution, Contribution.payment_id == Payment.id).filter(
        Contribution.campaign_id == campaign_id
    )
    return [row.status for row in rows]


def test_automatic_refund_flags_every_contribution(funded_campaign, admin, db):
    """Regression: the campaign flag alone left the sweep with nothing to refund."""
    from app.core.enums import ContributionStatus

    _outcome_type(db, funded_campaign["id"], "AUTOMATIC_REFUND")
    demo(admin, "simulate_deadline", funded_campaign["public_id"])

    db.expire_all()
    statuses = [c.status for c in _contributions(db, funded_campaign["id"])]
    assert statuses == [str(ContributionStatus.REFUND_PENDING)] * 2


def test_automatic_refund_actually_refunds_and_closes(funded_campaign, admin, db):
    from app.core.enums import CampaignStatus, ContributionStatus, PaymentStatus
    from app.models.campaign import Campaign
    from app.services import governance_service

    _outcome_type(db, funded_campaign["id"], "AUTOMATIC_REFUND")
    demo(admin, "simulate_deadline", funded_campaign["public_id"])

    db.expire_all()
    assert governance_service.process_due_refunds(db) == 2

    db.expire_all()
    assert [c.status for c in _contributions(db, funded_campaign["id"])] == [
        str(ContributionStatus.REFUNDED)
    ] * 2
    assert _payment_statuses(db, funded_campaign["id"]) == [str(PaymentStatus.REFUNDED)] * 2
    # Every contributor made whole, so the campaign is finished.
    assert db.get(Campaign, funded_campaign["id"]).status == str(CampaignStatus.CLOSED)


def test_sweeping_twice_refunds_each_contribution_once(funded_campaign, admin, db, monkeypatch):
    """The guard that matters: a second pass must not refund anybody again.

    Forced onto the asynchronous provider path, because that is the only one
    where the danger is real. A synchronous refund settles and closes the
    campaign, so a later sweep finds nothing and the test would pass without
    proving anything. Razorpay answers "processing" and finishes over a webhook,
    which leaves the contributions in REFUND_PENDING — exactly the rows the
    sweep selects on — so the second pass re-reads them and only the
    payment-status guard stands between the contributors and a double refund.
    """
    from app.services import governance_service, payment_service

    _outcome_type(db, funded_campaign["id"], "AUTOMATIC_REFUND")
    demo(admin, "simulate_deadline", funded_campaign["public_id"])

    provider = payment_service.get_provider()
    calls: list[str] = []

    def async_refund(payment_id, amount=None):
        calls.append(payment_id)
        return payment_service.RefundResult(
            refund_id=f"rfnd_{len(calls)}", status="processing", provider=provider.name
        )

    monkeypatch.setattr(provider, "refund", async_refund)

    db.expire_all()
    governance_service.process_due_refunds(db)
    db.expire_all()
    # Still awaiting the gateway, so the campaign and its contributions remain
    # selectable by the sweep.
    assert [c.status for c in _contributions(db, funded_campaign["id"])] == [
        "REFUND_PENDING"
    ] * 2
    governance_service.process_due_refunds(db)

    assert len(calls) == 2, f"expected exactly one refund per contribution, got {calls}"
    assert len(set(calls)) == 2


def test_refund_is_not_reissued_for_a_payment_already_in_flight(funded_campaign, admin, db):
    from app.core.enums import PaymentStatus
    from app.services import payment_service

    _outcome_type(db, funded_campaign["id"], "AUTOMATIC_REFUND")
    demo(admin, "simulate_deadline", funded_campaign["public_id"])

    db.expire_all()
    contribution = _contributions(db, funded_campaign["id"])[0]
    from app.models.payment import Payment

    payment = db.get(Payment, contribution.payment_id)
    payment.status = PaymentStatus.REFUND_INITIATED
    db.flush()

    result = payment_service.refund_contribution(db, contribution)
    assert result.status == "already_in_flight"


def test_vote_to_refund_still_refunds(funded_campaign, admin, contributor, db):
    """The path that already worked must keep working."""
    from app.core.enums import CampaignStatus, ContributionStatus
    from app.models.campaign import Campaign
    from app.services import governance_service

    public_id = funded_campaign["public_id"]
    demo(admin, "simulate_deadline", public_id)
    contributor.post(f"/api/campaigns/{public_id}/vote", json={"choice": "REFUND"})
    demo(admin, "close_governance", public_id)

    db.expire_all()
    governance_service.process_due_refunds(db)

    db.expire_all()
    assert [c.status for c in _contributions(db, funded_campaign["id"])] == [
        str(ContributionStatus.REFUNDED)
    ] * 2
    assert db.get(Campaign, funded_campaign["id"]).status == str(CampaignStatus.CLOSED)


def test_auto_process_refunds_off_moves_no_money(funded_campaign, admin, db, monkeypatch):
    from app.core.config import settings
    from app.core.enums import ContributionStatus
    from app.services import governance_service

    _outcome_type(db, funded_campaign["id"], "AUTOMATIC_REFUND")
    demo(admin, "simulate_deadline", funded_campaign["public_id"])
    monkeypatch.setattr(settings, "auto_process_refunds", False)

    db.expire_all()
    assert governance_service.process_due_refunds(db) == 0
    db.expire_all()
    assert [c.status for c in _contributions(db, funded_campaign["id"])] == [
        str(ContributionStatus.REFUND_PENDING)
    ] * 2


def test_keep_what_you_raise_refunds_nobody(funded_campaign, admin, db):
    from app.core.enums import CampaignStatus, ContributionStatus
    from app.models.campaign import Campaign
    from app.services import governance_service

    _outcome_type(db, funded_campaign["id"], "KEEP_WHAT_YOU_RAISE")
    demo(admin, "simulate_deadline", funded_campaign["public_id"])

    db.expire_all()
    assert governance_service.process_due_refunds(db) == 0
    db.expire_all()
    assert db.get(Campaign, funded_campaign["id"]).status == str(CampaignStatus.CLOSED)
    assert all(
        c.status != str(ContributionStatus.REFUND_PENDING)
        for c in _contributions(db, funded_campaign["id"])
    )
