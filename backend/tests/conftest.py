"""Test fixtures.

The suite runs against a throwaway SQLite database with every provider set to its
demo/mock implementation, so it needs no Postgres, no Razorpay keys, no LLM and
no chain node — while still exercising the real verification, state-machine and
idempotency code paths.
"""

from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta, timezone

# Must be set before app.core.config is imported anywhere.
_DB_FD, _DB_PATH = tempfile.mkstemp(suffix=".db", prefix="crowdwise-test-")
os.close(_DB_FD)
os.environ.update(
    {
        "DATABASE_URL": f"sqlite+pysqlite:///{_DB_PATH.replace(os.sep, '/')}",
        "ENVIRONMENT": "test",
        "DEMO_MODE": "true",
        "AI_PROVIDER": "mock",
        "SENTIMENT_PROVIDER": "mock",
        "PAYMENT_PROVIDER": "demo",
        "BLOCKCHAIN_PROVIDER": "mock",
        "STORAGE_PROVIDER": "local",
        "STORAGE_LOCAL_DIR": tempfile.mkdtemp(prefix="crowdwise-storage-"),
        "JWT_SECRET": "test-secret-value-for-suite-only-0123456789",
        "COOKIE_SECRET": "test-cookie-secret-for-suite-only-0123456789",
        "CHAIN_HASH_SALT": "test-chain-salt",
        "RATE_LIMIT_AUTH_PER_MINUTE": "1000",
        "RATE_LIMIT_DEFAULT_PER_MINUTE": "5000",
        "LOG_LEVEL": "WARNING",
    }
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine, get_db  # noqa: E402
from app.core.enums import UserRole  # noqa: E402
from app.main import app  # noqa: E402
from app.services import auth_service, blockchain_service  # noqa: E402

DEMO_PASSWORD = "TestPass123"


@pytest.fixture(scope="session", autouse=True)
def _schema():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_tables(_schema):
    """Truncate between tests so each one starts from a known empty state."""
    yield
    with engine.begin() as connection:
        for table in reversed(Base.metadata.sorted_tables):
            connection.exec_driver_sql(f'DELETE FROM "{table.name}"')
    # The simulated chain keeps an append-only ledger for the life of the
    # process, so each test gets a fresh one alongside a fresh database.
    blockchain_service.reset_provider()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def client():
    session = SessionLocal()

    def _override():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = _override
    # Constructed without the context manager on purpose: that skips the lifespan
    # so background worker threads never race the assertions.
    test_client = TestClient(app)
    try:
        yield test_client
    finally:
        app.dependency_overrides.clear()
        session.close()


class ApiUser:
    """A registered account plus a client bound to its bearer token."""

    def __init__(self, client: TestClient, email: str, role: str, name: str):
        self.client = client
        self.email = email
        self.role = role
        self.name = name
        self.token = ""
        self.id = 0

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}"}

    def get(self, url, **kwargs):
        return self.client.get(url, headers=self.headers, **kwargs)

    def post(self, url, **kwargs):
        return self.client.post(url, headers=self.headers, **kwargs)

    def patch(self, url, **kwargs):
        return self.client.patch(url, headers=self.headers, **kwargs)

    def delete(self, url, **kwargs):
        return self.client.delete(url, headers=self.headers, **kwargs)


def make_user(client: TestClient, email: str, role: str, name: str = "Test User") -> ApiUser:
    from app.core.security import create_token

    response = client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": DEMO_PASSWORD, "role": role},
    )
    assert response.status_code == 201, response.text
    user = ApiUser(client, email, role, name)
    user.id = response.json()["user"]["id"]
    user.token = create_token(user.id, "access", {"role": role, "email": email})
    return user


@pytest.fixture
def creator(client) -> ApiUser:
    return make_user(client, "creator@example.com", str(UserRole.CREATOR), "Asha Menon")


@pytest.fixture
def contributor(client) -> ApiUser:
    return make_user(client, "backer@example.com", str(UserRole.CONTRIBUTOR), "Ravi Kumar")


@pytest.fixture
def second_contributor(client) -> ApiUser:
    return make_user(client, "backer2@example.com", str(UserRole.CONTRIBUTOR), "Neha Shah")


@pytest.fixture
def admin(client) -> ApiUser:
    """Admins are provisioned directly — never through self-signup."""
    from app.core.security import create_token

    session = SessionLocal()
    try:
        user = auth_service.register(
            session,
            name="Platform Admin",
            email="admin@example.com",
            password=DEMO_PASSWORD,
            role=str(UserRole.CONTRIBUTOR),
        )
        user.role = str(UserRole.ADMIN)
        session.commit()
        api_user = ApiUser(client, user.email, str(UserRole.ADMIN), user.name)
        api_user.id = user.id
        api_user.token = create_token(
            user.id, "access", {"role": str(UserRole.ADMIN), "email": user.email}
        )
        return api_user
    finally:
        session.close()


KYC_PAYLOAD = {
    "full_name": "Asha Menon",
    "date_of_birth": "1990-04-12",
    "pan_number": "ABCDE1234F",
    "address": "12 Demo Street, Test Nagar, Bengaluru 560001",
    "bank_account_number": "000123456789",
    "bank_ifsc": "DEMO0001234",
    "confirm_demo_data": True,
}


def campaign_payload(**overrides) -> dict:
    payload = {
        "title": "Solar Water Purifier for Rural Schools",
        "short_description": (
            "Solar-powered water purifiers for 40 rural schools across two districts."
        ),
        "description": (
            "We build and deploy solar-powered water purification units for rural schools. "
            "Each unit serves 300 students daily and runs without grid electricity. "
            "Phase one covers 40 schools across two districts over six months, working with "
            "a manufacturing partner in Coimbatore and the district education office. "
            "The budget covers 40 units at INR 18,000 each, installation, one year of "
            "maintenance, and teacher training for upkeep. Our team has deployed 12 pilot "
            "units already and has three engineers with water treatment experience."
        ),
        "problem_statement": (
            "Rural schools in the region rely on untreated groundwater with high fluoride "
            "levels. Waterborne illness accounts for a large share of student absence, and "
            "existing purifiers need grid power that is unavailable for most of the day."
        ),
        "proposed_solution": (
            "A solar-powered multi-stage purifier designed for school use, with a phased "
            "deployment timeline, a local manufacturing partner, and a maintenance plan "
            "delivered through trained teachers in each school."
        ),
        "expected_impact": "12,000 students in 40 rural schools get safe drinking water daily.",
        "category": "ENVIRONMENT",
        "target_amount": "1000000.00",
        "minimum_contribution": "500.00",
        "deadline": (datetime.now(timezone.utc) + timedelta(days=45)).isoformat(),
    }
    payload.update(overrides)
    return payload
