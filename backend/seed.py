"""Seed CrowdWise with clearly-labelled demo data.

Everything created here is flagged `is_demo=True` and every campaign title is
suffixed so nobody can mistake seeded records for real ones. The passwords below
are for local development only and are documented in the README.

Run:  python seed.py           (add --reset to wipe and reseed)

The seed does not shortcut business rules: campaigns are walked through the real
state machine, application fees go through the real signature verification, and
contributions are created only by the verified-payment path.
"""

from __future__ import annotations

import argparse
import sys
from datetime import timedelta
from decimal import Decimal

from pathlib import Path
from sqlalchemy import select, text

from app.core.config import settings
from app.core.db import Base, SessionLocal, engine, utcnow
from app.core.enums import CampaignStatus, UserRole
from app.core.logging import configure_logging, get_logger
from app.models.campaign import Campaign
from app.models.community import Feedback
from app.models.user import User
from app.services import (
    ai_service,
    auth_service,
    blockchain_service,
    campaign_service,
    feedback_service,
    governance_service,
    kyc_service,
    payment_service,
    sentiment_service,
)
from app.services.campaign_service import CampaignDraft
from app.services.kyc_service import KYCSubmission

logger = get_logger("seed")

DEMO_PASSWORD = "Demo@12345"
DEMO_SUFFIX = " (DEMO)"

ACCOUNTS = [
    ("admin@example.com", "Priya Nair", UserRole.ADMIN, "Platform administrator"),
    ("creator@example.com", "Asha Menon", UserRole.CREATOR, "Primary demo creator"),
    ("creator2@example.com", "Vikram Rao", UserRole.CREATOR, "Second demo creator"),
    ("contributor@example.com", "Ravi Kumar", UserRole.CONTRIBUTOR, "Primary demo contributor"),
    ("contributor2@example.com", "Neha Shah", UserRole.CONTRIBUTOR, "Second demo contributor"),
    ("contributor3@example.com", "Arjun Iyer", UserRole.CONTRIBUTOR, "Third demo contributor"),
]

KYC = KYCSubmission(
    full_name="Demo Creator",
    date_of_birth="1990-04-12",
    pan_number="ABCDE1234F",
    address="12 Demo Street, Test Nagar, Bengaluru 560001",
    bank_account_number="000123456789",
    bank_ifsc="DEMO0001234",
)

