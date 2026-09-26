"""
app/services/auth_service.py

Business logic for passwordless OTP authentication.

Architecture
------------
Two service classes keep concerns separated:

    OTPService
        Handles everything related to OTP lifecycle:
        generation, hashing, storage, expiry, and verification.

    AuthService
        Handles user lookup/creation and JWT token building.

Route handlers import these services and call them — no database
queries or cryptographic operations should live inside route functions.

Security notes
--------------
* OTP generation uses secrets.randbelow() — cryptographically secure PRNG.
* OTP storage uses SHA-256 (hashlib) — the plaintext is discarded immediately.
* OTP comparison uses hmac.compare_digest() — constant-time to prevent
  timing-based side-channel attacks.
* SHA-256 is appropriate for short-lived, single-use, high-entropy OTPs
  that are already protected by expiry + attempt limits.  bcrypt is overkill
  and unnecessarily slow for values that are discarded after one successful use.
* Previous unverified OTP records for the same identifier are invalidated
  (attempts set to max) before a new one is created — this prevents replay
  of old OTPs if the user requests a new one.

Future work
-----------
* Rate limiting (requests-per-identifier per time window) — security hardening step.
* Token blacklisting for logout — security hardening step.
* SMS / email delivery integration — delivery step.
"""

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

from flask import current_app

from app.extensions import db
from app.models.otp_verification import OTPVerification
from app.models.token_blacklist import TokenBlacklist
from app.models.user import User

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# OTPService
# ══════════════════════════════════════════════════════════════════════════════

