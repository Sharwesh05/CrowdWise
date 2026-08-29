"""Explicit campaign state machine.

No API request may set an arbitrary status. Every status change goes through
`transition()`, which refuses moves that are not in the allowed map. This is the
guard that keeps the lifecycle honest — a creator cannot publish by patching a
field, and a campaign cannot reach GOVERNANCE without having completed.
"""

from __future__ import annotations

from app.core.enums import CampaignStatus
from app.core.errors import InvalidTransitionError

S = CampaignStatus

ALLOWED_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    S.DRAFT: {S.KYC_PENDING, S.CLOSED},
    S.KYC_PENDING: {S.FEE_PENDING, S.DRAFT, S.CLOSED},
    S.FEE_PENDING: {S.ANALYSIS_PENDING, S.DRAFT, S.CLOSED},
    S.ANALYSIS_PENDING: {S.UNDER_REVIEW, S.FEE_PENDING, S.CLOSED},
    S.UNDER_REVIEW: {S.APPROVED, S.REJECTED, S.DRAFT},
    S.APPROVED: {S.LIVE, S.CLOSED},
    S.LIVE: {S.COMPLETED, S.CLOSED},
    S.COMPLETED: {S.TARGET_MET, S.TARGET_MISSED},
    S.TARGET_MET: {S.CLOSED},
    S.TARGET_MISSED: {S.GOVERNANCE, S.REFUND_PENDING, S.CLOSED},
    S.GOVERNANCE: {S.REFUND_PENDING, S.CONTINUED, S.CLOSED},
    S.REFUND_PENDING: {S.CLOSED},
    S.CONTINUED: {S.LIVE, S.COMPLETED, S.CLOSED},
    S.CLOSED: set(),
    S.REJECTED: {S.DRAFT},
}

# Human-readable descriptions used in API errors and the admin UI.
STATUS_DESCRIPTIONS: dict[str, str] = {
    S.DRAFT: "Draft — being prepared by the creator",
    S.KYC_PENDING: "Waiting for creator identity verification",
    S.FEE_PENDING: "Waiting for the application fee to be verified",
    S.ANALYSIS_PENDING: "AI analysis in progress",
    S.UNDER_REVIEW: "Awaiting admin review",
    S.APPROVED: "Approved — ready to publish",
    S.LIVE: "Live and accepting contributions",
    S.COMPLETED: "Deadline reached — evaluating outcome",
    S.TARGET_MET: "Funding target achieved",
    S.TARGET_MISSED: "Funding target not achieved",
    S.GOVERNANCE: "Contributor governance vote open",
    S.REFUND_PENDING: "Refund being processed by payment infrastructure",
    S.CONTINUED: "Campaign continued by contributor vote",
    S.CLOSED: "Closed",
    S.REJECTED: "Rejected by admin review",
}


def can_transition(current: str, target: str) -> bool:
    try:
        return CampaignStatus(target) in ALLOWED_TRANSITIONS[CampaignStatus(current)]
    except (KeyError, ValueError):
        return False


def assert_transition(current: str, target: str) -> None:
    if current == target:
        return
    if not can_transition(current, target):
        allowed = sorted(str(s) for s in ALLOWED_TRANSITIONS.get(CampaignStatus(current), set()))
        raise InvalidTransitionError(
            f"Cannot move a campaign from {current} to {target}.",
            details={"current": current, "requested": target, "allowed": allowed},
        )


def transition(campaign, target: str) -> str:
    """Apply a validated transition to a Campaign instance."""
    assert_transition(campaign.status, target)
    previous = campaign.status
    campaign.status = target
    return previous


def next_states(current: str) -> list[str]:
    return sorted(str(s) for s in ALLOWED_TRANSITIONS.get(CampaignStatus(current), set()))
