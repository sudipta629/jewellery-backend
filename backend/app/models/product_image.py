"""
app/models/product_image.py

SQLAlchemy model for the `product_images` table.

A product can have multiple images stored as external URLs.
Actual image upload/cloud storage is NOT implemented here —
that belongs to a later step (Cloudinary / S3 / Firebase).

Relationships
-------------
ProductImage → Product  (many-to-one)
    Every image row belongs to one product.
    When the product is deleted, all its images are deleted too
    (cascade="all, delete-orphan" defined on Product.images).
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import mapped_column, MappedColumn

from app.extensions import db


class ProductImage(db.Model):
    """
    Stores a single image URL for a product.

    Table: product_images

    Note: Only `created_at` is included (images are not edited, they are
    replaced).  No `updated_at` is needed.
    """

    __tablename__ = "product_images"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Foreign key ───────────────────────────────────────────────────────────
    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Image fields ──────────────────────────────────────────────────────────
    # URL pointing to the image hosted on an external CDN / cloud storage.
    image_url = db.Column(db.String(500), nullable=False)

    # Accessibility text and UI label.
    alt_text = db.Column(db.String(200), nullable=True)

    # Controls display order in the frontend gallery (lower = earlier).
    sort_order = db.Column(db.Integer, nullable=False, default=0)

    # Only one image per product should have is_primary=True.
    # This is enforced at the service layer when setting a new primary.
    is_primary = db.Column(db.Boolean, nullable=False, default=False)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # ── Relationship ──────────────────────────────────────────────────────────
    product = db.relationship("Product", back_populates="images")

    def __repr__(self) -> str:
        return (
            f"<ProductImage id={self.id} product_id={self.product_id} "
            f"primary={self.is_primary} order={self.sort_order}>"
        )