class OTPService:
    """
    Manages the full OTP lifecycle: generate → hash → store → verify.

    All methods are static — no instance state is needed.
    """

    @staticmethod
    def generate_otp() -> str:
        """
        Generate a cryptographically secure 6-digit OTP.

        Uses secrets.randbelow() instead of random.randint() to ensure
        the value is drawn from the OS's secure random source.

        Returns:
            A zero-padded 6-character string, e.g. "042819".
        """
        # randbelow(1_000_000) gives an integer in [0, 999999].
        # zfill(6) pads with leading zeros so "42" becomes "000042".
        return str(secrets.randbelow(1_000_000)).zfill(6)

    @staticmethod
    def hash_otp(otp: str) -> str:
        """
        Compute the SHA-256 hex-digest of the OTP string.

        The digest (64 hex characters) is stored in the database.
        The plaintext OTP is never persisted.

        Args:
            otp: The 6-digit OTP string.

        Returns:
            A 64-character lowercase hex string.
        """
        return hashlib.sha256(otp.encode("utf-8")).hexdigest()

    @staticmethod
    def verify_otp_hash(submitted_otp: str, stored_hash: str) -> bool:
        """
        Compare a submitted OTP with the stored hash in constant time.

        hmac.compare_digest() prevents timing attacks by ensuring the
        comparison always takes the same amount of time regardless of
        how many characters match.

        Args:
            submitted_otp: The OTP string the user submitted.
            stored_hash:   The SHA-256 hex-digest stored in the database.

        Returns:
            True if the submitted OTP hashes to the stored digest.
        """
        submitted_hash = OTPService.hash_otp(submitted_otp)
        return hmac.compare_digest(submitted_hash, stored_hash)

    @staticmethod
    def create_otp_record(
        identifier: str,
        identifier_type: str,
        user_id: int | None = None,
    ) -> OTPVerification:
        """
        Invalidate any existing pending OTPs and create a fresh one.

        Invalidation works by exhausting the attempts counter of all
        prior unverified records for the same identifier.  This means:
        - Old OTPs can no longer be submitted successfully.
        - The database retains the full history for auditing.

        Args:
            identifier:      Email address or phone number.
            identifier_type: "email" or "phone".
            user_id:         Optional user FK — may be None for first-time logins.

        Returns:
            The newly created and saved OTPVerification instance.
        """
        max_attempts: int = current_app.config.get("OTP_MAX_ATTEMPTS", 5)
        expiry_minutes: int = current_app.config.get("OTP_EXPIRY_MINUTES", 5)

        # ── Invalidate prior pending OTPs for this identifier ─────────────────
        existing = OTPVerification.query.filter_by(
            identifier=identifier,
            identifier_type=identifier_type,
            is_verified=False,
        ).all()

        for record in existing:
            if not record.is_locked:
                record.attempts = record.max_attempts  # lock it immediately
        if existing:
            db.session.flush()  # persist invalidation before creating new record

        # ── Generate new OTP ──────────────────────────────────────────────────
        otp = OTPService.generate_otp()
        otp_hash = OTPService.hash_otp(otp)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=expiry_minutes)

        record = OTPVerification(
            user_id=user_id,
            identifier=identifier,
            identifier_type=identifier_type,
            otp_hash=otp_hash,
            expires_at=expires_at,
            attempts=0,
            max_attempts=max_attempts,
            is_verified=False,
        )
        db.session.add(record)
        db.session.commit()

        # ── Log (without the OTP itself in production) ────────────────────────
        flask_env = os.environ.get("FLASK_ENV", "development")
        if flask_env == "development":
            # Safe to log OTP in development for debugging convenience.
            logger.debug(
                "[OTPService] OTP created for %s (%s): %s",
                identifier,
                identifier_type,
                otp,
            )
        else:
            logger.info(
                "[OTPService] OTP created for %s (%s) — expires %s",
                identifier,
                identifier_type,
                expires_at.isoformat(),
            )

        # Attach the plaintext OTP to the record temporarily so the route
        # can include it in the development-only response.  This attribute
        # is NOT a database column — it lives only in memory.
        record._plaintext_otp = otp  # type: ignore[attr-defined]
        return record

    @staticmethod
    def find_valid_otp(
        identifier: str,
        identifier_type: str,
    ) -> OTPVerification | None:
        """
        Find the most recent usable OTP record for the given identifier.

        A usable record is one that:
        - matches the identifier + identifier_type
        - has not been verified yet
        - has not exceeded the attempt limit
        - has not expired

        Args:
            identifier:      Email address or phone number.
            identifier_type: "email" or "phone".

        Returns:
            The matching OTPVerification, or None if no valid record exists.
        """
        record = (
            OTPVerification.query
            .filter_by(
                identifier=identifier,
                identifier_type=identifier_type,
                is_verified=False,
            )
            .order_by(OTPVerification.created_at.desc())
            .first()
        )

        if record is None:
            return None

        # Check expiry and lock status here so the route receives a clean None
        # rather than having to re-check the same conditions.
        if not record.is_usable:
            return None

        return record

    @staticmethod
    def verify_and_consume(
        otp_record: OTPVerification,
        submitted_otp: str,
    ) -> tuple[bool, str]:
        """
        Verify the submitted OTP against the stored hash.

        On failure: increment the attempts counter and persist.
        On success: mark the record as verified and persist.

        Args:
            otp_record:    The OTPVerification row to check against.
            submitted_otp: The raw OTP string submitted by the user.

        Returns:
            A (success: bool, message: str) tuple.
        """
        if OTPService.verify_otp_hash(submitted_otp, otp_record.otp_hash):
            otp_record.is_verified = True
            db.session.commit()
            return True, "OTP verified successfully."

        # Incorrect OTP — increment attempt counter.
        otp_record.attempts += 1
        db.session.commit()

        remaining = otp_record.max_attempts - otp_record.attempts
        if remaining <= 0:
            return False, "Maximum verification attempts reached. Please request a new OTP."

        return False, f"Invalid OTP. {remaining} attempt(s) remaining."


# ══════════════════════════════════════════════════════════════════════════════
# AuthService
# ══════════════════════════════════════════════════════════════════════════════

