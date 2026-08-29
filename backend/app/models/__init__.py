"""SQLAlchemy models.

Importing this package registers every mapper on the shared declarative Base —
which is what Alembic autogenerate and `Base.metadata.create_all` rely on.
"""

from app.core.db import Base
from app.models.campaign import (
    Campaign,
    CampaignApplication,
    CampaignDocument,
    CampaignEvent,
    CampaignOutcome,
)
from app.models.chain import AuditLog, BlockchainTransaction
from app.models.community import AIAnalysis, AICommunityInsight, Feedback
from app.models.governance import Vote
from app.models.payment import Contribution, Payment, WebhookEvent
from app.models.user import KYCVerification, User

__all__ = [
    "Base",
    "User",
    "KYCVerification",
    "Campaign",
    "CampaignApplication",
    "CampaignDocument",
    "CampaignOutcome",
    "CampaignEvent",
    "Payment",
    "Contribution",
    "WebhookEvent",
    "AIAnalysis",
    "Feedback",
    "AICommunityInsight",
    "Vote",
    "BlockchainTransaction",
    "AuditLog",
]
