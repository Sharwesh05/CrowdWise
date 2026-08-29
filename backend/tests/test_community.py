"""Feedback, sentiment classification, aspect extraction and community insights."""

from __future__ import annotations

import pytest

from app.services import sentiment_service
from tests.conftest import KYC_PAYLOAD, campaign_payload


@pytest.fixture
def live_campaign(creator, admin) -> dict:
    creator.post("/api/kyc/submit", json=KYC_PAYLOAD)
    creator.post("/api/kyc/complete")
    campaign = creator.post("/api/campaigns", json=campaign_payload()).json()
    creator.post(f"/api/campaigns/{campaign['id']}/submit")
    order = creator.post(f"/api/campaigns/{campaign['id']}/application-fee/order").json()
    creator.post(f"/api/payments/{order['payment_id']}/simulate")
    creator.post(f"/api/campaigns/{campaign['id']}/analyze")
    return admin.post(f"/api/admin/campaigns/{campaign['public_id']}/approve", json={}).json()


# --------------------------------------------------------------------------
# Classifier behaviour
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,expected",
    [
        ("This is a wonderful and useful project with great social impact.", "POSITIVE"),
        ("Terrible execution, the funding target is unrealistic and misleading.", "NEGATIVE"),
        ("The campaign was submitted on Tuesday and lists two districts.", "NEUTRAL"),
        ("This is not good at all, very disappointed with the plan.", "NEGATIVE"),
        ("Bahut badhiya initiative, sahi kaam kar rahe hain.", "POSITIVE"),
    ],
)
def test_sentiment_classification(text, expected):
    """The classifier reads the text — including negation and Hinglish."""
    assert sentiment_service.get_provider().classify(text).label == expected


def test_but_clause_shifts_sentiment():
    """"Good, but X" is the shape most naive classifiers get wrong."""
    result = sentiment_service.get_provider().classify(
        "Good social impact, but the funding target seems aggressive and unrealistic."
    )
    assert result.label in ("NEGATIVE", "NEUTRAL")


@pytest.mark.parametrize(
    "text,expected_aspect",
    [
        ("The funding target of 10 lakh seems too ambitious.", "FUNDING_TARGET"),
        ("Who is on the team and what is their track record?", "TEAM"),
        ("How will you scale this to other districts?", "SCALABILITY"),
        ("Great social impact for village communities.", "IMPACT"),
        ("Is the delivery timeline realistic? The execution plan is thin.", "EXECUTION_PLAN"),
    ],
)
def test_aspect_classification(text, expected_aspect):
    assert expected_aspect in sentiment_service.classify_aspects(text)


def test_feedback_can_carry_multiple_aspects():
    aspects = sentiment_service.classify_aspects(
        "The funding target is high and the team has no track record for delivery."
    )
    assert len(aspects) >= 2


# --------------------------------------------------------------------------
# API behaviour
# --------------------------------------------------------------------------
def test_feedback_requires_authentication(client, live_campaign):
    # A genuine anonymous visitor: no session cookie from the fixture setup.
    client.cookies.clear()
    response = client.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "Anonymous drive-by comment on this campaign.", "rating": 5},
    )
    assert response.status_code == 401


def test_feedback_is_classified_and_aggregated(contributor, live_campaign):
    response = contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={
            "text": "Good social impact, but the funding target seems aggressive.",
            "rating": 4,
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["rating"] == 4

    # Classification runs as a background task, which TestClient executes.
    listed = contributor.get(f"/api/campaigns/{live_campaign['public_id']}/feedback").json()
    item = listed["items"][0]
    assert item["sentiment"] in ("POSITIVE", "NEUTRAL", "NEGATIVE")
    assert item["aspect"] is not None
    assert item["aspect_label"]

    summary = contributor.get(f"/api/campaigns/{live_campaign['public_id']}/sentiment").json()
    assert summary["feedback_count"] == 1
    assert summary["average_rating"] == 4.0
    total = (
        summary["positive_percentage"]
        + summary["neutral_percentage"]
        + summary["negative_percentage"]
    )
    assert abs(total - 100) < 0.1
    assert summary["aspect_distribution"]


def test_one_feedback_per_contributor_per_campaign(contributor, live_campaign):
    payload = {"text": "A perfectly reasonable first comment here.", "rating": 5}
    assert (
        contributor.post(
            f"/api/campaigns/{live_campaign['public_id']}/feedback", json=payload
        ).status_code
        == 201
    )
    second = contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback", json=payload
    )
    assert second.status_code == 409


def test_creator_cannot_review_own_campaign(creator, live_campaign):
    response = creator.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "My own campaign is excellent, obviously.", "rating": 5},
    )
    assert response.status_code == 409


def test_feedback_validation(contributor, live_campaign):
    short = contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "too short", "rating": 5},
    )
    assert short.status_code == 422
    bad_rating = contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "A long enough comment for the validator.", "rating": 9},
    )
    assert bad_rating.status_code == 422


def test_feedback_list_is_paginated(contributor, second_contributor, live_campaign):
    contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "The execution plan is clear and well documented.", "rating": 5},
    )
    second_contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "Concerned that the funding target is too aggressive.", "rating": 3},
    )
    page = contributor.get(
        f"/api/campaigns/{live_campaign['public_id']}/feedback?limit=1&offset=0"
    ).json()
    assert page["total"] == 2
    assert len(page["items"]) == 1


def test_community_insights_require_feedback(contributor, live_campaign):
    assert (
        contributor.get(
            f"/api/campaigns/{live_campaign['public_id']}/community-insights"
        ).status_code
        == 404
    )


def test_community_insights_summarise_aggregates(contributor, second_contributor, live_campaign):
    contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "Excellent social impact for rural village communities.", "rating": 5},
    )
    second_contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "The funding target seems unrealistic and too aggressive.", "rating": 2},
    )
    refreshed = contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/community-insights/refresh"
    )
    assert refreshed.status_code == 200, refreshed.text
    body = refreshed.json()
    assert body["feedback_count"] == 2
    assert body["community_summary"]
    assert body["top_concerns"]
    assert body["aspect_distribution"]
    assert "decision support" in body["disclaimer"]


def test_campaign_page_exposes_health_and_sentiment(client, contributor, live_campaign):
    contributor.post(
        f"/api/campaigns/{live_campaign['public_id']}/feedback",
        json={"text": "Strong impact but the timeline worries me a little.", "rating": 4},
    )
    page = client.get(f"/api/public/campaigns/{live_campaign['public_id']}").json()
    assert page["health"]["score"] >= 0
    assert page["health"]["label"] in ("Strong", "Healthy", "Watch", "At risk")
    assert "not a prediction" in page["health"]["note"]
    assert page["sentiment"]["feedback_count"] == 1
    assert page["analysis"]["risk_level"] in ("Low", "Medium", "High")


def test_public_campaign_never_leaks_creator_contact_details(client, live_campaign):
    import json as _json

    body = _json.dumps(
        client.get(f"/api/public/campaigns/{live_campaign['public_id']}").json()
    )
    assert "creator@example.com" not in body
    assert "password" not in body.lower()
    assert "ABCDE1234F" not in body  # the demo PAN from KYC
