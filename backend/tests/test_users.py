"""
tests/test_users.py

Test suite for the User Profile endpoints.

Endpoints tested
----------------
GET  /api/v1/users/me
PUT  /api/v1/users/me

All tests run against the SQLite in-memory database (see conftest.py).
"""

import pytest

from app.extensions import db
from app.models.user import User

BASE = "/api/v1/users"


# ── Helpers ───────────────────────────────────────────────────────────────────

def login(client, identifier="profile@example.com", identifier_type="email"):
    """Full OTP login flow — returns access_token."""
    r1 = client.post(
        "/api/v1/auth/request-otp",
        json={"identifier": identifier, "identifier_type": identifier_type},
    )
    assert r1.status_code == 200
    otp = r1.get_json()["otp"]

    r2 = client.post(
        "/api/v1/auth/verify-otp",
        json={"identifier": identifier, "identifier_type": identifier_type, "otp": otp},
    )
    assert r2.status_code == 200
    return r2.get_json()["access_token"]


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ══════════════════════════════════════════════════════════════════════════════
# GET /users/me
# ══════════════════════════════════════════════════════════════════════════════

class TestGetProfile:
    """GET /api/v1/users/me"""

    def test_get_profile_requires_jwt(self, client):
        """No token → 401."""
        resp = client.get(f"{BASE}/me")
        assert resp.status_code == 401

    def test_get_profile_with_valid_token(self, client):
        """Valid JWT → 200 with user fields."""
        token = login(client)
        resp  = client.get(f"{BASE}/me", headers=auth_headers(token))
        data  = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        user = data["user"]
        assert user["email"] == "profile@example.com"
        assert user["role"]  == "customer"
        assert user["is_verified"] is True
        assert "created_at" in user
        assert "updated_at" in user

    def test_get_profile_does_not_expose_sensitive_fields(self, client):
        """Response must NOT contain passwords, OTP hashes, or JWT secrets."""
        token     = login(client)
        resp      = client.get(f"{BASE}/me", headers=auth_headers(token))
        body_text = resp.get_data(as_text=True)

        assert "password"   not in body_text
        assert "otp_hash"   not in body_text
        assert "jwt_secret" not in body_text

    def test_get_profile_contains_timestamps(self, client):
        """Profile response should include created_at and updated_at."""
        token = login(client)
        resp  = client.get(f"{BASE}/me", headers=auth_headers(token))
        user  = resp.get_json()["user"]

        assert user["created_at"] is not None
        assert user["updated_at"] is not None


# ══════════════════════════════════════════════════════════════════════════════
# PUT /users/me
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateProfile:
    """PUT /api/v1/users/me"""

    def test_update_profile_requires_jwt(self, client):
        """No token → 401."""
        resp = client.put(f"{BASE}/me", json={"name": "New Name"})
        assert resp.status_code == 401

    def test_update_name_succeeds(self, client):
        """Changing name to a valid value → 200 with updated user."""
        token = login(client, "namechange@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"name": "Updated Name"},
            headers=auth_headers(token),
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"]        == "success"
        assert data["user"]["name"]  == "Updated Name"

    def test_update_name_persists_in_db(self, client, app):
        """Name change should be saved to the database."""
        token = login(client, "persist@example.com")
        client.put(
            f"{BASE}/me",
            json={"name": "Persisted Name"},
            headers=auth_headers(token),
        )
        with app.app_context():
            user = User.query.filter_by(email="persist@example.com").first()
            assert user.name == "Persisted Name"

    def test_empty_name_rejected(self, client):
        """Empty string name → 400."""
        token = login(client, "emptyname@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"name": ""},
            headers=auth_headers(token),
        )
        assert resp.status_code == 400

    def test_name_too_long_rejected(self, client):
        """Name exceeding 120 characters → 400."""
        token = login(client, "longname@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"name": "A" * 121},
            headers=auth_headers(token),
        )
        assert resp.status_code == 400

    def test_whitespace_only_name_rejected(self, client):
        """Whitespace-only name → 400."""
        token = login(client, "wsname@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"name": "   "},
            headers=auth_headers(token),
        )
        assert resp.status_code == 400

    def test_email_change_ignored_with_warning(self, client):
        """Attempting to change email → 200 but warning returned, email unchanged."""
        token = login(client, "emailchange@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"email": "newemail@example.com"},
            headers=auth_headers(token),
        )
        data = resp.get_json()

        assert resp.status_code == 200
        # Email must remain unchanged.
        assert data["user"]["email"] == "emailchange@example.com"
        # A warning should be present.
        assert "warnings" in data
        assert any("email" in w for w in data["warnings"])

    def test_phone_change_ignored_with_warning(self, client):
        """Attempting to change phone → 200 but warning returned."""
        token = login(client, "phonechange@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"phone": "+919999999999"},
            headers=auth_headers(token),
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert "warnings" in data
        assert any("phone" in w for w in data["warnings"])

    def test_cannot_change_role(self, client):
        """Attempting to change role → 200 but warning returned, role unchanged."""
        token = login(client, "rolechange@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"role": "admin"},
            headers=auth_headers(token),
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["user"]["role"] == "customer"
        assert "warnings" in data

    def test_cannot_change_is_verified(self, client):
        """Attempting to set is_verified=false → 200 but warning, value unchanged."""
        token = login(client, "verified@example.com")
        resp  = client.put(
            f"{BASE}/me",
            json={"is_verified": False},
            headers=auth_headers(token),
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["user"]["is_verified"] is True
        assert "warnings" in data

    def test_no_body_returns_400(self, client):
        """Empty request body → 400."""
        token = login(client, "nobody@example.com")
        resp  = client.put(
            f"{BASE}/me",
            content_type="application/json",
            data="",
            headers=auth_headers(token),
        )
        assert resp.status_code == 400
