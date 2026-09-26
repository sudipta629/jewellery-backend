"""
app/services/category_service.py

Business logic for category management.

Architecture
------------
    routes/category_routes.py         (public read)
    routes/admin_category_routes.py   (admin CRUD)
        ↓  calls
    CategoryService  (this file)
        ↓  queries
    Category model / db.session
"""

import logging
import re

from app.extensions import db
from app.models.category import Category

logger = logging.getLogger(__name__)

# Slug must contain only lowercase letters, digits, and hyphens.
_SLUG_RE = re.compile(r"^[a-z0-9-]+$")


class CategoryService:
    """
    Handles all category operations: CRUD, validation, serialization.
    All methods are static — no instance state is needed.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # Serialization
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def serialize(category: Category, include_timestamps: bool = True) -> dict:
        """
        Convert a Category to a JSON-safe dict.

        Args:
            category:           The Category model instance.
            include_timestamps: If True, add created_at / updated_at.

        Returns:
            Plain dict safe for JSON responses.
        """
        data = {
            "id":          category.id,
            "name":        category.name,
            "slug":        category.slug,
            "description": category.description,
            "image_url":   category.image_url,
            "is_active":   category.is_active,
        }
        if include_timestamps:
            data["created_at"] = category.created_at.isoformat() if category.created_at else None
            data["updated_at"] = category.updated_at.isoformat() if category.updated_at else None
        return data

    @staticmethod
    def serialize_short(category: Category) -> dict:
        """Minimal dict used when embedding category inside a product response."""
        return {
            "id":   category.id,
            "name": category.name,
            "slug": category.slug,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Validation
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def validate(data: dict, require_all: bool = True) -> list[str]:
        """
        Validate category input data.

        Args:
            data:        Dict of fields from the request body.
            require_all: If True, name and slug must be present (for POST).
                         If False, only present fields are validated (for PUT).

        Returns:
            List of human-readable error messages. Empty = pass.
        """
        errors: list[str] = []

        if require_all:
            if not str(data.get("name", "")).strip():
                errors.append("'name' is required.")
            if not str(data.get("slug", "")).strip():
                errors.append("'slug' is required.")

        if "name" in data:
            if len(str(data["name"]).strip()) > 100:
                errors.append("'name' must not exceed 100 characters.")

        if "slug" in data:
            slug = str(data["slug"]).strip()
            if slug and not _SLUG_RE.match(slug):
                errors.append(
                    "'slug' must contain only lowercase letters, digits, and hyphens "
                    "(e.g. 'gold-rings')."
                )

        return errors

    # ══════════════════════════════════════════════════════════════════════════
    # Queries
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_active_categories() -> list[Category]:
        """Return all is_active=True categories, alphabetically sorted."""
        return (
            Category.query
            .filter_by(is_active=True)
            .order_by(Category.name.asc())
            .all()
        )

    @staticmethod
    def get_all_paginated(
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        is_active: str | None = None,
    ) -> dict:
        """
        Admin: paginated list of all categories (active and inactive).

        Args:
            page:      Page number (1-indexed).
            per_page:  Items per page (max 100).
            search:    Case-insensitive search on name / slug.
            is_active: Optional filter string "true" / "false".

        Returns:
            { "items": [...], "pagination": {...} }
        """
        query = Category.query

        if search:
            term  = f"%{search}%"
            query = query.filter(
                db.or_(
                    Category.name.ilike(term),
                    Category.slug.ilike(term),
                )
            )

        if is_active is not None:
            flag  = str(is_active).lower() in ("true", "1", "yes")
            query = query.filter(Category.is_active == flag)

        query = query.order_by(Category.name.asc())
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            "items": pagination.items,
            "pagination": {
                "page":     page,
                "per_page": per_page,
                "total":    pagination.total,
                "pages":    pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }

    @staticmethod
    def get_active_by_id(category_id: int) -> Category | None:
        """Return one active category by PK, or None."""
        return Category.query.filter_by(id=category_id, is_active=True).first()

    @staticmethod
    def get_by_id(category_id: int) -> Category | None:
        """Admin: return any category (active or inactive) by PK."""
        return db.session.get(Category, category_id)

    # ══════════════════════════════════════════════════════════════════════════
    # CRUD
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def create(data: dict) -> Category:
        """
        Create a new category.

        Raises:
            ValueError: If the slug already exists.
        """
        slug = str(data["slug"]).strip()
        if Category.query.filter_by(slug=slug).first():
            raise ValueError("A category with this slug already exists.")

        category = Category(
            name=str(data["name"]).strip(),
            slug=slug,
            description=str(data["description"]).strip() if data.get("description") else None,
            image_url=str(data["image_url"]).strip() if data.get("image_url") else None,
            is_active=bool(data.get("is_active", True)),
        )
        db.session.add(category)
        db.session.commit()
        logger.info("[CategoryService] Created category id=%s slug=%r", category.id, category.slug)
        return category

    @staticmethod
    def update(category: Category, data: dict) -> Category:
        """
        Apply partial updates to a category.

        Raises:
            ValueError: If the new slug conflicts with another category.
        """
        if "slug" in data:
            new_slug = str(data["slug"]).strip()
            conflict = Category.query.filter(
                Category.slug == new_slug,
                Category.id != category.id,
            ).first()
            if conflict:
                raise ValueError("A category with this slug already exists.")
            category.slug = new_slug

        if "name" in data:
            category.name = str(data["name"]).strip()
        if "description" in data:
            category.description = str(data["description"]).strip() if data["description"] else None
        if "image_url" in data:
            category.image_url = str(data["image_url"]).strip() if data["image_url"] else None
        if "is_active" in data:
            category.is_active = bool(data["is_active"])

        db.session.commit()
        logger.info("[CategoryService] Updated category id=%s", category.id)
        return category

    @staticmethod
    def soft_delete(category: Category) -> None:
        """
        Soft-delete: set is_active=False.

        Products in this category are NOT deleted — they remain assigned
        to the inactive category until an admin reassigns them.
        """
        category.is_active = False
        db.session.commit()
        logger.info("[CategoryService] Soft-deleted category id=%s", category.id)
