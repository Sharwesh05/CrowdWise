"""Supporting documents: visibility tiers, authorisation, and AI ingest.

The rule these tests exist to hold: the visibility tier decides which *humans*
may open a file, and never whether the AI reads it. AI_ONLY means private from
supporters, not withheld from the analyst.
"""

from __future__ import annotations

import io

import pytest

from tests.conftest import KYC_PAYLOAD, campaign_payload

TXT = b"Budget: 40 units at INR 18,000 each. Vendor: Coimbatore Metalworks."
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


def create_campaign(creator) -> dict:
    response = creator.post("/api/campaigns", json=campaign_payload())
    assert response.status_code == 201, response.text
    return response.json()


def publish(creator, admin, campaign) -> dict:
    """Drive a campaign all the way to LIVE, the state a supporter can see."""
    assert creator.post("/api/kyc/submit", json=KYC_PAYLOAD).status_code == 200
    creator.post("/api/kyc/complete")
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    order = creator.post(f"/api/campaigns/{campaign['id']}/application-fee/order").json()
    creator.post(f"/api/payments/{order['payment_id']}/simulate")
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    approved = admin.post(
        f"/api/admin/campaigns/{campaign['public_id']}/approve", json={"notes": "ok"}
    )
    assert approved.status_code == 200, approved.text
    return approved.json()


def upload(creator, campaign_id, *, name="budget.txt", content=TXT, mime="text/plain",
           visibility="AI_ONLY"):
    return creator.post(
        f"/api/campaigns/{campaign_id}/documents",
        files={"file": (name, io.BytesIO(content), mime)},
        data={"visibility": visibility},
    )


# --------------------------------------------------------------------------
# Upload and extraction
# --------------------------------------------------------------------------
def test_upload_extracts_text_and_reports_readability(creator):
    campaign = create_campaign(creator)
    response = upload(creator, campaign["id"])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["visibility"] == "AI_ONLY"
    assert body["is_machine_readable"] is True
    assert body["extraction_note"] is None
    # Never a raw storage key: that route does not check who is asking.
    assert body["url"].startswith(f"/api/campaigns/{campaign['id']}/documents/")
    assert "/api/files/" not in body["url"]


def test_unreadable_upload_says_so_rather_than_failing(creator):
    """An image is stored and shown, but the creator is told the AI cannot read it."""
    campaign = create_campaign(creator)
    response = upload(creator, campaign["id"], name="photo.png", content=PNG, mime="image/png")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["is_machine_readable"] is False
    assert body["extraction_note"], "an unreadable file must explain why"


