"""
app/services/product_service.py

Business logic for product and product-image management.

Architecture
------------
    routes/product_routes.py          (public read)
    routes/admin_product_routes.py    (admin CRUD + image management)
        ↓  calls
    ProductService  (this file)
        ↓  queries
    Product / ProductImage models / db.session

Pricing note
------------
There is NO price field.  Jewellery pricing will be calculated dynamically
by a future pricing engine:
    price = (metal_rate × net_weight) + making_charge + stone_charge + GST
"""

import logging

from sqlalchemy.orm import joinedload

from app.extensions import db
from app.models.category import Category
from app.models.product import Product
from app.models.product_image import ProductImage

logger = logging.getLogger(__name__)

# ── Valid sort options ─────────────────────────────────────────────────────────
VALID_SORTS = {
    "newest":      lambda q: q.order_by(Product.created_at.desc()),
    "oldest":      lambda q: q.order_by(Product.created_at.asc()),
    "name_asc":    lambda q: q.order_by(Product.name.asc()),
    "name_desc":   lambda q: q.order_by(Product.name.desc()),
    "weight_asc":  lambda q: q.order_by(Product.gross_weight.asc()),
    "weight_desc": lambda q: q.order_by(Product.gross_weight.desc()),
}


class ProductService:
    """
    Handles product CRUD, filtering, pagination, sorting, and image management.
    All methods are static — no instance state is needed.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # Serialization
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def serialize_image(image: ProductImage) -> dict:
        return {
            "id":         image.id,
            "image_url":  image.image_url,
            "alt_text":   image.alt_text,
            "sort_order": image.sort_order,
            "is_primary": image.is_primary,
        }

    @staticmethod
    def serialize(product: Product, include_images: bool = True) -> dict:
        """
        Convert a Product to a JSON-safe dict.

        Decimal fields (weights, charges) are converted to float.
        At 2 decimal places, float representation is accurate.
        """
        from app.services.category_service import CategoryService

        data: dict = {
            "id":            product.id,
            "sku":           product.sku,
            "name":          product.name,
            "slug":          product.slug,
            "description":   product.description,
            "category":      CategoryService.serialize_short(product.category) if product.category else None,
            "metal_type":    product.metal_type,
            "purity":        product.purity,
            "gross_weight":  float(product.gross_weight)  if product.gross_weight  is not None else None,
            "net_weight":    float(product.net_weight)    if product.net_weight    is not None else None,
            "making_charge": float(product.making_charge),
            "stone_charge":  float(product.stone_charge),
            "gst_percentage":float(product.gst_percentage),
            "stock_quantity":product.stock_quantity,
            "is_featured":   product.is_featured,
            "is_new":        product.is_new,
            "is_active":     product.is_active,
            "created_at":    product.created_at.isoformat() if product.created_at else None,
            "updated_at":    product.updated_at.isoformat() if product.updated_at else None,
        }
        if include_images:
            data["images"] = [ProductService.serialize_image(img) for img in product.images]
        return data

    # ══════════════════════════════════════════════════════════════════════════
    # Validation
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def validate(data: dict, require_all: bool = True) -> list[str]:
        """
        Validate product input data.

        Args:
            data:        Dict of fields from the request body.
            require_all: True for POST (all required fields must be present),
                         False for PUT (only validate present fields).

        Returns:
            List of error messages. Empty = pass.
        """
        errors: list[str] = []
        REQUIRED = ("sku", "name", "slug", "category_id", "metal_type")

        if require_all:
            for field in REQUIRED:
                if not str(data.get(field, "")).strip():
                    errors.append(f"'{field}' is required.")

        if "name" in data and len(str(data["name"]).strip()) > 200:
            errors.append("'name' must not exceed 200 characters.")

        # Non-negative numeric fields
        for field in ("gross_weight", "net_weight", "making_charge", "stone_charge", "gst_percentage"):
            if field in data and data[field] is not None:
                try:
                    val = float(data[field])
                    if val < 0:
                        errors.append(f"'{field}' cannot be negative.")
                except (TypeError, ValueError):
                    errors.append(f"'{field}' must be a valid number.")

        if "stock_quantity" in data and data["stock_quantity"] is not None:
            try:
                if int(data["stock_quantity"]) < 0:
                    errors.append("'stock_quantity' cannot be negative.")
            except (TypeError, ValueError):
                errors.append("'stock_quantity' must be an integer.")

        if "category_id" in data and data["category_id"] is not None:
            try:
                int(data["category_id"])
            except (TypeError, ValueError):
                errors.append("'category_id' must be an integer.")

        return errors

    # ══════════════════════════════════════════════════════════════════════════
    # Query helpers
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _base_query(active_only: bool = True):
        """Build a base query with eager-loaded category and images."""
        q = Product.query.options(
            joinedload(Product.category),
            joinedload(Product.images),
        )
        if active_only:
            q = q.filter(Product.is_active == True)  # noqa: E712
        return q

    @staticmethod
    def _apply_filters(query, params: dict):
        """Apply search, category, metal, purity, flags, and weight filters."""
        search = str(params.get("search", "")).strip()
        if search:
            term = f"%{search}%"
            query = query.filter(
                db.or_(
                    Product.name.ilike(term),
                    Product.sku.ilike(term),
                    Product.slug.ilike(term),
                    Product.metal_type.ilike(term),
                    Product.purity.ilike(term),
                )
            )

        if params.get("category_id"):
            try:
                query = query.filter(Product.category_id == int(params["category_id"]))
            except (TypeError, ValueError):
                pass

        if params.get("metal_type"):
            query = query.filter(Product.metal_type.ilike(str(params["metal_type"])))

        if params.get("purity"):
            query = query.filter(Product.purity.ilike(str(params["purity"])))

        if params.get("is_featured") is not None:
            query = query.filter(Product.is_featured == bool(params["is_featured"]))

        if params.get("is_new") is not None:
            query = query.filter(Product.is_new == bool(params["is_new"]))

        if params.get("stock_only"):
            query = query.filter(Product.stock_quantity > 0)

        # Weight range
        if params.get("min_weight") is not None:
            try:
                query = query.filter(Product.gross_weight >= float(params["min_weight"]))
            except (TypeError, ValueError):
                pass

        if params.get("max_weight") is not None:
            try:
                query = query.filter(Product.gross_weight <= float(params["max_weight"]))
            except (TypeError, ValueError):
                pass

        # NOTE: min_price / max_price are intentionally NOT implemented here.
        # Jewellery pricing is dynamic (metal rate × weight + charges + GST).
        # A pricing engine will be added in a later step.

        return query

    # ══════════════════════════════════════════════════════════════════════════
    # Public product listing
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_products_paginated(params: dict) -> dict:
        """
        Return a paginated, filtered, sorted list of active products.

        Args:
            params: Combined dict of all query parameters (search, filters,
                    pagination, sort).

        Returns:
            {
                "items":      [Product, ...],
                "pagination": { page, per_page, total, pages, has_next, has_prev }
            }
        """
        # Pagination bounds
        try:
            page = max(1, int(params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            per_page = min(100, max(1, int(params.get("per_page", 20))))
        except (TypeError, ValueError):
            per_page = 20

        # Sort
        sort_key = str(params.get("sort", "newest"))
        sort_fn  = VALID_SORTS.get(sort_key, VALID_SORTS["newest"])

        query = ProductService._base_query(active_only=True)
        query = ProductService._apply_filters(query, params)
        query = sort_fn(query)

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
    def get_active_product_by_id(product_id: int) -> Product | None:
        """Return one active product with eager-loaded relations, or None."""
        return (
            ProductService._base_query(active_only=True)
            .filter(Product.id == product_id)
            .first()
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Admin product listing
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_all_products_paginated(params: dict) -> dict:
        """Admin version — includes inactive products."""
        try:
            page = max(1, int(params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            per_page = min(100, max(1, int(params.get("per_page", 20))))
        except (TypeError, ValueError):
            per_page = 20

        sort_key = str(params.get("sort", "newest"))
        sort_fn  = VALID_SORTS.get(sort_key, VALID_SORTS["newest"])

        query = ProductService._base_query(active_only=False)
        query = ProductService._apply_filters(query, params)
        query = sort_fn(query)

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
    def get_product_by_id(product_id: int) -> Product | None:
        """Admin: return any product (active or inactive), or None."""
        return (
            ProductService._base_query(active_only=False)
            .filter(Product.id == product_id)
            .first()
        )

    # ══════════════════════════════════════════════════════════════════════════
    # Admin product CRUD
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def create(data: dict) -> Product:
        """
        Create a new product.

        Raises:
            ValueError: On duplicate SKU, duplicate slug, or invalid category.
        """
        # Category must exist
        category = db.session.get(Category, int(data["category_id"]))
        if not category:
            raise ValueError("Invalid 'category_id': category does not exist.")

        # Uniqueness checks
        if Product.query.filter_by(sku=str(data["sku"]).strip()).first():
            raise ValueError("A product with this SKU already exists.")
        if Product.query.filter_by(slug=str(data["slug"]).strip()).first():
            raise ValueError("A product with this slug already exists.")

        product = Product(
            sku=str(data["sku"]).strip(),
            name=str(data["name"]).strip(),
            slug=str(data["slug"]).strip(),
            description=data.get("description") or None,
            category_id=int(data["category_id"]),
            metal_type=str(data["metal_type"]).strip(),
            purity=data.get("purity") or None,
            gross_weight=data.get("gross_weight"),
            net_weight=data.get("net_weight"),
            making_charge=data.get("making_charge", 0),
            stone_charge=data.get("stone_charge", 0),
            gst_percentage=data.get("gst_percentage", 0),
            stock_quantity=int(data.get("stock_quantity", 0)),
            is_featured=bool(data.get("is_featured", False)),
            is_new=bool(data.get("is_new", False)),
            is_active=bool(data.get("is_active", True)),
        )
        db.session.add(product)
        db.session.commit()
        logger.info("[ProductService] Created product id=%s sku=%r", product.id, product.sku)
        return product

    @staticmethod
    def update(product: Product, data: dict) -> Product:
        """
        Apply partial updates to a product.

        Raises:
            ValueError: On duplicate SKU/slug or invalid category.
        """
        if "sku" in data:
            new_sku = str(data["sku"]).strip()
            if Product.query.filter(Product.sku == new_sku, Product.id != product.id).first():
                raise ValueError("A product with this SKU already exists.")
            product.sku = new_sku

        if "slug" in data:
            new_slug = str(data["slug"]).strip()
            if Product.query.filter(Product.slug == new_slug, Product.id != product.id).first():
                raise ValueError("A product with this slug already exists.")
            product.slug = new_slug

        if "category_id" in data:
            category = db.session.get(Category, int(data["category_id"]))
            if not category:
                raise ValueError("Invalid 'category_id': category does not exist.")
            product.category_id = int(data["category_id"])

        if "name" in data:
            product.name = str(data["name"]).strip()
        if "description" in data:
            product.description = data["description"] or None
        if "metal_type" in data:
            product.metal_type = str(data["metal_type"]).strip()
        if "purity" in data:
            product.purity = data["purity"] or None

        for field in ("gross_weight", "net_weight", "making_charge", "stone_charge", "gst_percentage"):
            if field in data:
                setattr(product, field, data[field])

        if "stock_quantity" in data:
            product.stock_quantity = int(data["stock_quantity"])

        for field in ("is_featured", "is_new", "is_active"):
            if field in data:
                setattr(product, field, bool(data[field]))

        db.session.commit()
        logger.info("[ProductService] Updated product id=%s", product.id)
        return product

    @staticmethod
    def soft_delete(product: Product) -> None:
        """Soft-delete: set is_active=False."""
        product.is_active = False
        db.session.commit()
        logger.info("[ProductService] Soft-deleted product id=%s", product.id)

    # ══════════════════════════════════════════════════════════════════════════
    # Image management
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_image(image_id: int, product_id: int) -> ProductImage | None:
        """Fetch a ProductImage that belongs to the given product."""
        return ProductImage.query.filter_by(id=image_id, product_id=product_id).first()

    @staticmethod
    def add_image(product_id: int, data: dict) -> ProductImage:
        """
        Add an image to a product.

        If is_primary=True, all other images of this product are set to
        is_primary=False atomically.
        """
        if data.get("is_primary"):
            ProductImage.query.filter_by(
                product_id=product_id, is_primary=True
            ).update({"is_primary": False})

        image = ProductImage(
            product_id=product_id,
            image_url=str(data["image_url"]).strip(),
            alt_text=data.get("alt_text") or None,
            sort_order=int(data.get("sort_order", 0)),
            is_primary=bool(data.get("is_primary", False)),
        )
        db.session.add(image)
        db.session.commit()
        logger.info("[ProductService] Added image id=%s to product_id=%s", image.id, product_id)
        return image

    @staticmethod
    def update_image(image: ProductImage, data: dict) -> ProductImage:
        """
        Update a product image.

        If is_primary=True, clears primary on all other images of the
        same product first.
        """
        if data.get("is_primary") is True:
            ProductImage.query.filter(
                ProductImage.product_id == image.product_id,
                ProductImage.id != image.id,
            ).update({"is_primary": False})
            image.is_primary = True
        elif data.get("is_primary") is False:
            image.is_primary = False

        if "image_url" in data:
            image.image_url = str(data["image_url"]).strip()
        if "alt_text" in data:
            image.alt_text = data["alt_text"] or None
        if "sort_order" in data:
            image.sort_order = int(data["sort_order"])

        db.session.commit()
        logger.info("[ProductService] Updated image id=%s", image.id)
        return image

    @staticmethod
    def delete_image(image: ProductImage) -> None:
        """Hard-delete a product image row."""
        image_id   = image.id
        db.session.delete(image)
        db.session.commit()
        logger.info("[ProductService] Deleted image id=%s", image_id)
