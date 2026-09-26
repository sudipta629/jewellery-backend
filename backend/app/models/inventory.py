"""
app/models/inventory.py

SQLAlchemy model for the `inventory_transactions` table.

Inventory state is derived by summing all transactions for a product
(STOCK_IN - STOCK_OUT - SALE + RETURN + ADJUSTMENT).

The current quantity is also cached on Product.stock_quantity for
fast reads — but this table is the authoritative audit trail.

Transaction Types
-----------------
    STOCK_IN    — goods received from supplier
    STOCK_OUT   — goods removed (damaged, expired, etc.)
    SALE        — sold via an order (linked via order_id)
    RETURN      — customer return (linked via order_id)
    ADJUSTMENT  — admin manual adjustment (count correction)

Relationships
-------------
    InventoryTransaction → Product  (many-to-one)
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class TransactionType(str, enum.Enum):
    """Allowed values for InventoryTransaction.transaction_type."""
    STOCK_IN   = "STOCK_IN"
    STOCK_OUT  = "STOCK_OUT"
    SALE       = "SALE"
    RETURN     = "RETURN"
    ADJUSTMENT = "ADJUSTMENT"


class InventoryTransaction(TimestampMixin, db.Model):
    """
    Represents a single stock movement event for a product.

    Table: inventory_transactions
    """

    __tablename__ = "inventory_transactions"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Foreign keys ──────────────────────────────────────────────────────────
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Optional: link a SALE / RETURN transaction to its order.
    # Stored as integer rather than a FK to avoid a circular import with the
    # future Order model.  The Order model will add a back-reference once created.
    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # ── Transaction data ──────────────────────────────────────────────────────
    transaction_type = db.Column(
        db.String(20),
        nullable=False,
        index=True,
    )

    # Positive = stock added (STOCK_IN, RETURN).
    # Negative = stock removed (STOCK_OUT, SALE, negative ADJUSTMENT).
    quantity = db.Column(
        db.Integer,
        nullable=False,
    )

    # Human-readable reason / note for the transaction.
    notes = db.Column(db.Text, nullable=True)

    # Staff member who performed the adjustment (user_id from the JWT).
    performed_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Relationship ──────────────────────────────────────────────────────────
    product = db.relationship("Product", backref=db.backref("inventory_transactions", lazy="dynamic"))

    def __repr__(self) -> str:
        return (
            f"<InventoryTransaction id={self.id} product_id={self.product_id} "
            f"type={self.transaction_type} qty={self.quantity}>"
        )
