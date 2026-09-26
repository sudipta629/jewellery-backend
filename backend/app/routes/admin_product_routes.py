"""
app/routes/admin_product_routes.py

Admin-only product management endpoints (CRUD + media).

All routes require a valid JWT with any admin role.

Endpoints
---------
GET    /api/v1/admin/products/                       Paginated list (all products).
GET    /api/v1/admin/products/<id>                   Single product (any status).
POST   /api/v1/admin/products/                       Create a product.
PUT    /api/v1/admin/products/<id>                   Update a product.
DELETE /api/v1/admin/products/<id>                   Soft-delete (is_active=False).

Media
-----
POST   /api/v1/admin/products/<id>/media             Add an image/media.
PUT    /api/v1/admin/products/<id>/media/<media_id>  Update an image/media.
DELETE /api/v1/admin/products/<id>/media/<media_id>  Delete an image/media.

Security
--------
* @require_admin validates the JWT AND checks role is an admin role.
* Inventory staff can read products; only admin/super_admin can modify.
* Slug + SKU uniqueness enforced at the service layer (409 Conflict).
"""

import logging

from flask import Blueprint, jsonify, request

from app.services.product_service import ProductService, VALID_SORTS
from app.utils.decorators import (
    require_admin,
    require_role,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_INVENTORY_STAFF,
    ROLE_SALES_STAFF,
)

logger = logging.getLogger(__name__)

