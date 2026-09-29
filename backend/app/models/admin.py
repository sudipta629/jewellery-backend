"""
app/models/admin.py

SQLAlchemy model for the `admins` table.

This model represents a back-office admin account with
password-based authentication.  Admin accounts are never
self-registered — they are created exclusively by the
`flask init-admin` CLI command using credentials supplied
via environment variables.

Security notes
--------------
* Passwords are NEVER stored as plain text.
* Werkzeug's `generate_password_hash` (scrypt / pbkdf2) is used
  for hashing.  `check_password_hash` performs constant-time
  verification.
* The `password_hash` field is NEVER returned in API responses.
"""

from app.extensions import db
from app.models.base import TimestampMixin
from werkzeug.security import check_password_hash, generate_password_hash


class Admin(TimestampMixin, db.Model):
    """
    Represents a back-office admin account.

    Table: admins
    """

    __tablename__ = "admins"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ── Credentials ───────────────────────────────────────────────────────────
    username = db.Column(
        db.String(80),
        nullable=False,
        unique=True,
        index=True,
    )

    password_hash = db.Column(
        db.String(256),
        nullable=False,
    )

    # ── Status ────────────────────────────────────────────────────────────────
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
    )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def set_password(self, plain_password: str) -> None:
        """Hash *plain_password* and store the result.  Never stores plaintext."""
        self.password_hash = generate_password_hash(plain_password)

    def check_password(self, plain_password: str) -> bool:
        """Return True if *plain_password* matches the stored hash."""
        return check_password_hash(self.password_hash, plain_password)

    def to_safe_dict(self) -> dict:
        """Return public-safe fields only.  Never includes password_hash."""
        return {
            "id": self.id,
            "username": self.username,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        return f"<Admin id={self.id} username={self.username!r} active={self.is_active}>"
