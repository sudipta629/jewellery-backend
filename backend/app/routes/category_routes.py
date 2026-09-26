"""
app/routes/category_routes.py

Public category endpoints — no authentication required.

Endpoints
---------
GET /api/v1/categories/        List all active categories.
GET /api/v1/categories/<id>    Return one active category.
"""

import logging

from flask import Blueprint, jsonify

from app.services.category_service import CategoryService

logger = logging.getLogger(__name__)

categories_bp = Blueprint("categories", __name__)


@categories_bp.get("/")
def list_categories():
    """
    Return all active categories for the public storefront.

    Response (200):
        { "status": "success", "data": [ { ... }, ... ] }
    """
    categories = CategoryService.get_active_categories()
    return jsonify({
        "status": "success",
        "data":   [CategoryService.serialize(c) for c in categories],
    }), 200


@categories_bp.get("/<int:category_id>")
def get_category(category_id: int):
    """
    Return one active category by ID.

    Response (200): { "status": "success", "data": { ... } }
    Error (404):    { "status": "error",   "message": "Category not found." }
    """
    category = CategoryService.get_active_by_id(category_id)
    if category is None:
        return jsonify({
            "status":  "error",
            "message": "Category not found.",
        }), 404

    return jsonify({
        "status": "success",
        "data":   CategoryService.serialize(category),
    }), 200


@categories_bp.get("/<int:category_id>/products")
def get_category_products(category_id: int):
    """
    GET /api/v1/categories/<id>/products
    Return paginated products for a category.
    """
    category = CategoryService.get_active_by_id(category_id)
    if category is None:
        return jsonify({"status": "error", "message": "Category not found."}), 404

    from app.services.product_service import ProductService
    from flask import request

    params = {
        "category_id": category_id,
        "page":        request.args.get("page", 1),
        "per_page":    request.args.get("per_page", 20),
        "sort":        request.args.get("sort", "newest"),
    }
    
    result = ProductService.get_products_paginated(params)
    return jsonify({
        "status":     "success",
        "data":       [ProductService.serialize(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200
