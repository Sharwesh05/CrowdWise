"""The full creator lifecycle: KYC → fee → analysis → review → LIVE → QR.

This is the integration test that mirrors the live demo. Each gate is asserted
separately, because the point of CrowdWise is that the gates exist.
"""

from __future__ import annotations

import pytest

from tests.conftest import KYC_PAYLOAD, campaign_payload


def create_campaign(creator) -> dict:
    response = creator.post("/api/campaigns", json=campaign_payload())
    assert response.status_code == 201, response.text
    return response.json()


def complete_kyc(creator) -> None:
    assert creator.post("/api/kyc/submit", json=KYC_PAYLOAD).status_code == 200
    assert creator.post("/api/kyc/complete").json()["status"] == "VERIFIED"


def pay_application_fee(creator, campaign_id: int) -> dict:
    order = creator.post(f"/api/campaigns/{campaign_id}/application-fee/order")
    assert order.status_code == 200, order.text
    body = order.json()
    assert body["amount"] == "500.00"
    assert body["amount_paise"] == 50000
    simulate = creator.post(f"/api/payments/{body['payment_id']}/simulate")
    assert simulate.status_code == 200, simulate.text
    return simulate.json()


def test_campaign_starts_as_draft(creator):
    campaign = create_campaign(creator)
    assert campaign["status"] == "DRAFT"
    assert campaign["approval_status"] == "NOT_SUBMITTED"
    assert campaign["public_id"].startswith("CMP-")
    assert campaign["qr_token"] is None


def test_submit_blocked_until_kyc_verified(creator):
    """Business rule 1: KYC gates the whole lifecycle."""
    campaign = create_campaign(creator)
    response = creator.post(f"/api/campaigns/{campaign['id']}/submit")
    assert response.status_code == 409
    assert "verification" in response.json()["error"]["message"].lower()

    complete_kyc(creator)
    response = creator.post(f"/api/campaigns/{campaign['id']}/submit")
    assert response.status_code == 200
    assert response.json()["status"] == "FEE_PENDING"


def test_fee_order_requires_submitted_campaign(creator):
    campaign = create_campaign(creator)
    response = creator.post(f"/api/campaigns/{campaign['id']}/application-fee/order")
    assert response.status_code == 409


def test_application_fee_advances_to_analysis_pending(creator):
    complete_kyc(creator)
    campaign = create_campaign(creator)
    creator.post(f"/api/campaigns/{campaign['id']}/submit")

    pay_application_fee(creator, campaign["id"])

    status = creator.get(f"/api/campaigns/{campaign['id']}/application-fee/status").json()
    assert status["paid"] is True
    assert status["campaign_status"] == "ANALYSIS_PENDING"


def test_analysis_produces_validated_scores_and_moves_to_review(creator):
    complete_kyc(creator)
    campaign = create_campaign(creator)
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    pay_application_fee(creator, campaign["id"])

    response = creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "UNDER_REVIEW"

    analysis = creator.get(f"/api/campaigns/{campaign['id']}/analysis").json()
    for field in ("feasibility_score", "problem_clarity_score", "impact_score", "risk_score"):
        assert 0 <= analysis[field] <= 100, f"{field} out of range"
    assert analysis["risk_level"] in ("Low", "Medium", "High")
    assert analysis["strengths"] and analysis["concerns"]
    assert "decision support" in analysis["disclaimer"]


def test_analysis_rejected_before_fee_is_verified(creator):
    complete_kyc(creator)
    campaign = create_campaign(creator)
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    response = creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    assert response.status_code == 409


def test_admin_approval_publishes_and_issues_qr(creator, admin, client):
    complete_kyc(creator)
    campaign = create_campaign(creator)
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    pay_application_fee(creator, campaign["id"])
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    public_id = campaign["public_id"]

    queue = admin.get("/api/admin/campaigns/pending").json()
    assert any(item["public_id"] == public_id for item in queue["items"])

    review = admin.get(f"/api/admin/campaigns/{public_id}").json()
    assert review["application_fee_paid"] is True
    assert review["creator"]["kyc_status"] == "VERIFIED"
    assert review["analysis"] is not None
    assert review["allowed_actions"] == ["approve", "reject", "request_changes"]

    approved = admin.post(
        f"/api/admin/campaigns/{public_id}/approve", json={"notes": "Looks solid."}
    )
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "LIVE"
    assert body["approval_status"] == "APPROVED"
    assert body["qr_token"], "an approved campaign must receive a QR token"
    assert body["outcome_rules"]["locked_at"], "outcome rules lock at publication"

    # The campaign is only publicly visible once it is LIVE.
    public = client.get(f"/api/public/campaigns/{public_id}")
    assert public.status_code == 200
    assert public.json()["qr_url"].endswith(f"/campaign/{public_id}")

    qr = client.get(f"/api/public/campaigns/{public_id}/qr.png")
    assert qr.status_code == 200
    assert qr.headers["content-type"] == "image/png"
    assert qr.content.startswith(b"\x89PNG")


def test_unapproved_campaign_is_not_public(creator, client):
    campaign = create_campaign(creator)
    assert client.get(f"/api/public/campaigns/{campaign['public_id']}").status_code == 404


