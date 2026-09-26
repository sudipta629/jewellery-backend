"""
app/models/user.py

SQLAlchemy model for the `users` table.

This model represents a registered customer (or staff member) of the
Jewellery store.  Authentication is intentionally NOT handled here —
the system uses passwordless OTP login (implemented in a later step),
so there is no password field.

Relationships
-------------
User  →  Address  (one-to-many)
    A user can have multiple saved delivery addresses.
    When a user is deleted, all their addresses are deleted too
    (cascade="all, delete-orphan").
"""

from app.extensions import db
from app.models.base import TimestampMixin


class User(TimestampMixin, db.Model):
    """
    Represents a user account in the system.

    Table: users
    """

    __tablename__ = "users"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,        # unique row identifier
        autoincrement=True,      # PostgreSQL will assign 1, 2, 3, ...
    )

    # ── Identity fields ───────────────────────────────────────────────────────
    name = db.Column(
        db.String(120),
        nullable=False,          # every user must have a name
    )

    email = db.Column(
        db.String(254),          # RFC 5321 max email length
        nullable=True,           # nullable because some users may sign up via phone
        unique=True,             # no two users share the same email
        index=True,              # speeds up  WHERE email = '...'  queries
    )

    phone = db.Column(
        db.String(20),
        nullable=True,           # nullable because some users may sign up via email
        unique=True,             # no two users share the same phone number
        index=True,              # speeds up  WHERE phone = '...'  queries
    )

    # ── Role & status ─────────────────────────────────────────────────────────
    role = db.Column(
        db.String(20),
        nullable=False,
        default="customer",      # options: "customer", "staff", "admin"
    )

    is_verified = db.Column(
        db.Boolean,
        nullable=False,
        default=False,           # flipped to True after OTP verification
    )

    # NOTE: No password field — this system uses OTP-based passwordless login.
    # Storing hashed passwords would be added here only if password auth is needed.

    # ── Relationship: one User → many Addresses ───────────────────────────────
    addresses = db.relationship(
        "Address",
        back_populates="user",
        # cascade="all, delete-orphan" means:
        #   - "all"          → save/update/delete Address objects with their User
        #   - "delete-orphan"→ if an Address is removed from user.addresses list,
        #                      it is also deleted from the database
        # Result: deleting a User automatically deletes all their Addresses.
        cascade="all, delete-orphan",
        # lazy="select" is the default: addresses are loaded when accessed
        # (not eagerly loaded with every User query — better for performance)
        lazy="select",
    )

    def __repr__(self) -> str:
        """Readable string for debugging — e.g. print(user)."""
        return f"<User id={self.id} name={self.name!r} role={self.role!r}>"