admin_products_bp = Blueprint("admin_products", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_bool(value: str | None) -> bool | None:
    """Convert query-string boolean strings to Python bool."""
    if value is None:
        return None
    return str(value).lower() in ("true", "1", "yes")


def _build_params() -> dict:
    """Extract and coerce all query parameters for product filtering."""
    args = request.args
    return {
        "search":      args.get("search", "").strip(),
        "category_id": args.get("category_id"),
        "metal_type":  args.get("metal_type", "").strip(),
        "purity":      args.get("purity", "").strip(),
        "is_featured": _parse_bool(args.get("is_featured")),
        "is_new":      _parse_bool(args.get("is_new")),
        "is_active":   _parse_bool(args.get("is_active")),
        "stock_only":  _parse_bool(args.get("stock_only")),
        "min_weight":  args.get("min_weight"),
        "max_weight":  args.get("max_weight"),
        "page":        args.get("page", 1),
        "per_page":    args.get("per_page", 20),
        "sort":        args.get("sort", "newest"),
    }


# ── GET / ─────────────────────────────────────────────────────────────────────

@admin_products_bp.get("/")
@require_admin
def list_products():
    """
    Paginated, filterable, sortable list of ALL products (active + inactive).

    Query parameters:
        search      — text search across name, SKU, slug, metal_type, purity
        category_id — integer
        metal_type  — string
        purity      — string
        is_featured — true | false
        is_new      — true | false
        is_active   — true | false (admin can see inactive)
        stock_only  — true | false
        min_weight  — float
        max_weight  — float
        page        — integer, default 1
        per_page    — integer, default 20, max 100
        sort        — newest | oldest | name_asc | name_desc | weight_asc | weight_desc

    Response (200):
        {
            "status": "success",
            "data": [...],
            "pagination": { "page": 1, "per_page": 20, "total": 50, "pages": 3 }
        }
    """
    params   = _build_params()
    sort_key = params.get("sort", "newest")

    if sort_key not in VALID_SORTS:
        return jsonify({
            "status":  "error",
            "message": f"Invalid sort value. Allowed: {', '.join(VALID_SORTS.keys())}.",
        }), 400

    result = ProductService.get_all_products_paginated(params)

    return jsonify({
        "status":     "success",
        "data":       [ProductService.serialize(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200


# ── GET /<id> ─────────────────────────────────────────────────────────────────

@admin_products_bp.get("/<int:product_id>")
@require_admin
def get_product(product_id: int):
    """
    Return full details of one product (active or inactive).

    Response (200): { "status": "success", "data": { ... } }
    Error    (404): { "status": "error", "message": "Product not found." }
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    return jsonify({
        "status": "success",
        "data":   ProductService.serialize(product),
    }), 200


# ── POST / ────────────────────────────────────────────────────────────────────

@admin_products_bp.post("/")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_STAFF)
def create_product():
    """
    Create a new product.

    Required fields:
        sku, name, slug, category_id, metal_type

    Optional fields:
        description, purity, gross_weight, net_weight,
        making_charge, stone_charge, gst_percentage,
        stock_quantity, is_featured, is_new, is_active,
        gender, occasion

    Response (201): { "status": "success", "message": "Product created.", "data": { ... } }
    Errors: 400, 401, 403, 409 (duplicate SKU/slug), 422 (invalid category).
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    errors = ProductService.validate(data, require_all=True)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    try:
        product = ProductService.create(data)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409

    return jsonify({
        "status":  "success",
        "message": "Product created.",
        "data":    ProductService.serialize(product),
    }), 201


# ── PUT /<id> ─────────────────────────────────────────────────────────────────

@admin_products_bp.put("/<int:product_id>")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_STAFF)
def update_product(product_id: int):
    """
    Partial update of a product — only sent fields are changed.

    Response (200): { "status": "success", "message": "Product updated.", "data": { ... } }
    Errors: 400, 401, 403, 404, 409.
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    errors = ProductService.validate(data, require_all=False)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    try:
        updated = ProductService.update(product, data)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409

    return jsonify({
        "status":  "success",
        "message": "Product updated.",
        "data":    ProductService.serialize(updated),
    }), 200


# ── DELETE /<id> ──────────────────────────────────────────────────────────────

@admin_products_bp.delete("/<int:product_id>")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def delete_product(product_id: int):
    """
    Soft-delete a product (sets is_active=False).

    Response (200): { "status": "success", "message": "Product deactivated." }
    Errors: 401, 403, 404.
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    ProductService.soft_delete(product)

    return jsonify({
        "status":  "success",
        "message": "Product deactivated.",
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
# MEDIA MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

# ── POST /<id>/media ──────────────────────────────────────────────────────────

@admin_products_bp.post("/<int:product_id>/media")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_STAFF)
def add_media(product_id: int):
    """
    Add an image/media URL to a product.

    Request body:
        {
            "image_url":  "https://...",   (required)
            "alt_text":   "...",           (optional)
            "sort_order": 0,               (optional, default 0)
            "is_primary": false            (optional, default false)
        }

    IMPORTANT: Large binary image files must NOT be stored in PostgreSQL.
    Use a CDN/cloud storage (Cloudinary, S3, Firebase Storage) and supply
    the resulting URL here.

    Response (201): { "status": "success", "message": "Media added.", "data": { ... } }
    Errors: 400, 401, 403, 404.
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    if not str(data.get("image_url", "")).strip():
        return jsonify({"status": "error", "message": "'image_url' is required."}), 400

    image = ProductService.add_image(product_id, data)

    return jsonify({
        "status":  "success",
        "message": "Media added.",
        "data":    ProductService.serialize_image(image),
    }), 201


# ── PUT /<id>/media/<media_id> ────────────────────────────────────────────────

@admin_products_bp.put("/<int:product_id>/media/<int:media_id>")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_STAFF)
def update_media(product_id: int, media_id: int):
    """
    Update a product image/media entry.

    Request body (all fields optional):
        {
            "image_url":  "https://...",
            "alt_text":   "...",
            "sort_order": 1,
            "is_primary": true
        }

    Response (200): { "status": "success", "message": "Media updated.", "data": { ... } }
    Errors: 400, 401, 403, 404.
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    image = ProductService.get_image(media_id, product_id)
    if image is None:
        return jsonify({"status": "error", "message": "Media not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    updated = ProductService.update_image(image, data)

    return jsonify({
        "status":  "success",
        "message": "Media updated.",
        "data":    ProductService.serialize_image(updated),
    }), 200


# ── DELETE /<id>/media/<media_id> ─────────────────────────────────────────────

@admin_products_bp.delete("/<int:product_id>/media/<int:media_id>")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_STAFF)
def delete_media(product_id: int, media_id: int):
    """
    Hard-delete a product image/media entry.

    Response (200): { "status": "success", "message": "Media deleted." }
    Errors: 401, 403, 404.
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    image = ProductService.get_image(media_id, product_id)
    if image is None:
        return jsonify({"status": "error", "message": "Media not found."}), 404

    ProductService.delete_image(image)

    return jsonify({
        "status":  "success",
        "message": "Media deleted.",
    }), 200