# ---------------------------------------------------------------------------
# Campaign definitions
# ---------------------------------------------------------------------------
CAMPAIGNS = [
    {
        "key": "solar",
        "creator": "creator@example.com",
        "title": "Solar Water Purifier for Rural Schools",
        "category": "ENVIRONMENT",
        "target": "1000000.00",
        "minimum": "500.00",
        "days": 45,
        "short": "Solar-powered water purifiers for 40 rural schools across two districts.",
        "problem": (
            "Rural schools across the district rely on untreated groundwater with fluoride "
            "levels well above the safe limit. Waterborne illness is one of the largest "
            "causes of student absence, and conventional purifiers need grid electricity "
            "that is unavailable for most of the school day."
        ),
        "solution": (
            "A solar-powered multi-stage purification unit designed specifically for school "
            "use. Each unit produces 500 litres of safe drinking water per day with no grid "
            "connection. Deployment runs in three phases over six months with a "
            "manufacturing partner in Coimbatore and the district education office, and "
            "each school gets a trained teacher-custodian for routine upkeep."
        ),
        "impact": "12,000 students across 40 rural schools get safe drinking water every day.",
        "description": (
            "CrowdWise campaign for a solar water purification programme.\n\n"
            "Phase 1 covers 40 schools across two districts over six months. The budget "
            "covers 40 units at INR 18,000 each (INR 7,20,000), installation and transport "
            "(INR 1,20,000), one year of maintenance and spares (INR 1,00,000), and "
            "teacher training plus water-quality testing (INR 60,000).\n\n"
            "We have already deployed 12 pilot units over the past year, and the team "
            "includes three engineers with water treatment experience and an operations "
            "lead who previously ran a district-level sanitation programme.\n\n"
            "After phase 1, the same model can be replicated in neighbouring districts "
            "using the manufacturing partnership already in place."
        ),
        "state": "live",
        "contributions": [
            ("contributor@example.com", "25000.00"),
            ("contributor2@example.com", "50000.00"),
            ("contributor3@example.com", "15000.00"),
        ],
        "feedback": [
            (
                "contributor@example.com",
                "Good social impact, but the funding target seems aggressive for a first phase.",
                4,
            ),
            (
                "contributor2@example.com",
                "Excellent initiative for village communities. The solar approach is smart "
                "and the pilot data makes it credible.",
                5,
            ),
            (
                "contributor3@example.com",
                "Who is on the team and what is their delivery track record? The execution "
                "plan needs a clearer timeline.",
                3,
            ),
        ],
    },
    {
        "key": "library",
        "creator": "creator2@example.com",
        "title": "Community Digital Library Network",
        "category": "EDUCATION",
        "target": "600000.00",
        "minimum": "250.00",
        "days": 30,
        "short": "Ten offline-first digital learning centres for students without home internet.",
        "problem": (
            "Students in the taluk have smartphones but no affordable data, so online "
            "learning material is effectively out of reach. The nearest library is 14 km "
            "away and holds no digital resources at all."
        ),
        "solution": (
            "Ten offline-first digital library nodes, each a low-power server preloaded "
            "with curriculum content, textbooks and video lessons, served over local "
            "wi-fi. No internet connection is required to use a node, and content is "
            "refreshed monthly by a visiting coordinator."
        ),
        "impact": "4,000 students get free access to curriculum-aligned digital learning.",
        "description": (
            "CrowdWise campaign for an offline-first digital library network.\n\n"
            "Each node costs INR 45,000 including the server, display units, solar backup "
            "and one year of content updates. Ten nodes are planned across the taluk, "
            "placed in existing panchayat buildings so there is no rent.\n\n"
            "Content is sourced from openly licensed repositories and the state curriculum "
            "board. A local coordinator visits each node monthly to refresh content and "
            "collect usage data.\n\n"
            "Two pilot nodes have been running for eight months with 600 registered "
            "student users between them."
        ),
        "state": "live",
        "contributions": [
            ("contributor@example.com", "10000.00"),
            ("contributor2@example.com", "20000.00"),
        ],
        "feedback": [
            (
                "contributor@example.com",
                "Very useful and well thought out. The offline approach solves the real "
                "problem here.",
                5,
            ),
            (
                "contributor2@example.com",
                "How will you scale this beyond ten nodes, and who maintains the hardware "
                "long term?",
                4,
            ),
        ],
    },
    {
        "key": "clinic",
        "creator": "creator@example.com",
        "title": "Mobile Health Clinic for Coastal Villages",
        "category": "HEALTHCARE",
        "target": "1500000.00",
        "minimum": "500.00",
        "days": 60,
        "short": "A mobile clinic serving eighteen coastal villages with no local health centre.",
        "problem": (
            "Eighteen coastal villages have no primary health centre within 20 km. Routine "
            "check-ups are skipped and treatable conditions become emergencies, with the "
            "burden falling hardest on elderly residents and young children."
        ),
        "solution": (
            "A fully equipped mobile clinic running a fixed weekly route across eighteen "
            "villages, staffed by a doctor, a nurse and a technician, with basic diagnostics "
            "on board and a referral link to the district hospital."
        ),
        "impact": "Regular primary healthcare for roughly 9,000 coastal residents.",
        "description": (
            "CrowdWise campaign for a mobile primary healthcare service.\n\n"
            "The budget covers the vehicle and medical fit-out (INR 11,00,000), diagnostic "
            "equipment (INR 2,50,000) and the first six months of consumables and fuel "
            "(INR 1,50,000). Staff salaries are covered by an existing grant.\n\n"
            "The route and schedule have been agreed with the district health office, and "
            "referral arrangements with the district hospital are already in place."
        ),
        "state": "under_review",
        "contributions": [],
        "feedback": [],
    },
    {
        "key": "compost",
        "creator": "creator2@example.com",
        "title": "Neighbourhood Composting Units",
        "category": "ENVIRONMENT",
        "target": "800000.00",
        "minimum": "500.00",
        "days": 20,
        "short": "Decentralised composting units to divert ward waste from landfill.",
        "problem": (
            "The ward sends 2.4 tonnes of wet waste to landfill every day. Collection is "
            "irregular, street corners accumulate refuse, and the landfill site is already "
            "beyond its designed capacity."
        ),
        "solution": (
            "Twelve decentralised aerobic composting units placed across the ward, each "
            "processing 200 kg of wet waste daily. Residents deposit segregated waste and "
            "the resulting compost is distributed free to local gardens and terrace farms."
        ),
        "impact": "2.4 tonnes of wet waste diverted from landfill every day.",
        "description": (
            "CrowdWise campaign for decentralised ward composting.\n\n"
            "Each unit costs INR 55,000 installed, with INR 1,40,000 covering the first "
            "year of operator wages and maintenance across all twelve sites.\n\n"
            "This campaign is seeded in a completed, target-missed state so the governance "
            "flow can be demonstrated end to end."
        ),
        # Deliberately ends short of target so the demo always has a live
        # governance round to show.
        "state": "governance",
        "contributions": [
            ("contributor@example.com", "5000.00"),
            ("contributor2@example.com", "7500.00"),
            ("contributor3@example.com", "2500.00"),
        ],
        "feedback": [
            (
                "contributor@example.com",
                "The funding target is unrealistic for twelve units and the timeline is "
                "far too short.",
                2,
            ),
            (
                "contributor2@example.com",
                "Great impact for the neighbourhood, I would support a smaller phase one.",
                4,
            ),
            (
                "contributor3@example.com",
                "Concerned about who operates the units after the first year of funding.",
                3,
            ),
        ],
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ensure_user(db, email: str, name: str, role: str) -> User:
    existing = auth_service.get_by_email(db, email)
    if existing:
        return existing
    if role == UserRole.ADMIN:
        # Admin accounts are provisioned, never self-registered.
        user = auth_service.register(
            db, name=name, email=email, password=DEMO_PASSWORD, role=str(UserRole.CONTRIBUTOR)
        )
        user.role = str(UserRole.ADMIN)
    else:
        user = auth_service.register(
            db, name=name, email=email, password=DEMO_PASSWORD, role=str(role)
        )
    user.is_demo = True
    db.flush()
    return user


def verify_kyc(db, user: User) -> None:
    if user.is_kyc_verified:
        return
    kyc_service.submit_kyc(db, user, KYC)
    kyc_service.finalize_kyc(db, user)


def pay(db, payment) -> None:
    """Complete a payment through the real signature-verification path."""
    provider = payment_service.get_provider()
    gateway_payment_id, signature = provider.simulate_success(payment.razorpay_order_id)
    payment_service.verify_checkout_callback(
        db,
        order_id=payment.razorpay_order_id,
        payment_id=gateway_payment_id,
        signature=signature,
        actor_id=payment.user_id,
    )


def build_campaign(db, spec: dict, users: dict[str, User], admin: User) -> Campaign:
    creator = users[spec["creator"]]
    verify_kyc(db, creator)

    campaign = campaign_service.create_campaign(
        db,
        creator,
        CampaignDraft(
            title=spec["title"] + DEMO_SUFFIX,
            short_description=spec["short"],
            description=spec["description"],
            problem_statement=spec["problem"],
            proposed_solution=spec["solution"],
            expected_impact=spec["impact"],
            category=spec["category"],
            target_amount=Decimal(spec["target"]),
            minimum_contribution=Decimal(spec["minimum"]),
            deadline=utcnow() + timedelta(days=spec["days"]),
        ),
    )
    campaign.is_demo = True
    db.flush()

    # Walk the real lifecycle: submit → fee → analysis → review.
    campaign_service.submit_application(db, campaign, creator)
    fee_payment = payment_service.create_application_fee_order(db, campaign, creator)
    pay(db, fee_payment)
    campaign_service.run_analysis_and_advance(db, campaign, actor_id=creator.id)

    if spec["state"] == "under_review":
        return campaign

    campaign_service.approve_campaign(db, campaign, admin, notes="Approved for the demo.")

    for email, amount in spec["contributions"]:
        backer = users[email]
        contribution_payment = payment_service.create_contribution_order(
            db, campaign, backer, Decimal(amount)
        )
        pay(db, contribution_payment)

    # Create every comment first, then classify them in one batch. Per-item
    # classification against an LLM provider costs a request each, which turned
    # a four-campaign seed into a multi-minute wait.
    created_feedback = [
        feedback_service.create_feedback(db, campaign, users[email], text, rating)
        for email, text, rating in spec["feedback"]
    ]
    if created_feedback:
        sentiment_service.analyze_batch(db, created_feedback)

    if spec["feedback"]:
        ai_service.generate_community_insights(db, campaign)

    blockchain_service.sync_pending_contributions(db)

    if spec["state"] == "governance":
        # Force the deadline so the campaign completes short of target and the
        # predefined outcome (a contributor vote) opens.
        campaign.deadline = utcnow()
        db.flush()
        campaign_service.complete_campaign(db, campaign, actor_id=admin.id)
        # One contributor has already voted, so the round shows real activity.
        governance_service.cast_vote(
            db, campaign, users["contributor@example.com"], "REFUND"
        )

    return campaign


def reset_database() -> None:
    """Drop everything and rebuild the schema.

    On PostgreSQL this drops the whole schema rather than using
    `Base.metadata.drop_all`. drop_all emits a DROP for each constraint the
    models declare by name, which fails with UndefinedObject when the live
    schema was built by Alembic and named its constraints differently — the
    common case, since `alembic upgrade head` is the documented setup path.
    Dropping the schema is also indifferent to objects the models no longer know
    about, such as a table left behind by a reverted migration.

    Alembic is stamped afterwards, because create_all records no revision and an
    unstamped database makes the next `alembic upgrade head` replay the initial
    migration and fail on tables that already exist.
    """
    logger.warning("dropping_all_tables")
    if engine.dialect.name == "postgresql":
        with engine.begin() as connection:
            connection.execute(text("DROP SCHEMA public CASCADE"))
            connection.execute(text("CREATE SCHEMA public"))
    else:
        Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    _stamp_alembic_head()


def _stamp_alembic_head() -> None:
    """Record the current head so later migrations apply cleanly."""
    try:
        from alembic import command  # noqa: PLC0415
        from alembic.config import Config  # noqa: PLC0415

        ini = Path(__file__).resolve().parent / "alembic.ini"
        if not ini.exists():
            logger.warning("alembic_ini_missing", path=str(ini))
            return
        command.stamp(Config(str(ini)), "head")
    except Exception as exc:
        # Not fatal: the data is seeded either way, and the operator can stamp by
        # hand. Say so loudly rather than leaving a silent trap.
        logger.warning("alembic_stamp_failed", error=str(exc))
        print(
            "  NOTE: could not stamp Alembic. Run `alembic stamp head` before "
            "your next `alembic upgrade head`."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed CrowdWise demo data")
    parser.add_argument("--reset", action="store_true", help="drop and recreate all tables first")
    args = parser.parse_args()

    configure_logging(settings.log_level)

    if not settings.demo_mode:
        print("Refusing to seed: DEMO_MODE is false. Seed data is for local demos only.")
        return 1

    if args.reset:
        if settings.blockchain_provider == "web3":
            # Campaign references are derived deterministically from the public
            # id, so reusing the same titles against a chain that still holds the old
            # run will revert with CampaignExists / VotingHasClosed.
            print()
            print(
                "NOTE: BLOCKCHAIN_PROVIDER=web3 and the database is being reset. "
                "Restart the Hardhat node too, or campaign references from the "
                "previous run still exist on chain and anchoring will be skipped."
            )
            print()
        reset_database()
    else:
        Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        if db.execute(select(Campaign.id)).first() and not args.reset:
            print("Database already contains campaigns. Re-run with --reset to reseed.")
            return 0

        users: dict[str, User] = {}
        for email, name, role, _ in ACCOUNTS:
            users[email] = ensure_user(db, email, name, str(role))
        db.flush()
        admin = users["admin@example.com"]

        created = []
        for spec in CAMPAIGNS:
            campaign = build_campaign(db, spec, users, admin)
            created.append(campaign)
            db.commit()

        print("\n" + "=" * 72)
        print("  CrowdWise — demo data seeded")
        print("=" * 72)
        print("\nAccounts (LOCAL DEVELOPMENT ONLY — password is the same for all):")
        print(f"  password: {DEMO_PASSWORD}\n")
        for email, name, role, note in ACCOUNTS:
            print(f"  {role:<12} {email:<28} {name:<14} {note}")

        print("\nCampaigns:")
        for campaign in created:
            db.refresh(campaign)
            print(
                f"  {campaign.public_id:<9} {campaign.status:<14} "
                f"INR {campaign.raised_amount:>12,.0f} / {campaign.target_amount:<12,.0f} "
                f"{campaign.title}"
            )

        governance = [c for c in created if c.status == CampaignStatus.GOVERNANCE]
        if governance:
            print(
                f"\n  Governance round open on {governance[0].public_id} — "
                "sign in as a contributor to vote."
            )

        feedback_count = len(db.execute(select(Feedback)).scalars().all())
        print(f"\n  {feedback_count} feedback items classified for sentiment and aspects.")
        print(f"  Providers: ai={settings.ai_provider}, sentiment={settings.sentiment_provider}, "
              f"payments={settings.payment_provider}, chain={settings.blockchain_provider}")
        print("\n  All seeded records are marked DEMO.")
        print("=" * 72 + "\n")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
