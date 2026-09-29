"""
tests/test_admin_auth.py

Automated tests for the Admin Authentication system.

Coverage
--------
1.  Successful admin login.
2.  Login with an incorrect password.
3.  Login with an unknown username.
4.  Login with a disabled admin account.
5.  Accessing an admin endpoint without a token.
6.  Accessing an admin endpoint with an invalid token.
7.  Accessing an admin endpoint using a normal user JWT.
8.  Accessing an admin endpoint using a valid admin JWT.
9.  Password hashes are stored, not plain text.
10. Admin password/hash is never exposed in API responses.
11. Initial admin cannot be duplicated via init_admin_from_env.
12. Existing user auth/APIs continue to work.
13. Admin /logout revokes the token.
"""

import pytest
from unittest.mock import patch

from app.models.admin import Admin
from app.services.admin_service import AdminService, ADMIN_SUB_TYPE

BASE = "/api/v1/admin"
AUTH_BASE = "/api/v1/auth"


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _create_admin(app, username="testadmin", password="Secr3t!", active=True):
    """Helper: insert an Admin row directly into the test DB."""
    with app.app_context():
        from app.extensions import db
        admin = Admin(username=username, is_active=active)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        return admin.id


def _login_admin(client, username="testadmin", password="Secr3t!"):
    """Helper: POST /api/v1/admin/login and return the response."""
    return client.post(f"{BASE}/login", json={
        "username": username,
        "password": password,
    })


def _get_admin_token(client, app, username="testadmin", password="Secr3t!"):
    """Helper: create admin + log in, return access_token string."""
    _create_admin(app, username=username, password=password)
    resp = _login_admin(client, username=username, password=password)
    return resp.get_json()["access_token"]


def _get_user_token(client):
    """Helper: create a regular customer and return their access_token."""
    r1 = client.post(f"{AUTH_BASE}/request-otp", json={
        "identifier": "user@example.com",
        "identifier_type": "email",
    })
    otp = r1.get_json()["otp"]
    r2 = client.post(f"{AUTH_BASE}/verify-otp", json={
        "identifier": "user@example.com",
        "identifier_type": "email",
        "otp": otp,
    })
    return r2.get_json()["access_token"]


# ══════════════════════════════════════════════════════════════════════════════
# 1. Successful admin login
# ══════════════════════════════════════════════════════════════════════════════

class TestAdminLogin:

    def test_successful_login_returns_200(self, client, app):
        """Valid credentials return 200 with tokens and admin profile."""
        _create_admin(app)
        resp = _login_admin(client)
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        assert "access_token" in data
        assert "refresh_token" in data
        assert "admin" in data

    def test_login_response_contains_admin_profile(self, client, app):
        """Login response includes id, username, is_active."""
        _create_admin(app)
        resp = _login_admin(client)
        admin_data = resp.get_json()["admin"]

        assert "id" in admin_data
        assert admin_data["username"] == "testadmin"
        assert admin_data["is_active"] is True

    # ── Test 10: password_hash never exposed ──────────────────────────────────
    def test_password_hash_not_in_login_response(self, client, app):
        """password_hash must NEVER appear in the login response."""
        _create_admin(app)
        resp = _login_admin(client)
        body_text = resp.get_data(as_text=True)

        assert "password_hash" not in body_text
        assert "password" not in resp.get_json().get("admin", {})

    def test_login_missing_username(self, client, app):
        """Missing username field should return 400."""
        resp = client.post(f"{BASE}/login", json={"password": "Secr3t!"})
        assert resp.status_code == 400

    def test_login_missing_password(self, client, app):
        """Missing password field should return 400."""
        resp = client.post(f"{BASE}/login", json={"username": "testadmin"})
        assert resp.status_code == 400

    def test_login_non_json_body(self, client, app):
        """Non-JSON body should return 400."""
        resp = client.post(f"{BASE}/login", data="not json",
                           content_type="text/plain")
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 2 & 3. Incorrect password / unknown username
# ══════════════════════════════════════════════════════════════════════════════

