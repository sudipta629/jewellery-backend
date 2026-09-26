"""
app/models/category.py

SQLAlchemy model for the `categories` table.

A category groups related jewellery products (e.g. Rings, Necklaces, Gold).

Relationships
-------------
Category → Products  (one-to-many)
    Each category can have many products.
    Products are NOT deleted when a category is soft-deleted — they
    simply remain assigned to an inactive category until reassigned.
"""

from app.extensions import db
from app.models.base import TimestampMixin


class Category(TimestampMixin, db.Model):
    """
    Represents a product category in the jewellery store.

    Table: categories
    """

    __tablename__ = "categories"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Core fields ───────────────────────────────────────────────────────────
    name = db.Column(
        db.String(100),
        nullable=False,
    )

    # URL-friendly identifier — must be unique and URL-safe.
    # Example: "gold-rings", "diamond-earrings"
    slug = db.Column(
        db.String(100),
        nullable=False,
        unique=True,
        index=True,
    )

    description = db.Column(
        db.Text,
        nullable=True,
    )

    # URL of the category banner/thumbnail image (stored externally).
    image_url = db.Column(
        db.String(500),
        nullable=True,
    )

    # Soft-delete flag: False = hidden from public API.
    is_active = db.Column(
        db.Boolean,
        nullable=False,
        default=True,
        index=True,
    )

    # ── Relationship ──────────────────────────────────────────────────────────
    # passive_deletes=True: relies on the DB's ON DELETE SET NULL / RESTRICT
    # rather than loading all child products into memory before a delete.
    # We do NOT cascade-delete products when a category is removed.
    products = db.relationship(
        "Product",
        back_populates="category",
        lazy="select",
        passive_deletes=True,
    )

    def __repr__(self) -> str:
        return f"<Category id={self.id} name={self.name!r} active={self.is_active}>"
