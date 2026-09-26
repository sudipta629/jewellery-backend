"""
app/models/offer.py

SQLAlchemy models for offers, coupons, and banners.

Offer     — Category/product-level discount promotions.
Coupon    — Code-based discounts applied at checkout.
CouponUsage — Tracks per-user coupon usage (prevents abuse).
Banner    — Homepage/promotional banners.
"""

import enum
from datetime import datetime, timezone

from app.extensions import db
from app.models.base import TimestampMixin


class DiscountType(str, enum.Enum):
    PERCENTAGE = "PERCENTAGE"
    FIXED      = "FIXED"


# ══════════════════════════════════════════════════════════════════════════════
# Offer
# ══════════════════════════════════════════════════════════════════════════════

class Offer(TimestampMixin, db.Model):
    """
    Represents a promotional offer on a category or all products.

    Table: offers

    Computed status (not stored):
        ACTIVE   — is_active=True, now between start_date and end_date
        UPCOMING — is_active=True, start_date > now
        EXPIRED  — is_active=True, end_date < now
        DISABLED — is_active=False
    """

    __tablename__ = "offers"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    title       = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text,        nullable=True)

    discount_type  = db.Column(db.String(20), nullable=False)  # PERCENTAGE | FIXED
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)

    minimum_purchase = db.Column(db.Numeric(12, 2), nullable=True)   # min order value
    maximum_discount = db.Column(db.Numeric(12, 2), nullable=True)   # cap for percentage

    start_date = db.Column(db.DateTime(timezone=True), nullable=True)
    end_date   = db.Column(db.DateTime(timezone=True), nullable=True)

    # Optional: restrict to a category (None = all products)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    # ── Relationship ──────────────────────────────────────────────────────────
    category = db.relationship("Category", backref=db.backref("offers", lazy="dynamic"))

    def get_computed_status(self) -> str:
        """Return the computed display status of the offer."""
        now = datetime.now(timezone.utc)
        if not self.is_active:
            return "DISABLED"
        if self.start_date and now < self.start_date:
            return "UPCOMING"
        if self.end_date and now > self.end_date:
            return "EXPIRED"
        return "ACTIVE"

    def __repr__(self) -> str:
        return f"<Offer id={self.id} title={self.title!r} status={self.get_computed_status()}>"


# ══════════════════════════════════════════════════════════════════════════════
# Coupon
# ══════════════════════════════════════════════════════════════════════════════

class Coupon(TimestampMixin, db.Model):
    """
    Represents a promotional coupon code.

    Table: coupons

    CRITICAL: Discount amounts must ALWAYS be calculated server-side.
    Never trust a discount value sent from the frontend.
    """

    __tablename__ = "coupons"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # The alphanumeric code the customer enters (e.g. "GOLD10")
    code = db.Column(
        db.String(50),
        nullable=False,
        unique=True,
        index=True,
    )

    description    = db.Column(db.Text, nullable=True)
    discount_type  = db.Column(db.String(20), nullable=False)
    discount_value = db.Column(db.Numeric(10, 2), nullable=False)

    minimum_order    = db.Column(db.Numeric(12, 2), nullable=True)   # minimum cart value
    maximum_discount = db.Column(db.Numeric(12, 2), nullable=True)   # cap for percentage

    usage_limit     = db.Column(db.Integer, nullable=True)           # total uses allowed
    per_user_limit  = db.Column(db.Integer, nullable=True, default=1) # uses per customer

    start_date = db.Column(db.DateTime(timezone=True), nullable=True)
    end_date   = db.Column(db.DateTime(timezone=True), nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    # ── Relationship ──────────────────────────────────────────────────────────
    usages = db.relationship(
        "CouponUsage",
        back_populates="coupon",
        cascade="all, delete-orphan",
        lazy="dynamic",
    )

    def get_computed_status(self) -> str:
        """Return computed display status."""
        now = datetime.now(timezone.utc)
        if not self.is_active:
            return "DISABLED"
        if self.start_date and now < self.start_date:
            return "UPCOMING"
        if self.end_date and now > self.end_date:
            return "EXPIRED"
        return "ACTIVE"

    def get_total_usage(self) -> int:
        """Return total number of times this coupon has been used."""
        return self.usages.count()

    def __repr__(self) -> str:
        return f"<Coupon id={self.id} code={self.code!r}>"


class CouponUsage(TimestampMixin, db.Model):
    """
    Records each time a coupon is used by a customer.

    Table: coupon_usages

    Used to enforce per-user and global usage limits.
    """

    __tablename__ = "coupon_usages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    coupon_id = db.Column(
        db.Integer,
        db.ForeignKey("coupons.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
    )

    discount_applied = db.Column(db.Numeric(12, 2), nullable=False)

    coupon = db.relationship("Coupon", back_populates="usages")

    def __repr__(self) -> str:
        return f"<CouponUsage id={self.id} coupon_id={self.coupon_id} user_id={self.user_id}>"


# ══════════════════════════════════════════════════════════════════════════════
# Banner
# ══════════════════════════════════════════════════════════════════════════════

class Banner(TimestampMixin, db.Model):
    """
    Represents a promotional banner shown on the website/app.

    Table: banners
    """

    __tablename__ = "banners"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    title             = db.Column(db.String(200), nullable=False)
    image_url         = db.Column(db.String(500), nullable=False)
    mobile_image_url  = db.Column(db.String(500), nullable=True)   # responsive variant
    link_url          = db.Column(db.String(500), nullable=True)   # CTA destination

    display_order = db.Column(db.Integer, nullable=False, default=0, index=True)

    start_date = db.Column(db.DateTime(timezone=True), nullable=True)
    end_date   = db.Column(db.DateTime(timezone=True), nullable=True)

    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    def is_currently_visible(self) -> bool:
        """Return True if the banner should be visible to the public now."""
        now = datetime.now(timezone.utc)
        if not self.is_active:
            return False
        if self.start_date and now < self.start_date:
            return False
        if self.end_date and now > self.end_date:
            return False
        return True

    def __repr__(self) -> str:
        return f"<Banner id={self.id} title={self.title!r} active={self.is_active}>"
