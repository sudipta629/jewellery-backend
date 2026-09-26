"""
app/models/address.py

SQLAlchemy model for the `addresses` table.

Each row represents a single delivery address saved by a user.
A user can have many addresses but only one marked as the default.

Relationships
-------------
Address  →  User  (many-to-one)
    Every address belongs to exactly one user via user_id (foreign key).
"""

from app.extensions import db
from app.models.base import TimestampMixin


class Address(TimestampMixin, db.Model):
    """
    Represents a saved delivery address belonging to a User.

    Table: addresses
    """

    __tablename__ = "addresses"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(
        db.Integer,
        primary_key=True,
        autoincrement=True,
    )

    # ── Foreign key — links each address to its owner ─────────────────────────
    # ForeignKey("users.id") tells PostgreSQL:
    #   "The value in this column MUST exist in the `id` column of `users`."
    # This prevents orphaned addresses (addresses with no owner).
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,          # every address must belong to a user
        index=True,              # speeds up  WHERE user_id = ?  queries
    )

    # ── Delivery contact ──────────────────────────────────────────────────────
    full_name = db.Column(
        db.String(120),
        nullable=False,          # name of the person receiving the delivery
    )

    phone = db.Column(
        db.String(20),
        nullable=False,          # contact number for the delivery
    )

    # ── Address details ───────────────────────────────────────────────────────
    address_line = db.Column(
        db.String(255),
        nullable=False,          # street / flat / building details
    )

    city = db.Column(
        db.String(100),
        nullable=False,
    )

    state = db.Column(
        db.String(100),
        nullable=False,
    )

    pincode = db.Column(
        db.String(10),
        nullable=False,          # e.g. "700001" (Indian postal code)
    )

    # ── Default flag ──────────────────────────────────────────────────────────
    is_default = db.Column(
        db.Boolean,
        nullable=False,
        default=False,           # True = this is the user's default shipping address
    )

    # ── Relationship: back-reference to the owning User ───────────────────────
    # back_populates="addresses" must match the name used in User.addresses
    user = db.relationship(
        "User",
        back_populates="addresses",
    )

    def __repr__(self) -> str:
        """Readable string for debugging."""
        return (
            f"<Address id={self.id} user_id={self.user_id} "
            f"city={self.city!r} default={self.is_default}>"
        )
        
    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "full_name": self.full_name,
            "phone": self.phone,
            "address_line": self.address_line,
            "city": self.city,
            "state": self.state,
            "pincode": self.pincode,
            "is_default": self.is_default
        }