def test_visibility_defaults_to_private(creator):
    """A creator who does not choose has not agreed to publish."""
    campaign = create_campaign(creator)
    response = creator.post(
        f"/api/campaigns/{campaign['id']}/documents",
        files={"file": ("budget.txt", io.BytesIO(TXT), "text/plain")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["visibility"] == "AI_ONLY"


def test_unknown_visibility_is_rejected(creator):
    campaign = create_campaign(creator)
    response = upload(creator, campaign["id"], visibility="PUBLIC")
    assert response.status_code == 422, response.text


# --------------------------------------------------------------------------
# Authorisation
# --------------------------------------------------------------------------
def test_shared_document_is_readable_by_any_signed_in_user(creator, admin, contributor):
    campaign = create_campaign(creator)
    document = upload(creator, campaign["id"], visibility="SHARED").json()
    publish(creator, admin, campaign)

    response = contributor.get(document["url"])
    assert response.status_code == 200, response.text
    assert response.content == TXT
    assert response.headers["cache-control"] == "private, no-store"


def test_ai_only_document_is_refused_to_a_supporter(creator, admin, contributor):
    campaign = create_campaign(creator)
    document = upload(creator, campaign["id"], visibility="AI_ONLY").json()
    publish(creator, admin, campaign)

    assert contributor.get(document["url"]).status_code == 403


def test_ai_only_document_is_readable_by_the_reviewing_admin(creator, admin):
    """The admin carries the approval decision and must be able to read the evidence."""
    campaign = create_campaign(creator)
    document = upload(creator, campaign["id"], visibility="AI_ONLY").json()

    response = admin.get(document["url"])
    assert response.status_code == 200
    assert response.content == TXT


def test_shared_document_is_not_readable_before_the_campaign_is_public(
    creator, contributor
):
    """Nothing about a campaign under review has been published to anyone yet."""
    campaign = create_campaign(creator)
    document = upload(creator, campaign["id"], visibility="SHARED").json()

    assert contributor.get(document["url"]).status_code == 403


def test_document_download_requires_authentication(creator, admin, client):
    campaign = create_campaign(creator)
    document = upload(creator, campaign["id"], visibility="SHARED").json()
    publish(creator, admin, campaign)

    # `client` is the shared TestClient, and registering a user left its session
    # cookie in the jar. Clear it so this really is an anonymous request.
    client.cookies.clear()
    assert client.get(document["url"]).status_code == 401


def test_documents_are_not_served_by_the_unauthenticated_file_route(creator, client, db):
    """A leaked storage key must not be a permanent public link."""
    from app.models.campaign import CampaignDocument

    campaign = create_campaign(creator)
    upload(creator, campaign["id"], visibility="AI_ONLY")
    key = db.query(CampaignDocument).one().storage_key
    assert key.startswith("campaigns/")

    assert client.get(f"/api/files/{key}").status_code == 404


# --------------------------------------------------------------------------
# The public listing
# --------------------------------------------------------------------------
def test_public_listing_counts_private_documents_without_exposing_them(
    creator, admin, contributor, client
):
    campaign = create_campaign(creator)
    upload(creator, campaign["id"], name="shared.txt", visibility="SHARED")
    upload(creator, campaign["id"], name="private.txt", visibility="AI_ONLY")
    publish(creator, admin, campaign)
    public_id = campaign["public_id"]

    client.cookies.clear()  # a genuinely signed-out visitor
    anonymous = client.get(f"/api/public/campaigns/{public_id}/documents").json()
    assert anonymous["total"] == 1
    assert anonymous["ai_only_count"] == 1
    assert anonymous["requires_sign_in"] is True
    assert anonymous["documents"] == []

    signed_in = contributor.get(f"/api/public/campaigns/{public_id}/documents").json()
    assert signed_in["requires_sign_in"] is False
    assert [d["file_name"] for d in signed_in["documents"]] == ["shared.txt"]
    # The private one is counted, never listed.
    assert signed_in["ai_only_count"] == 1


# --------------------------------------------------------------------------
# What the AI is given
# --------------------------------------------------------------------------
def test_both_tiers_reach_the_ai_analyst(creator, db):
    """The tier governs human readers only. Both documents reach the model."""
    from app.models.campaign import Campaign
    from app.services import ai_service

    campaign = create_campaign(creator)
    upload(creator, campaign["id"], name="public-budget.txt", visibility="SHARED")
    upload(
        creator,
        campaign["id"],
        name="private-quote.txt",
        content=b"Vendor quote: INR 240000, valid 30 days.",
        visibility="AI_ONLY",
    )

    row = db.get(Campaign, campaign["id"])
    section = ai_service._campaign_payload(row)["supporting_documents"]
    assert "public-budget.txt (SHARED)" in section
    assert "private-quote.txt (AI_ONLY)" in section
    assert "Coimbatore Metalworks" in section
    assert "INR 240000" in section


def test_unreadable_document_is_declared_to_the_analyst(creator, db):
    """"Attached but unreadable" must not look the same as "never attached"."""
    from app.models.campaign import Campaign
    from app.services import ai_service

    campaign = create_campaign(creator)
    upload(creator, campaign["id"], name="scan.png", content=PNG, mime="image/png")

    row = db.get(Campaign, campaign["id"])
    section = ai_service._campaign_payload(row)["supporting_documents"]
    assert "scan.png" in section
    assert "No readable text" in section


def test_no_documents_is_stated_plainly(creator, db):
    from app.models.campaign import Campaign
    from app.services import ai_service

    campaign = create_campaign(creator)
    row = db.get(Campaign, campaign["id"])
    assert ai_service._campaign_payload(row)["supporting_documents"] == "None attached."


# --------------------------------------------------------------------------
# Deletion and the cover image
# --------------------------------------------------------------------------
def test_creator_can_remove_a_document(creator):
    campaign = create_campaign(creator)
    document = upload(creator, campaign["id"]).json()

    assert creator.delete(
        f"/api/campaigns/{campaign['id']}/documents/{document['id']}"
    ).status_code == 200
    assert creator.get(f"/api/campaigns/{campaign['id']}/documents").json() == []


def test_another_creator_cannot_touch_the_documents(creator, client):
    from app.core.enums import UserRole
    from tests.conftest import make_user

    campaign = create_campaign(creator)
    document = upload(creator, campaign["id"], visibility="SHARED").json()
    intruder = make_user(client, "other@example.com", str(UserRole.CREATOR), "Other")

    assert intruder.get(f"/api/campaigns/{campaign['id']}/documents").status_code == 403
    assert intruder.delete(
        f"/api/campaigns/{campaign['id']}/documents/{document['id']}"
    ).status_code == 403


def test_cover_image_upload_sets_the_campaign_image(creator):
    campaign = create_campaign(creator)
    response = creator.post(
        f"/api/campaigns/{campaign['id']}/cover-image",
        files={"file": ("cover.png", io.BytesIO(PNG), "image/png")},
    )
    assert response.status_code == 200, response.text
    url = response.json()["cover_image_url"]
    assert url and "covers/" in url
    # Relative, not absolute: this app is reachable at localhost, a LAN IP and an
    # HTTPS front door, and a URL baked with one of them loads at none of the
    # others. The client resolves it against the origin it is actually using.
    assert url.startswith("/api/files/"), url


def test_cover_image_rejects_a_non_image(creator):
    campaign = create_campaign(creator)
    response = creator.post(
        f"/api/campaigns/{campaign['id']}/cover-image",
        files={"file": ("notes.txt", io.BytesIO(TXT), "text/plain")},
    )
    assert response.status_code == 422, response.text
