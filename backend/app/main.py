"""CrowdWise API.

Smarter Crowdfunding. Stronger Communities.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    admin,
    auth,
    blockchain,
    campaigns,
    dashboard,
    feedback,
    files,
    governance,
    kyc,
    payments,
    public,
)
from app.core.config import settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.middleware.request_context import RateLimitMiddleware, RequestContextMiddleware
from app.workers import scheduler

configure_logging(settings.log_level, json_output=settings.is_production)
logger = get_logger(__name__)

DESCRIPTION = """
**CrowdWise — AI-Powered Community Crowdfunding & Governance Platform.**

Crowdfunding modelled as a governed community lifecycle rather than a payment:
creators are verified and AI-evaluated, campaigns are approved by a human
reviewer, contributions are verified server-side through Razorpay, community
feedback is classified and summarised, key events are anchored on an EVM chain,
and contributors decide the outcome when a target is missed.

**Boundaries this API keeps:**

* Razorpay is the source of truth for money. A client callback is a claim, never a fact.
* The blockchain is an audit surface, not a bank, and never holds personal data.
* AI is decision support. A human admin makes every approval decision.
"""

TAGS_METADATA = [
    {"name": "Auth", "description": "Registration, sign-in, session and role management."},
    {"name": "KYC", "description": "Demo identity verification (simulated, test data only)."},
    {"name": "Campaigns", "description": "Creator campaign lifecycle, documents, QR, dashboards."},
    {"name": "Public", "description": "Unauthenticated discovery and campaign pages."},
    {"name": "Payments", "description": "Razorpay orders, server-side verification, webhooks."},
    {"name": "Contributions", "description": "Verified contributions and their records."},
    {"name": "Feedback", "description": "Community ratings, comments and sentiment."},
    {"name": "AI", "description": "Campaign analysis and community intelligence."},
    {"name": "Governance", "description": "Contributor voting when a target is missed."},
    {"name": "Blockchain", "description": "Anchored records, status and retries."},
    {"name": "Admin", "description": "Review queue, decisions, platform metrics, demo controls."},
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.assert_production_safe()
    logger.info(
        "startup",
        environment=settings.environment,
        demo_mode=settings.demo_mode,
        ai_provider=settings.ai_provider,
        sentiment_provider=settings.sentiment_provider,
        payment_provider=settings.payment_provider,
        blockchain_provider=settings.blockchain_provider,
        storage_provider=settings.storage_provider,
    )
    # Background jobs run in-process. Migrations are never applied automatically:
    # schema changes are an explicit `alembic upgrade head`.
    scheduler.start()
    blockchain_service_start()
    try:
        yield
    finally:
        scheduler.stop()
        logger.info("shutdown")


def blockchain_service_start() -> None:
    from app.services import blockchain_service

    blockchain_service.start_worker()


app = FastAPI(
    title="CrowdWise API",
    description=DESCRIPTION,
    version="1.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,  # cookie auth requires an explicit origin allowlist
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token", "X-Request-Id"],
    expose_headers=["X-Request-Id"],
)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(RequestContextMiddleware)

register_exception_handlers(app)

app.include_router(auth.router)
app.include_router(kyc.router)
app.include_router(campaigns.router)
app.include_router(public.router)
app.include_router(payments.router)
app.include_router(payments.webhook_router)
app.include_router(feedback.router)
app.include_router(governance.router)
app.include_router(blockchain.router)
app.include_router(dashboard.router)
app.include_router(admin.router)
app.include_router(admin.demo_router)
app.include_router(files.router)


@app.get("/health", tags=["Admin"])
def health() -> dict:
    """Liveness and configuration probe used by Docker health checks."""
    from sqlalchemy import text

    from app.core.db import engine

    database_ok = True
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - failure path
        database_ok = False
        logger.error("health_db_failed", error=str(exc))

    return {
        "status": "ok" if database_ok else "degraded",
        "service": "crowdwise-api",
        "version": "1.0.0",
        "database": "ok" if database_ok else "unavailable",
        "demo_mode": settings.demo_mode,
        "providers": {
            "ai": settings.ai_provider,
            "sentiment": settings.sentiment_provider,
            "payments": settings.payment_provider,
            "blockchain": settings.blockchain_provider,
            "storage": settings.storage_provider,
            "kyc": settings.kyc_provider,
        },
    }


@app.get("/", tags=["Admin"])
def root() -> dict:
    return {
        "name": "CrowdWise",
        "tagline": "Smarter Crowdfunding. Stronger Communities.",
        "docs": "/docs",
        "health": "/health",
    }
