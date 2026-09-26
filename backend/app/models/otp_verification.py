"""
app/models/otp_verification.py

SQLAlchemy model for the `otp_verifications` table.

This model stores hashed, short-lived OTP tokens used for
passwordless authentication via email or phone.

Security design
---------------
* The actual OTP is NEVER stored — only its SHA-256 hex-digest.
* Expiry is enforced via the `expires_at` column (checked in the service).
* Attempt tracking prevents brute-force: after `max_attempts` failed
  tries the record is permanently locked and verification fails.
* A new OTP request for the same identifier invalidates prior records
  by exhausting their attempt counter, not by deleting them (preserves
  the audit trail).

Relationships
-------------
OTPVerification → User (many-to-one, nullable)
    user_id is nullable because an OTP may be generated BEFORE a user
    account exists (first-time login flow creates the user on verify).
"""

from datetime import datetime, timezone

from app.extensions import db
from app.models.base import TimestampMixin


class OTPVerification(TimestampMixin, db.Model):
    """
    Represents a single OTP generation event.

    Table: otp_verifications
    """

    __tablename__ = "otp_verifications"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ── Link to the user (nullable — set after user is found/created) ─────────
    # ForeignKey on users.id with SET NULL so that deleting a user does NOT
    # cascade-delete their OTP history (useful for auditing).
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Identifier fields ─────────────────────────────────────────────────────
    # The email address or phone number the OTP was sent to.
    identifier = db.Column(
        db.String(254),   # max email length per RFC 5321
        nullable=False,
        index=True,       # speeds up  WHERE identifier = ?  lookups
    )

    # Discriminator: "email" or "phone"
    identifier_type = db.Column(
        db.String(10),
        nullable=False,
    )

    # ── OTP storage (HASH ONLY — never plaintext) ─────────────────────────────
    # SHA-256 produces a 64-character hex string.
    otp_hash = db.Column(
        db.String(64),
        nullable=False,
    )

    # ── Expiry ────────────────────────────────────────────────────────────────
    expires_at = db.Column(
        db.DateTime(timezone=True),
        nullable=False,
    )

    # ── Attempt tracking ──────────────────────────────────────────────────────
    attempts = db.Column(
        db.Integer,
        nullable=False,
        default=0,         # incremented on each failed verification attempt
    )

    max_attempts = db.Column(
        db.Integer,
        nullable=False,
        default=5,         # configurable per record (read from OTP_MAX_ATTEMPTS)
    )

    # ── Status ────────────────────────────────────────────────────────────────
    is_verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False,     # flipped to True when the correct OTP is submitted
    )

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def is_expired(self) -> bool:
        """True if the OTP's expiry time has passed.

        Handles both timezone-aware datetimes (PostgreSQL) and
        timezone-naive datetimes (SQLite used in tests) by normalising
        both sides to UTC before comparing.
        """
        now = datetime.now(timezone.utc)
        expiry = self.expires_at
        # SQLite strips timezone info — make it timezone-aware (UTC) if needed.
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return now > expiry

    @property
    def is_locked(self) -> bool:
        """True if the maximum number of attempts has been reached."""
        return self.attempts >= self.max_attempts

    @property
    def is_usable(self) -> bool:
        """True if the OTP can still be submitted (not expired, not locked, not already used)."""
        return not self.is_expired and not self.is_locked and not self.is_verified

    def __repr__(self) -> str:
        return (
            f"<OTPVerification id={self.id} identifier={self.identifier!r} "
            f"type={self.identifier_type!r} verified={self.is_verified} "
            f"attempts={self.attempts}/{self.max_attempts}>"
        )
