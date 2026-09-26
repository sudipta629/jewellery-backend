"""
app/models/metal_rate.py

SQLAlchemy model for the `metal_rates` table.

Stores the live gold/silver/platinum rate per gram.
A new row is inserted each time an admin updates the rate —
old rows are kept for historical queries.

The currently active rate for a given metal+purity combination
is the row with is_active=True and the most recent effective_date.

Examples
--------
    Gold 24K  — 6200 INR/gram
    Gold 22K  — 5700 INR/gram
    Gold 18K  — 4600 INR/gram
    Silver    — 78 INR/gram

Relationships
-------------
MetalRate is a standalone audit table — no FK to products.
The PricingService queries the latest active rate when calculating
a product's current price.
"""

from app.extensions import db
from app.models.base import TimestampMixin


class MetalRate(TimestampMixin, db.Model):
    """
    Represents a metal-rate snapshot for a specific metal type and purity.

    Table: metal_rates
    """

    __tablename__ = "metal_rates"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Metal identity ────────────────────────────────────────────────────────
    # Examples: "gold", "silver", "platinum", "diamond"
    metal_type = db.Column(
        db.String(50),
        nullable=False,
        index=True,
    )

    # Purity/grade — e.g. "24K", "22K", "18K", "925", "950", "999"
    # For metals without purity grades (e.g. plain silver), set to None.
    purity = db.Column(
        db.String(20),
        nullable=True,
        index=True,
    )

    # ── Rate ──────────────────────────────────────────────────────────────────
    # Numeric(12, 2) handles up to 10-digit amounts with 2 decimal places.
    # Example: 62000.00 (INR per 10g → stored as 6200.00 per gram)
    rate_per_gram = db.Column(
        db.Numeric(12, 2),
        nullable=False,
    )

    # The date from which this rate became effective.
    # For real-time pricing, this would be set to the current date.
    effective_date = db.Column(
        db.Date,
        nullable=False,
        index=True,
    )

    # Source of the rate: "manual", "api", "mcx", etc.
    source = db.Column(
        db.String(100),
        nullable=True,
        default="manual",
    )

    # Only one row per metal+purity should have is_active=True.
    # Enforced at the service layer when a new rate is set.
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    def __repr__(self) -> str:
        return (
            f"<MetalRate id={self.id} {self.metal_type}/{self.purity} "
            f"rate={self.rate_per_gram} active={self.is_active}>"
        )
