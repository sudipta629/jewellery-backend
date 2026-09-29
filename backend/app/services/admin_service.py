"""
app/services/admin_service.py

Business logic for admin authentication (password-based).

AdminService handles:
  - Validating admin login credentials.
  - Building JWT tokens specifically for admin identities.
  - Initialising (seeding) the first admin account from env vars.

Security notes
--------------
* Admin tokens carry `sub_type = "admin"` in their additional_claims.
  The `require_admin_token` decorator validates this claim to ensure
  that a normal user JWT is NEVER accepted on admin endpoints.
* Passwords are verified with Werkzeug's check_password_hash which
  runs a constant-time comparison.
* The plaintext password is NEVER logged.
"""

import logging
import os

from flask_jwt_extended import create_access_token, create_refresh_token

from app.extensions import db
from app.models.admin import Admin

logger = logging.getLogger(__name__)

# Claim embedded in every admin JWT so it can be distinguished from user JWTs.
ADMIN_SUB_TYPE = "admin"


class AdminService:
    """Static service for admin authentication and token management."""

    # ── Login ─────────────────────────────────────────────────────────────────

    @staticmethod
    def authenticate(username: str, password: str) -> Admin | None:
        """
        Verify username + password against the admins table.

        Returns the Admin row on success, None on any failure.
        Does NOT reveal whether the username exists (caller must return
        the same generic error for both "not found" and "wrong password").
        """
        admin = Admin.query.filter_by(username=username).first()
        if admin is None:
            # Perform a dummy comparison to prevent timing attacks that
            # could reveal whether the username exists.
            from werkzeug.security import check_password_hash
            check_password_hash(
                "pbkdf2:sha256:260000$dummy$" + "0" * 64,
                password,
            )
            return None

        if not admin.check_password(password):
            return None

        return admin

    # ── JWT token building ────────────────────────────────────────────────────

    @staticmethod
    def build_token_response(admin: Admin) -> dict:
        """
        Issue access + refresh tokens for an admin and return the safe payload.

        Additional JWT claims:
          role      — always "admin" (admin panel role)
          sub_type  — always "admin" (distinguishes from user tokens)

        The password_hash is NEVER included in the response.
        """
        additional_claims = {
            "role": "admin",
            "sub_type": ADMIN_SUB_TYPE,
        }

        access_token = create_access_token(
            identity=f"admin:{admin.id}",
            additional_claims=additional_claims,
        )
        refresh_token = create_refresh_token(
            identity=f"admin:{admin.id}",
            additional_claims=additional_claims,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "admin": admin.to_safe_dict(),
        }

    # ── Seed / initialise ─────────────────────────────────────────────────────

    @staticmethod
    def init_admin_from_env() -> tuple[bool, str]:
        """
        Create the first admin account from ADMIN_USERNAME / ADMIN_PASSWORD
        environment variables.

        Idempotent — if an admin with that username already exists, nothing
        is changed.

        Returns:
            (created: bool, message: str)
            created is True only when a new row was inserted.
        """
        username = os.environ.get("ADMIN_USERNAME", "").strip()
        password = os.environ.get("ADMIN_PASSWORD", "").strip()

        if not username or not password:
            return False, "ADMIN_USERNAME and ADMIN_PASSWORD must be set."

        existing = Admin.query.filter_by(username=username).first()
        if existing:
            logger.info("[AdminService] Admin '%s' already exists — skipped.", username)
            return False, f"Admin '{username}' already exists."

        admin = Admin(username=username)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()

        logger.info("[AdminService] Admin account '%s' created (id=%s).", username, admin.id)
        return True, f"Admin '{username}' created successfully (id={admin.id})."