class AuthService:
    """
    Handles user lookup/creation and JWT token construction.
    """

    @staticmethod
    def get_or_create_user(
        identifier: str,
        identifier_type: str,
    ) -> tuple[User, bool]:
        """
        Find an existing user by email or phone, or create a new customer.

        First-time login flow:
        - No user found with the given email/phone.
        - A new User is created with role="customer", is_verified=True.
        - name is set to a placeholder ("New Customer") — the user can
          update their profile in a later step.

        Args:
            identifier:      Email address or phone number.
            identifier_type: "email" or "phone".

        Returns:
            A (User, was_created: bool) tuple.
            was_created is True when a new account was just created.
        """
        if identifier_type == "email":
            user = User.query.filter_by(email=identifier).first()
        else:
            user = User.query.filter_by(phone=identifier).first()

        if user is not None:
            # Existing user — mark as verified (in case they weren't before).
            if not user.is_verified:
                user.is_verified = True
                db.session.commit()
            return user, False

        # ── Create new customer ───────────────────────────────────────────────
        kwargs: dict = {
            "name": "New Customer",
            "role": "customer",
            "is_verified": True,
        }
        if identifier_type == "email":
            kwargs["email"] = identifier
        else:
            kwargs["phone"] = identifier

        new_user = User(**kwargs)
        db.session.add(new_user)
        db.session.commit()

        logger.info(
            "[AuthService] New customer created: id=%s (%s=%s)",
            new_user.id,
            identifier_type,
            identifier,
        )
        return new_user, True

    @staticmethod
    def build_token_response(user: User) -> dict:
        """
        Create JWT access + refresh tokens and build the safe user payload.

        Identity: user.id (integer)
        Additional claims: role (string) — added to the token payload.

        Args:
            user: The authenticated User model instance.

        Returns:
            A dict suitable for returning directly as a JSON response body.
            Does NOT include sensitive fields (otp_hash, password, etc.).
        """
        from flask_jwt_extended import create_access_token, create_refresh_token

        additional_claims = {"role": user.role}

        access_token = create_access_token(
            identity=str(user.id),
            additional_claims=additional_claims,
        )
        refresh_token = create_refresh_token(
            identity=str(user.id),
            additional_claims=additional_claims,
        )

        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "user": {
                "id": user.id,
                "name": user.name,
                "email": user.email,
                "phone": user.phone,
                "role": user.role,
                "is_verified": user.is_verified,
            },
        }


# ════════════════════════════════════════════════════════════════════════════════
# TokenBlacklistService
# ════════════════════════════════════════════════════════════════════════════════

class TokenBlacklistService:
    """
    Manages JWT token revocation using a database-backed blacklist.

    Flow
    ----
    1. User calls POST /api/v1/auth/logout.
    2. The route extracts the token's `jti` and `exp` claims.
    3. revoke_token() stores the jti in the `token_blacklist` table.
    4. On every subsequent protected request, Flask-JWT-Extended calls
       the `token_in_blocklist_loader` registered in app/__init__.py,
       which calls is_token_revoked().  A match returns 401.

    All methods are static — no instance state is needed.
    """

    @staticmethod
    def revoke_token(
        jti: str,
        token_type: str,
        expires_at: datetime,
        user_id: int | None = None,
    ) -> TokenBlacklist:
        """
        Insert a token's jti into the blacklist.

        Args:
            jti:        The JWT ID claim (unique per token).
            token_type: "access" or "refresh".
            expires_at: The token's natural expiry (from the `exp` claim).
            user_id:    The user who is logging out (optional).

        Returns:
            The newly created TokenBlacklist row.
        """
        record = TokenBlacklist(
            jti=jti,
            token_type=token_type,
            expires_at=expires_at,
            user_id=user_id,
        )
        db.session.add(record)
        db.session.commit()
        logger.info(
            "[TokenBlacklistService] Revoked %s token jti=%s for user_id=%s",
            token_type,
            jti,
            user_id,
        )
        return record

    @staticmethod
    def is_token_revoked(jti: str) -> bool:
        """
        Return True if the given jti exists in the blacklist.

        Called by the Flask-JWT-Extended `token_in_blocklist_loader`
        on every request to a protected endpoint.

        Args:
            jti: The JWT ID claim to look up.

        Returns:
            True if the token has been revoked, False otherwise.
        """
        return db.session.query(
            TokenBlacklist.query.filter_by(jti=jti).exists()
        ).scalar()

    @staticmethod
    def cleanup_expired_tokens() -> int:
        """
        Delete blacklist rows whose tokens have already naturally expired.

        After a token's `expires_at` timestamp passes, Flask-JWT-Extended
        would reject it anyway, so keeping the row only wastes space.

        Returns:
            The number of rows deleted.
        """
        now = datetime.now(timezone.utc)
        deleted = (
            TokenBlacklist.query
            .filter(TokenBlacklist.expires_at < now)
            .delete(synchronize_session=False)
        )
        db.session.commit()
        logger.info(
            "[TokenBlacklistService] Cleaned up %d expired blacklist entries.",
            deleted,
        )
        return deleted
