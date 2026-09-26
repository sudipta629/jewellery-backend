"""
app/routes/admin_category_routes.py

Admin-only category management endpoints.

All routes require a valid JWT with any admin role
(super_admin, admin, sales_staff, inventory_staff).

Endpoints
---------
GET    /api/v1/admin/categories/          Paginated list (all, including inactive).
GET    /api/v1/admin/categories/<id>      Single category (any status).
POST   /api/v1/admin/categories/          Create a new category.
PUT    /api/v1/admin/categories/<id>      Update a category.
DELETE /api/v1/admin/categories/<id>      Soft-delete (is_active=False).

Security
--------
* @require_admin validates the JWT AND checks role is an admin role.
* Returns 401 if no/invalid token, 403 if role is 'customer'.
* Slug uniqueness is enforced at the service layer (409 Conflict).
"""

import logging

from flask import Blueprint, jsonify, request

from app.services.category_service import CategoryService
from app.utils.decorators import require_admin

logger = logging.getLogger(__name__)

admin_categories_bp = Blueprint("admin_categories", __name__)


# ── GET / ─────────────────────────────────────────────────────────────────────

@admin_categories_bp.get("/")
@require_admin
def list_categories():
    """
    Paginated list of ALL categories (active and inactive).

    Query parameters:
        search    — case-insensitive text search on name/slug
        is_active — true | false (optional filter)
        page      — integer, default 1
        per_page  — integer, default 20, max 100

    Response (200):
        {
            "status": "success",
            "data": [ { ... }, ... ],
            "pagination": { "page": 1, "per_page": 20, "total": 5, "pages": 1 }
        }
    """
    args = request.args

    # Pagination
    try:
        page = max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(100, max(1, int(args.get("per_page", 20))))
    except (TypeError, ValueError):
        per_page = 20

    # Filters
    search    = args.get("search", "").strip()
    is_active = args.get("is_active")  # optional: "true" / "false"

    result = CategoryService.get_all_paginated(
        page=page,
        per_page=per_page,
        search=search,
        is_active=is_active,
    )

    return jsonify({
        "status":     "success",
        "data":       [CategoryService.serialize(c) for c in result["items"]],
        "pagination": result["pagination"],
    }), 200


# ── GET /<id> ─────────────────────────────────────────────────────────────────

@admin_categories_bp.get("/<int:category_id>")
@require_admin
def get_category(category_id: int):
    """
    Return a single category by ID (active or inactive).

    Response (200): { "status": "success", "data": { ... } }
    Error    (404): { "status": "error", "message": "Category not found." }
    """
    category = CategoryService.get_by_id(category_id)
    if category is None:
        return jsonify({"status": "error", "message": "Category not found."}), 404

    return jsonify({
        "status": "success",
        "data":   CategoryService.serialize(category),
    }), 200


# ── POST / ────────────────────────────────────────────────────────────────────

@admin_categories_bp.post("/")
@require_admin
def create_category():
    """
    Create a new category.

    Request body:
        { "name": "Gold", "slug": "gold", "description": "...", "image_url": "...", "is_active": true }

    Response (201):
        { "status": "success", "message": "Category created.", "data": { ... } }

    Errors:
        400 — validation error
        401 — missing/invalid JWT
        403 — not admin
        409 — slug already exists
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    errors = CategoryService.validate(data, require_all=True)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    try:
        category = CategoryService.create(data)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409

    return jsonify({
        "status":  "success",
        "message": "Category created.",
        "data":    CategoryService.serialize(category),
    }), 201


# ── PUT /<id> ─────────────────────────────────────────────────────────────────

@admin_categories_bp.put("/<int:category_id>")
@require_admin
def update_category(category_id: int):
    """
    Update a category (partial update — only sent fields are changed).

    Response (200): { "status": "success", "message": "Category updated.", "data": { ... } }
    Errors: 400, 401, 403, 404, 409.
    """
    category = CategoryService.get_by_id(category_id)
    if category is None:
        return jsonify({"status": "error", "message": "Category not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    errors = CategoryService.validate(data, require_all=False)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    try:
        updated = CategoryService.update(category, data)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409

    return jsonify({
        "status":  "success",
        "message": "Category updated.",
        "data":    CategoryService.serialize(updated),
    }), 200


# ── DELETE /<id> ──────────────────────────────────────────────────────────────

@admin_categories_bp.delete("/<int:category_id>")
@require_admin
def delete_category(category_id: int):
    """
    Soft-delete a category (sets is_active=False).

    Products assigned to this category are NOT deleted.

    Response (200): { "status": "success", "message": "Category deactivated." }
    Errors: 401, 403, 404.
    """
    category = CategoryService.get_by_id(category_id)
    if category is None:
        return jsonify({"status": "error", "message": "Category not found."}), 404

    CategoryService.soft_delete(category)

    return jsonify({
        "status":  "success",
        "message": "Category deactivated.",
    }), 200