def test_admin_reject_and_request_changes(creator, admin):
    complete_kyc(creator)
    campaign = create_campaign(creator)
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    pay_application_fee(creator, campaign["id"])
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    public_id = campaign["public_id"]

    changes = admin.post(
        f"/api/admin/campaigns/{public_id}/request-changes",
        json={"notes": "Please add a budget breakdown before we can approve."},
    )
    assert changes.status_code == 200
    assert changes.json()["status"] == "DRAFT"
    assert changes.json()["approval_status"] == "CHANGES_REQUESTED"

    # Approving a campaign that is no longer under review must fail.
    assert admin.post(f"/api/admin/campaigns/{public_id}/approve", json={}).status_code == 409


def test_creator_cannot_access_another_creators_campaign(creator, client):
    from tests.conftest import make_user

    complete_kyc(creator)
    campaign = create_campaign(creator)
    intruder = make_user(client, "intruder@example.com", "CREATOR", "Intruder")
    assert intruder.get(f"/api/campaigns/{campaign['id']}").status_code == 403


def test_contributor_cannot_create_campaign(contributor):
    assert contributor.post("/api/campaigns", json=campaign_payload()).status_code == 403


@pytest.mark.parametrize(
    "field,value",
    [("target_amount", "0"), ("minimum_contribution", "0"), ("title", "short")],
)
def test_campaign_validation(creator, field, value):
    assert creator.post("/api/campaigns", json=campaign_payload(**{field: value})).status_code == 422


def test_deadline_must_be_in_the_future(creator):
    from datetime import datetime, timedelta, timezone

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    response = creator.post("/api/campaigns", json=campaign_payload(deadline=past))
    assert response.status_code == 422
    assert "future" in response.json()["error"]["message"].lower()


def test_audit_trail_records_every_transition(creator, admin, db):
    complete_kyc(creator)
    campaign = create_campaign(creator)
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    pay_application_fee(creator, campaign["id"])
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    admin.post(f"/api/admin/campaigns/{campaign['public_id']}/approve", json={})

    logs = admin.get("/api/admin/audit-logs?limit=200").json()
    actions = {item["action"] for item in logs["items"]}
    for expected in {
        "CREATOR_REGISTERED",
        "KYC_SUBMITTED",
        "KYC_VERIFIED",
        "CAMPAIGN_CREATED",
        "CAMPAIGN_SUBMITTED",
        "APPLICATION_FEE_PAID",
        "AI_ANALYSIS_COMPLETED",
        "CAMPAIGN_APPROVED",
        "CAMPAIGN_PUBLISHED",
    }:
        assert expected in actions, f"missing audit action {expected}"


# --------------------------------------------------------------------------
# Editing while the campaign waits in the review queue
# --------------------------------------------------------------------------
def under_review(creator) -> dict:
    """Drive a campaign to UNDER_REVIEW, where a reviewer has not yet acted."""
    complete_kyc(creator)
    campaign = create_campaign(creator)
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    pay_application_fee(creator, campaign["id"])
    analysed = creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    assert analysed.json()["status"] == "UNDER_REVIEW"
    return campaign


def test_creator_can_edit_a_campaign_under_review(creator):
    """A campaign in the queue is still the creator's to correct."""
    campaign = under_review(creator)
    response = creator.patch(
        f"/api/campaigns/{campaign['id']}",
        json={"title": "Solar Water Purifiers for 60 Rural Schools"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Solar Water Purifiers for 60 Rural Schools"
    assert body["status"] == "UNDER_REVIEW", "editing must not move the campaign"
    assert body["editable"] is True


def test_editing_under_review_flags_the_analysis_as_stale(creator, admin):
    """A reviewer must never be shown scores for text that has since changed."""
    campaign = under_review(creator)
    before = admin.get(f"/api/admin/campaigns/{campaign['public_id']}").json()
    assert not any("after this analysis" in flag for flag in before["risk_indicators"])

    creator.patch(
        f"/api/campaigns/{campaign['id']}",
        json={"title": "Solar Water Purifiers for 60 Rural Schools"},
    )

    after = admin.get(f"/api/admin/campaigns/{campaign['public_id']}").json()
    assert any("after this analysis" in flag for flag in after["risk_indicators"])


def test_a_no_op_edit_does_not_flag_the_analysis(creator, admin):
    """Saving the form unchanged is not an edit, and must not cry wolf."""
    campaign = under_review(creator)
    creator.patch(f"/api/campaigns/{campaign['id']}", json={"title": campaign["title"]})

    review = admin.get(f"/api/admin/campaigns/{campaign['public_id']}").json()
    assert not any("after this analysis" in flag for flag in review["risk_indicators"])


def test_a_live_campaign_can_no_longer_be_edited(creator, admin):
    """Contributors funded the text as it stands; it is fixed from publication."""
    campaign = under_review(creator)
    admin.post(f"/api/admin/campaigns/{campaign['public_id']}/approve", json={})

    response = creator.patch(f"/api/campaigns/{campaign['id']}", json={"title": "Something else"})
    assert response.status_code == 409, response.text
    assert creator.get(f"/api/campaigns/{campaign['id']}").json()["editable"] is False
