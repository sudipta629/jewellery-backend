"""
app/models/cart.py

SQLAlchemy models for shopping cart and wishlist.

Cart      — Per-customer shopping cart session.
CartItem  — Individual product in a cart.
Wishlist  — Customer's saved product wishlist.

Design Notes
------------
* Only ONE active cart per customer at a time.
* Price is recalculated by the backend on every cart retrieval —
  the stored price is a HINT only, never trusted for final checkout.
* CartItem.price_snapshot stores the calculated price at the time the
  item was added (for display). Final price is always recomputed.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import mapped_column, MappedColumn

from app.extensions import db
from app.models.base import TimestampMixin


class Cart(TimestampMixin, db.Model):
    """
    Shopping cart for a customer.

    Table: carts
    """

    __tablename__ = "carts"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,    # one active cart per user
        index=True,
    )

    items = db.relationship(
        "CartItem",
        back_populates="cart",
        cascade="all, delete-orphan",
        lazy="select",
    )

    user = db.relationship("User", backref=db.backref("cart", uselist=False))

    def __repr__(self) -> str:
        return f"<Cart id={self.id} user_id={self.user_id}>"


class CartItem(TimestampMixin, db.Model):
    """
    A single product line item in a shopping cart.

    Table: cart_items
    """

    __tablename__ = "cart_items"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    cart_id = db.Column(
        db.Integer,
        db.ForeignKey("carts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    quantity = db.Column(db.Integer, nullable=False, default=1)

    # Price snapshot at time of adding to cart (informational only).
    # Final price is always recalculated from current metal rates.
    price_snapshot = db.Column(db.Numeric(12, 2), nullable=True)

    # Relationships
    cart    = db.relationship("Cart",    back_populates="items")
    product = db.relationship("Product", backref=db.backref("cart_items", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<CartItem id={self.id} cart_id={self.cart_id} product_id={self.product_id}>"


class Wishlist(TimestampMixin, db.Model):
    """
    Customer's saved wishlist.

    Table: wishlists

    Each row represents one product saved by one customer.
    """

    __tablename__ = "wishlists"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Unique constraint ──────────────────────────────────────────────────────
    __table_args__ = (
        db.UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),
    )

    user    = db.relationship("User",    backref=db.backref("wishlist_items", lazy="dynamic"))
    product = db.relationship("Product", backref=db.backref("wishlist_items", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<Wishlist id={self.id} user_id={self.user_id} product_id={self.product_id}>"
