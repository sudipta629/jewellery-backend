"""
app/models/product.py

SQLAlchemy model for the `products` table.

Each row represents a unique jewellery product SKU.

Jewellery pricing note
-----------------------
There is NO `price` column in this table.  Jewellery prices are
calculated dynamically at order time:

    Final Price = (Metal Rate × Applicable Weight)
                + Making Charge
                + Stone Charge
                + GST

The live metal-rate pricing engine will be implemented in a later step.
This model stores only the static product attributes needed for that
calculation.

Relationships
-------------
Product → Category       (many-to-one)
Product → ProductImages  (one-to-many, cascade delete)
"""

from app.extensions import db
from app.models.base import TimestampMixin


class Product(TimestampMixin, db.Model):
    """
    Represents a jewellery product in the store catalogue.

    Table: products
    """

    __tablename__ = "products"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Stock Keeping Unit — unique catalogue identifier ──────────────────────
    # Example: "GLD-RNG-001"
    sku = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Product identity ──────────────────────────────────────────────────────
    name = db.Column(
        db.String(200),
        nullable=False,
        index=True,
    )

    # URL-friendly identifier. Example: "classic-gold-ring"
    slug = db.Column(
        db.String(200),
        nullable=False,
        unique=True,
        index=True,
    )

    description = db.Column(db.Text, nullable=True)

    # ── Category ──────────────────────────────────────────────────────────────
    # ON DELETE RESTRICT: prevents deleting a category that still has products.
    # Admin must move/deactivate products first.
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # ── Metal attributes ──────────────────────────────────────────────────────
    # Examples: "gold", "silver", "platinum", "diamond"
    metal_type = db.Column(db.String(50), nullable=False)

    # Examples: "22K", "18K", "24K", "925", "950"
    purity = db.Column(db.String(20), nullable=True)

    # ── Weight ────────────────────────────────────────────────────────────────
    # Numeric(10, 2) is used instead of Float to avoid floating-point
    # rounding errors in financial calculations.
    # gross_weight: total weight including stones and mounting.
    # net_weight:   weight of metal only (used in price calculation).
    gross_weight = db.Column(db.Numeric(10, 2), nullable=True)
    net_weight   = db.Column(db.Numeric(10, 2), nullable=True)

    # ── Pricing components ────────────────────────────────────────────────────
    # These are COMPONENTS of the final price, not the final price itself.
    # Final price = (metal_rate × net_weight) + making_charge + stone_charge + GST.
    making_charge  = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    stone_charge   = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    gst_percentage = db.Column(db.Numeric(5,  2), nullable=False, default=0)

    # ── Inventory ─────────────────────────────────────────────────────────────
    stock_quantity = db.Column(db.Integer, nullable=False, default=0)

    # ── Merchandising flags ───────────────────────────────────────────────────
    is_featured = db.Column(db.Boolean, nullable=False, default=False, index=True)
    is_new      = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # Soft-delete flag: False = hidden from public listing.
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)

    # ── Relationships ─────────────────────────────────────────────────────────
    category = db.relationship("Category", back_populates="products")

    # Cascade-delete product images when a product is hard-deleted.
    images = db.relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        lazy="select",
        order_by="ProductImage.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} sku={self.sku!r} name={self.name!r}>"