class TestAdminLoginFailures:

    def test_wrong_password_returns_401(self, client, app):
        """Wrong password must return 401 with a generic error."""
        _create_admin(app)
        resp = _login_admin(client, password="WrongPassword!")
        data = resp.get_json()

        assert resp.status_code == 401
        assert data["status"] == "error"

    def test_unknown_username_returns_401(self, client, app):
        """Unknown username must return 401 — same as wrong password."""
        resp = _login_admin(client, username="nobody", password="any")
        data = resp.get_json()

        assert resp.status_code == 401
        assert data["status"] == "error"

    def test_error_message_is_generic(self, client, app):
        """Error message must not reveal whether username exists."""
        _create_admin(app)
        wrong_pw_msg = _login_admin(client, password="bad").get_json()["message"]
        unknown_user_msg = _login_admin(client, username="nobody",
                                        password="bad").get_json()["message"]
        assert wrong_pw_msg == unknown_user_msg


# ══════════════════════════════════════════════════════════════════════════════
# 4. Disabled admin account
# ══════════════════════════════════════════════════════════════════════════════

class TestDisabledAdmin:

    def test_disabled_admin_cannot_login(self, client, app):
        """Disabled admin account must return 403 Forbidden."""
        _create_admin(app, active=False)
        resp = _login_admin(client)
        assert resp.status_code == 403

    def test_disabled_admin_me_rejected(self, client, app):
        """Even with a valid token, a disabled admin is rejected at /me."""
        # Create active, log in, then disable the account in DB.
        _create_admin(app)
        access_token = _login_admin(client).get_json()["access_token"]

        with app.app_context():
            from app.extensions import db
            admin = Admin.query.filter_by(username="testadmin").first()
            admin.is_active = False
            db.session.commit()

        resp = client.get(f"{BASE}/me",
                          headers={"Authorization": f"Bearer {access_token}"})
        assert resp.status_code == 403


# ══════════════════════════════════════════════════════════════════════════════
# 5 & 6. No token / invalid token on admin endpoints
# ══════════════════════════════════════════════════════════════════════════════

