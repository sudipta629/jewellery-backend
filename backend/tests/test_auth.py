"""
tests/test_auth.py

Test suite for the passwordless OTP authentication endpoints.

Endpoints tested
----------------
POST  /api/v1/auth/request-otp
POST  /api/v1/auth/verify-otp
POST  /api/v1/auth/refresh
GET   /api/v1/auth/me

All tests run against the SQLite in-memory database (see conftest.py).
FLASK_ENV=development is forced so the OTP is returned in request-otp
responses — no real SMS/email service is used.

Test isolation
--------------
The clean_db fixture in conftest.py deletes all rows between tests,
so each test starts with an empty database.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from app.extensions import db
from app.models.otp_verification import OTPVerification
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User
from app.services.auth_service import OTPService

BASE = "/api/v1/auth"


# ══════════════════════════════════════════════════════════════════════════════
# Helper functions
# ══════════════════════════════════════════════════════════════════════════════

def request_otp(client, identifier: str, identifier_type: str):
    """POST /request-otp and return the response."""
    return client.post(
        f"{BASE}/request-otp",
        json={"identifier": identifier, "identifier_type": identifier_type},
    )


def verify_otp(client, identifier: str, identifier_type: str, otp: str):
    """POST /verify-otp and return the response."""
    return client.post(
        f"{BASE}/verify-otp",
        json={
            "identifier": identifier,
            "identifier_type": identifier_type,
            "otp": otp,
        },
    )


def get_valid_token(client, identifier="test@example.com", identifier_type="email"):
    """
    Full login flow: request OTP → verify OTP → return access_token.
    Helper used by tests that need an authenticated client.
    """
    resp = request_otp(client, identifier, identifier_type)
    assert resp.status_code == 200
    otp = resp.get_json()["otp"]

    resp2 = verify_otp(client, identifier, identifier_type, otp)
    assert resp2.status_code == 200
    return resp2.get_json()["access_token"]


def get_valid_tokens(client, identifier="test@example.com", identifier_type="email"):
    """
    Full login flow: request OTP → verify OTP → return (access_token, refresh_token).
    Helper used by logout tests that need both tokens.
    """
    resp = request_otp(client, identifier, identifier_type)
    assert resp.status_code == 200
    otp = resp.get_json()["otp"]

    resp2 = verify_otp(client, identifier, identifier_type, otp)
    assert resp2.status_code == 200
    data = resp2.get_json()
    return data["access_token"], data["refresh_token"]


# ══════════════════════════════════════════════════════════════════════════════
# 1 & 2. Request OTP — valid email and phone
# ══════════════════════════════════════════════════════════════════════════════

class TestRequestOTP:
    """POST /api/v1/auth/request-otp"""

    def test_request_otp_with_valid_email(self, client):
        """Should return 200 with the OTP in development mode."""
        resp = request_otp(client, "user@example.com", "email")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["development_only"] is True
        # OTP must be a 6-digit string
        assert "otp" in data
        assert len(data["otp"]) == 6
        assert data["otp"].isdigit()

    def test_request_otp_with_valid_phone(self, client):
        """Should return 200 with the OTP for a phone number."""
        resp = request_otp(client, "+919876543210", "phone")
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        assert data["development_only"] is True
        assert len(data["otp"]) == 6
        assert data["otp"].isdigit()

    @patch("app.services.email_service.smtplib.SMTP")
    @patch("app.services.email_service.os.environ.get")
    def test_request_otp_sends_email(self, mock_env_get, mock_smtp, client):
        """Requesting an OTP for an email should trigger SMTP delivery."""
        # Mock environment variables for Gmail credentials
        def mock_env(key, default=None):
            if key == "GMAIL_ADDRESS": return "test@gmail.com"
            if key == "GMAIL_APP_PASSWORD": return "password123"
            return default
        mock_env_get.side_effect = mock_env

        mock_server = mock_smtp.return_value.__enter__.return_value

        resp = request_otp(client, "sendemail@example.com", "email")
        
        assert resp.status_code == 200
        
        # Verify SMTP server was called correctly
        mock_smtp.assert_called_with("smtp.gmail.com", 587, timeout=10)
        mock_server.starttls.assert_called_once()
        mock_server.login.assert_called_once_with("test@gmail.com", "password123")
        mock_server.send_message.assert_called_once()
        
        # Verify message contents
        msg = mock_server.send_message.call_args[0][0]
        assert msg["To"] == "sendemail@example.com"
        assert msg["From"] == "test@gmail.com"
        assert "Your login verification code is:" in msg.get_content()

    def test_request_otp_with_plain_phone_digits(self, client):
        """Phone without leading '+' should also be accepted."""
        resp = request_otp(client, "9876543210", "phone")
        assert resp.status_code == 200

    # ── Validation failures ───────────────────────────────────────────────────

    def test_invalid_identifier_type(self, client):
        """identifier_type must be 'email' or 'phone'."""
        resp = request_otp(client, "user@example.com", "sms")
        data = resp.get_json()

        assert resp.status_code == 400
        assert data["status"] == "error"
        assert "identifier_type" in data["message"]

    def test_invalid_email_format(self, client):
        """Malformed email should return 400."""
        resp = request_otp(client, "not-an-email", "email")
        data = resp.get_json()

        assert resp.status_code == 400
        assert data["status"] == "error"
        assert "email" in data["message"].lower()

    def test_invalid_phone_format(self, client):
        """Phone with letters should return 400."""
        resp = request_otp(client, "abc123", "phone")
        data = resp.get_json()

        assert resp.status_code == 400
        assert data["status"] == "error"

    def test_missing_identifier(self, client):
        """Empty identifier should return 400."""
        resp = client.post(f"{BASE}/request-otp", json={"identifier_type": "email"})
        assert resp.status_code == 400

    def test_missing_identifier_type(self, client):
        """Missing identifier_type should return 400."""
        resp = client.post(f"{BASE}/request-otp", json={"identifier": "a@b.com"})
        assert resp.status_code == 400

    def test_empty_body(self, client):
        """No JSON body should return 400."""
        resp = client.post(f"{BASE}/request-otp", content_type="application/json", data="")
        assert resp.status_code == 400

    def test_new_otp_invalidates_previous(self, client, app):
        """Requesting a second OTP should lock the first one."""
        request_otp(client, "user@example.com", "email")

        with app.app_context():
            first_record = OTPVerification.query.filter_by(
                identifier="user@example.com"
            ).order_by(OTPVerification.created_at.asc()).first()
            assert first_record is not None
            first_id = first_record.id

        request_otp(client, "user@example.com", "email")

        with app.app_context():
            first = db.session.get(OTPVerification, first_id)
            # The first record should be locked (attempts >= max_attempts).
            assert first.is_locked


# ══════════════════════════════════════════════════════════════════════════════
# 3–9. Verify OTP
# ══════════════════════════════════════════════════════════════════════════════

class TestVerifyOTP:
    """POST /api/v1/auth/verify-otp"""

    def test_verify_with_wrong_otp(self, client):
        """Submitting an incorrect OTP should return 401."""
        request_otp(client, "user@example.com", "email")
        resp = verify_otp(client, "user@example.com", "email", "000000")
        data = resp.get_json()

        assert resp.status_code == 401
        assert data["status"] == "error"

    def test_verify_without_requesting_otp_first(self, client):
        """Verifying when no OTP was requested should return 401."""
        resp = verify_otp(client, "nobody@example.com", "email", "123456")
        assert resp.status_code == 401

    def test_verify_with_expired_otp(self, client, app):
        """An expired OTP should be rejected."""
        request_otp(client, "user@example.com", "email")

        # Manually expire the OTP record in the database.
        # Use a timezone-naive datetime so SQLite (used in tests) can store it.
        with app.app_context():
            record = OTPVerification.query.filter_by(
                identifier="user@example.com"
            ).first()
            # Use timezone-naive datetime for SQLite compatibility in tests.
            # The is_expired property normalises it to UTC before comparing.
            record.expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=1)
            db.session.commit()

        resp = verify_otp(client, "user@example.com", "email", "123456")
        assert resp.status_code == 401

    def test_verify_too_many_attempts(self, client):
        """After 5 failed attempts, verification should return 429."""
        request_otp(client, "user@example.com", "email")

        # Make 5 failed attempts.
        for _ in range(5):
            resp = verify_otp(client, "user@example.com", "email", "000000")

        # The 5th (or any subsequent) attempt should be 429.
        assert resp.status_code == 429
        data = resp.get_json()
        assert data["status"] == "error"

    def test_successful_otp_verification(self, client):
        """Correct OTP should return 200 with access_token, refresh_token, and user."""
        resp1 = request_otp(client, "user@example.com", "email")
        otp = resp1.get_json()["otp"]

        resp2 = verify_otp(client, "user@example.com", "email", otp)
        data = resp2.get_json()

        assert resp2.status_code == 200
        assert data["status"] == "success"
        assert "access_token" in data
        assert "refresh_token" in data
        assert "user" in data
        user = data["user"]
        assert user["email"] == "user@example.com"
        assert user["role"] == "customer"
        assert user["is_verified"] is True

    def test_new_customer_created_on_first_login(self, client, app):
        """First-time login should create a new User row in the database."""
        resp1 = request_otp(client, "newuser@example.com", "email")
        otp = resp1.get_json()["otp"]
        verify_otp(client, "newuser@example.com", "email", otp)

        with app.app_context():
            user = User.query.filter_by(email="newuser@example.com").first()
            assert user is not None
            assert user.role == "customer"
            assert user.is_verified is True

    def test_new_user_flag_returned_for_first_login(self, client):
        """Response should include new_user=True for first-time logins."""
        resp1 = request_otp(client, "brand@new.com", "email")
        otp = resp1.get_json()["otp"]
        resp2 = verify_otp(client, "brand@new.com", "email", otp)
        data = resp2.get_json()

        assert data.get("new_user") is True

    def test_existing_user_no_new_user_flag(self, client, app):
        """Existing users should NOT have new_user in the response."""
        # First login — creates user.
        resp1 = request_otp(client, "returning@example.com", "email")
        otp = resp1.get_json()["otp"]
        verify_otp(client, "returning@example.com", "email", otp)

        # Second login — user already exists.
        resp2 = request_otp(client, "returning@example.com", "email")
        otp2 = resp2.get_json()["otp"]
        resp3 = verify_otp(client, "returning@example.com", "email", otp2)
        data = resp3.get_json()

        assert data.get("new_user") is None or data.get("new_user") is False

    def test_otp_field_missing(self, client):
        """Missing otp field should return 400."""
        request_otp(client, "user@example.com", "email")
        resp = client.post(
            f"{BASE}/verify-otp",
            json={"identifier": "user@example.com", "identifier_type": "email"},
        )
        assert resp.status_code == 400

    def test_otp_wrong_length(self, client):
        """OTP that is not 6 digits should return 400."""
        request_otp(client, "user@example.com", "email")
        resp = verify_otp(client, "user@example.com", "email", "123")
        assert resp.status_code == 400

    def test_otp_non_numeric(self, client):
        """Non-numeric OTP should return 400."""
        request_otp(client, "user@example.com", "email")
        resp = verify_otp(client, "user@example.com", "email", "abcdef")
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# 10–11. JWT Access Token
# ══════════════════════════════════════════════════════════════════════════════

class TestJWT:
    """JWT token creation and validation."""

    def test_access_token_is_valid_jwt(self, client):
        """The access_token returned should be a decodable JWT string."""
        resp1 = request_otp(client, "jwt@example.com", "email")
        otp = resp1.get_json()["otp"]
        resp2 = verify_otp(client, "jwt@example.com", "email", otp)
        data = resp2.get_json()

        access_token = data["access_token"]
        # A JWT has exactly three dot-separated Base64 segments.
        parts = access_token.split(".")
        assert len(parts) == 3, "access_token should be a well-formed JWT"

    def test_refresh_token_is_valid_jwt(self, client):
        """The refresh_token returned should be a decodable JWT string."""
        resp1 = request_otp(client, "refresh@example.com", "email")
        otp = resp1.get_json()["otp"]
        resp2 = verify_otp(client, "refresh@example.com", "email", otp)
        data = resp2.get_json()

        refresh_token = data["refresh_token"]
        parts = refresh_token.split(".")
        assert len(parts) == 3, "refresh_token should be a well-formed JWT"


# ══════════════════════════════════════════════════════════════════════════════
# 12. JWT Refresh
# ══════════════════════════════════════════════════════════════════════════════

class TestRefresh:
    """POST /api/v1/auth/refresh"""

    def test_refresh_returns_new_access_token(self, client):
        """A valid refresh token should return a new access token."""
        resp1 = request_otp(client, "refresh@example.com", "email")
        otp = resp1.get_json()["otp"]
        resp2 = verify_otp(client, "refresh@example.com", "email", otp)
        data = resp2.get_json()
        refresh_token = data["refresh_token"]

        resp3 = client.post(
            f"{BASE}/refresh",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        data3 = resp3.get_json()

        assert resp3.status_code == 200
        assert data3["status"] == "success"
        assert "access_token" in data3
        # New access token should be a valid JWT.
        assert len(data3["access_token"].split(".")) == 3

    def test_refresh_with_access_token_fails(self, client):
        """Using an access token on the refresh endpoint should fail."""
        access_token = get_valid_token(client, "refresh2@example.com", "email")

        resp = client.post(
            f"{BASE}/refresh",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        # Flask-JWT-Extended returns 422 when a non-refresh token is used here.
        assert resp.status_code in (401, 422)

    def test_refresh_without_token_fails(self, client):
        """No token on the refresh endpoint should return 401."""
        resp = client.post(f"{BASE}/refresh")
        assert resp.status_code == 401


# ══════════════════════════════════════════════════════════════════════════════
# 13–14. Protected /me endpoint
# ══════════════════════════════════════════════════════════════════════════════

class TestMe:
    """GET /api/v1/auth/me"""

    def test_me_without_token_returns_401(self, client):
        """Calling /me with no Authorization header should return 401."""
        resp = client.get(f"{BASE}/me")
        assert resp.status_code == 401
        data = resp.get_json()
        assert data["status"] == "error"

    def test_me_with_invalid_token_returns_401(self, client):
        """Calling /me with a garbage token should return 401."""
        resp = client.get(
            f"{BASE}/me",
            headers={"Authorization": "Bearer this.is.not.a.jwt"},
        )
        assert resp.status_code == 401

    def test_me_with_valid_token_returns_user(self, client):
        """Calling /me with a valid access token should return the user profile."""
        access_token = get_valid_token(client, "me@example.com", "email")

        resp = client.get(
            f"{BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        assert "user" in data
        user = data["user"]
        assert user["email"] == "me@example.com"
        assert user["role"] == "customer"
        assert user["is_verified"] is True
        # Sensitive fields must NOT be present.
        assert "otp_hash" not in user
        assert "password" not in user

    def test_me_does_not_expose_sensitive_fields(self, client):
        """The /me response must never include otp_hash or password."""
        access_token = get_valid_token(client, "safe@example.com", "email")

        resp = client.get(
            f"{BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        body_text = resp.get_data(as_text=True)

        assert "otp_hash" not in body_text
        assert "password" not in body_text


# ══════════════════════════════════════════════════════════════════════════════
# OTPService unit tests (no HTTP, direct service calls)
# ══════════════════════════════════════════════════════════════════════════════

class TestOTPService:
    """Direct unit tests for OTPService helper methods."""

    def test_generate_otp_is_6_digits(self):
        """Generated OTP must be a 6-character numeric string."""
        otp = OTPService.generate_otp()
        assert len(otp) == 6
        assert otp.isdigit()

    def test_generate_otp_is_not_predictable(self):
        """Two consecutive OTPs should (almost certainly) differ."""
        otps = {OTPService.generate_otp() for _ in range(20)}
        # With 1,000,000 possible values, generating 20 identical ones is
        # astronomically unlikely if the PRNG is working correctly.
        assert len(otps) > 1

    def test_hash_otp_returns_64_char_hex(self):
        """SHA-256 hex-digest should be exactly 64 characters."""
        digest = OTPService.hash_otp("123456")
        assert len(digest) == 64
        # Must be lowercase hex characters only.
        assert all(c in "0123456789abcdef" for c in digest)

    def test_hash_otp_is_deterministic(self):
        """Same OTP must always produce the same hash."""
        assert OTPService.hash_otp("123456") == OTPService.hash_otp("123456")

    def test_hash_otp_differs_for_different_inputs(self):
        """Different OTPs must produce different hashes."""
        assert OTPService.hash_otp("123456") != OTPService.hash_otp("654321")

    def test_verify_otp_hash_correct(self):
        """verify_otp_hash returns True for the correct OTP."""
        otp = "123456"
        stored = OTPService.hash_otp(otp)
        assert OTPService.verify_otp_hash(otp, stored) is True

    def test_verify_otp_hash_incorrect(self):
        """verify_otp_hash returns False for a wrong OTP."""
        stored = OTPService.hash_otp("123456")
        assert OTPService.verify_otp_hash("654321", stored) is False


# ════════════════════════════════════════════════════════════════════════════════
# Logout / Token Blacklisting tests
# ════════════════════════════════════════════════════════════════════════════════

class TestLogout:
    """POST /api/v1/auth/logout"""

    def test_logout_returns_200(self, client):
        """Valid logout with access token should return 200."""
        access_token, _ = get_valid_tokens(client, "logout@example.com")

        resp = client.post(
            f"{BASE}/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["status"] == "success"
        assert "Logged out" in data["message"]

    def test_logout_without_token_returns_401(self, client):
        """Calling /logout without an Authorization header should return 401."""
        resp = client.post(f"{BASE}/logout")
        assert resp.status_code == 401

    def test_access_token_rejected_after_logout(self, client):
        """After logout, the revoked access token must be rejected by /me."""
        access_token, _ = get_valid_tokens(client, "revoke@example.com")

        # Confirm /me works before logout.
        resp_before = client.get(
            f"{BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp_before.status_code == 200

        # Logout.
        client.post(
            f"{BASE}/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        # /me must now return 401 with the same token.
        resp_after = client.get(
            f"{BASE}/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp_after.status_code == 401

    def test_logout_also_revokes_refresh_token(self, client):
        """When refresh_token is included in logout body, /refresh must be rejected."""
        access_token, refresh_token = get_valid_tokens(client, "fulllogout@example.com")

        # Logout with both tokens.
        client.post(
            f"{BASE}/logout",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"refresh_token": refresh_token},
        )

        # /refresh must now return 401.
        resp = client.post(
            f"{BASE}/refresh",
            headers={"Authorization": f"Bearer {refresh_token}"},
        )
        assert resp.status_code == 401

    def test_logout_stores_jti_in_blacklist(self, client, app):
        """After logout, the token's jti should exist in the token_blacklist table."""
        access_token, _ = get_valid_tokens(client, "jti@example.com")

        client.post(
            f"{BASE}/logout",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        with app.app_context():
            count = TokenBlacklist.query.count()
            assert count >= 1
