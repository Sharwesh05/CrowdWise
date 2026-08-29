"""Authentication, authorization and password handling."""

from __future__ import annotations

from tests.conftest import DEMO_PASSWORD, make_user


def test_register_and_login_sets_httponly_cookie(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Asha Menon",
            "email": "asha@example.com",
            "password": DEMO_PASSWORD,
            "role": "CREATOR",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["user"]["role"] == "CREATOR"
    assert body["user"]["kyc_status"] == "NOT_STARTED"
    assert body["csrf_token"]

    cookie_header = response.headers.get("set-cookie", "")
    assert "cw_access" in cookie_header
    assert "httponly" in cookie_header.lower()

    login = client.post(
        "/api/auth/login", json={"email": "asha@example.com", "password": DEMO_PASSWORD}
    )
    assert login.status_code == 200


def test_password_is_hashed_not_stored(client, db):
    from app.services import auth_service

    make_user(client, "hash@example.com", "CONTRIBUTOR")
    user = auth_service.get_by_email(db, "hash@example.com")
    assert user.password_hash != DEMO_PASSWORD
    assert user.password_hash.startswith("$2b$")


def test_weak_password_rejected(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Weak Password",
            "email": "weak@example.com",
            "password": "nodigitshere",
            "role": "CONTRIBUTOR",
        },
    )
    assert response.status_code == 422
    assert "number" in response.json()["error"]["message"].lower()


def test_duplicate_email_rejected(client):
    make_user(client, "dupe@example.com", "CONTRIBUTOR")
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Someone Else",
            "email": "dupe@example.com",
            "password": DEMO_PASSWORD,
            "role": "CONTRIBUTOR",
        },
    )
    assert response.status_code == 409


def test_admin_cannot_self_register(client):
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Sneaky Admin",
            "email": "sneaky@example.com",
            "password": DEMO_PASSWORD,
            "role": "ADMIN",
        },
    )
    assert response.status_code == 422


def test_wrong_password_and_unknown_email_are_indistinguishable(client):
    make_user(client, "real@example.com", "CONTRIBUTOR")
    wrong = client.post(
        "/api/auth/login", json={"email": "real@example.com", "password": "WrongPass123"}
    )
    unknown = client.post(
        "/api/auth/login", json={"email": "ghost@example.com", "password": DEMO_PASSWORD}
    )
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json()["error"]["message"] == unknown.json()["error"]["message"]


def test_protected_endpoint_requires_authentication(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.get("/api/campaigns/my").status_code == 401
    assert client.get("/api/admin/dashboard").status_code == 401


def test_role_enforcement(contributor, admin):
    """A contributor cannot reach admin surfaces; an admin can."""
    assert contributor.get("/api/admin/dashboard").status_code == 403
    assert admin.get("/api/admin/dashboard").status_code == 200


def test_me_returns_session_projection(creator):
    response = creator.get("/api/auth/me")
    assert response.status_code == 200
    body = response.json()
    assert body["email"] == "creator@example.com"
    assert "password_hash" not in body


def test_change_password(client, contributor):
    response = contributor.post(
        "/api/auth/change-password",
        json={"current_password": DEMO_PASSWORD, "new_password": "BrandNew123"},
    )
    assert response.status_code == 200
    assert (
        client.post(
            "/api/auth/login",
            json={"email": contributor.email, "password": "BrandNew123"},
        ).status_code
        == 200
    )