class TestAdminEndpointProtection:

    def test_me_without_token_returns_401(self, client, app):
        """GET /admin/me without a token must return 401."""
        resp = client.get(f"{BASE}/me")
        assert resp.status_code == 401

    def test_me_with_garbage_token_returns_401(self, client, app):
        """GET /admin/me with a malformed token must return 401."""
        resp = client.get(f"{BASE}/me",
                          headers={"Authorization": "Bearer not.a.jwt"})
        assert resp.status_code == 401

    # ── Test 7: normal user JWT must be rejected ──────────────────────────────
    def test_me_with_user_jwt_returns_403(self, client, app):
        """A regular customer's JWT must NOT grant access to admin /me."""
        user_token = _get_user_token(client)
        resp = client.get(f"{BASE}/me",
                          headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 403

    # ── Test 8: valid admin JWT is accepted ───────────────────────────────────
    def test_me_with_admin_jwt_returns_200(self, client, app):
        """A valid admin JWT must be accepted by admin /me."""
        admin_token = _get_admin_token(client, app)
        resp = client.get(f"{BASE}/me",
                          headers={"Authorization": f"Bearer {admin_token}"})
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["admin"]["username"] == "testadmin"

    def test_me_does_not_expose_password_hash(self, client, app):
        """GET /admin/me must never return password_hash."""
        admin_token = _get_admin_token(client, app)
        resp = client.get(f"{BASE}/me",
                          headers={"Authorization": f"Bearer {admin_token}"})
        body = resp.get_data(as_text=True)

        assert "password_hash" not in body
        assert "password" not in resp.get_json().get("admin", {})


# ══════════════════════════════════════════════════════════════════════════════
# 9. Password stored as hash, not plaintext
# ══════════════════════════════════════════════════════════════════════════════

class TestPasswordStorage:

    def test_password_is_hashed_in_db(self, app):
        """The DB must never store the plaintext password."""
        _create_admin(app, password="MyP@ssw0rd")
        with app.app_context():
            admin = Admin.query.filter_by(username="testadmin").first()
            assert admin.password_hash != "MyP@ssw0rd"
            assert len(admin.password_hash) > 20   # it's a hash string

    def test_check_password_validates_correctly(self, app):
        """check_password() must return True for correct, False for wrong."""
        _create_admin(app, password="CorrectHorse!")
        with app.app_context():
            admin = Admin.query.filter_by(username="testadmin").first()
            assert admin.check_password("CorrectHorse!") is True
            assert admin.check_password("WrongPassword") is False

    def test_set_password_changes_hash(self, app):
        """set_password() must produce a new hash each time."""
        _create_admin(app, password="OldPassword!")
        with app.app_context():
            from app.extensions import db
            admin = Admin.query.filter_by(username="testadmin").first()
            old_hash = admin.password_hash
            admin.set_password("NewPassword!")
            db.session.commit()
            assert admin.password_hash != old_hash


# ══════════════════════════════════════════════════════════════════════════════
# 11. init_admin_from_env cannot create duplicates
# ══════════════════════════════════════════════════════════════════════════════

class TestInitAdmin:

    def test_init_creates_admin_if_not_exists(self, app):
        """init_admin_from_env() must create the admin on first call."""
        with app.app_context():
            with patch.dict("os.environ",
                            {"ADMIN_USERNAME": "newadmin", "ADMIN_PASSWORD": "Pass!"}):
                created, msg = AdminService.init_admin_from_env()
            assert created is True
            admin = Admin.query.filter_by(username="newadmin").first()
            assert admin is not None

    def test_init_is_idempotent(self, app):
        """Calling init_admin_from_env() twice must not create a duplicate."""
        with app.app_context():
            with patch.dict("os.environ",
                            {"ADMIN_USERNAME": "dup_admin", "ADMIN_PASSWORD": "Pass!"}):
                AdminService.init_admin_from_env()
                created, msg = AdminService.init_admin_from_env()
            assert created is False
            count = Admin.query.filter_by(username="dup_admin").count()
            assert count == 1

    def test_init_fails_without_env_vars(self, app):
        """Missing env vars must return (False, error message)."""
        with app.app_context():
            with patch.dict("os.environ",
                            {"ADMIN_USERNAME": "", "ADMIN_PASSWORD": ""}):
                created, msg = AdminService.init_admin_from_env()
            assert created is False


# ══════════════════════════════════════════════════════════════════════════════
# Admin Logout
# ══════════════════════════════════════════════════════════════════════════════

class TestAdminLogout:

    def test_logout_returns_200(self, client, app):
        """POST /admin/logout with a valid token must return 200."""
        token = _get_admin_token(client, app)
        resp = client.post(f"{BASE}/logout",
                           headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

    def test_token_rejected_after_logout(self, client, app):
        """After logout, the same token must be rejected on /admin/me."""
        token = _get_admin_token(client, app)

        # Confirm /me works before logout.
        assert client.get(f"{BASE}/me",
                          headers={"Authorization": f"Bearer {token}"}
                          ).status_code == 200

        # Log out.
        client.post(f"{BASE}/logout",
                    headers={"Authorization": f"Bearer {token}"})

        # /me must now return 401.
        assert client.get(f"{BASE}/me",
                          headers={"Authorization": f"Bearer {token}"}
                          ).status_code == 401

    def test_logout_without_token_returns_401(self, client, app):
        """POST /admin/logout without any token must return 401."""
        resp = client.post(f"{BASE}/logout")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 12. Existing user auth still works
# ══════════════════════════════════════════════════════════════════════════════

class TestExistingAuthUnaffected:

    def test_user_otp_login_still_works(self, client, app):
        """Regular OTP login must still work after admin system is added."""
        r1 = client.post(f"{AUTH_BASE}/request-otp", json={
            "identifier": "existing@example.com",
            "identifier_type": "email",
        })
        assert r1.status_code == 200

        otp = r1.get_json()["otp"]
        r2 = client.post(f"{AUTH_BASE}/verify-otp", json={
            "identifier": "existing@example.com",
            "identifier_type": "email",
            "otp": otp,
        })
        assert r2.status_code == 200
        assert "access_token" in r2.get_json()

    def test_user_me_endpoint_still_works(self, client, app):
        """GET /auth/me with a valid user token must still return 200."""
        user_token = _get_user_token(client)
        resp = client.get(f"{AUTH_BASE}/me",
                          headers={"Authorization": f"Bearer {user_token}"})
        assert resp.status_code == 200
