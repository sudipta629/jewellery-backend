"""
app/routes/product_routes.py

Public product endpoints — no authentication required.

Endpoints
---------
GET /api/v1/products/           Paginated, filtered, sorted product list.
GET /api/v1/products/<id>       Full product detail.

Query parameters (GET /products/)
----------------------------------
search      — case-insensitive text search across name, SKU, slug, metal_type, purity
category_id — integer
metal_type  — string (case-insensitive)
purity      — string (case-insensitive)
is_featured — true | false
is_new      — true | false
stock_only  — true | false  (only in-stock products)
min_weight  — float (gross_weight >=)
max_weight  — float (gross_weight <=)
page        — integer, default 1
per_page    — integer, default 20, max 100
sort        — newest (default) | oldest | name_asc | name_desc
              weight_asc | weight_desc
"""

import logging

from flask import Blueprint, jsonify, request

from app.services.product_service import ProductService, VALID_SORTS

logger = logging.getLogger(__name__)

products_bp = Blueprint("products", __name__)


def _parse_bool(value: str | None) -> bool | None:
    """Convert query-string boolean strings to Python bool."""
    if value is None:
        return None
    return str(value).lower() in ("true", "1", "yes")


def _build_params() -> dict:
    """Extract and lightly coerce all query parameters for product filtering."""
    args = request.args
    return {
        "search":      args.get("search",      "").strip(),
        "category_id": args.get("category_id"),
        "metal_type":  args.get("metal_type",  "").strip(),
        "purity":      args.get("purity",      "").strip(),
        "is_featured": _parse_bool(args.get("is_featured")),
        "is_new":      _parse_bool(args.get("is_new")),
        "stock_only":  _parse_bool(args.get("stock_only")),
        "min_weight":  args.get("min_weight"),
        "max_weight":  args.get("max_weight"),
        "page":        args.get("page",     1),
        "per_page":    args.get("per_page", 20),
        "sort":        args.get("sort",     "newest"),
    }


@products_bp.get("/")
def list_products():
    """
    Paginated, filterable, sortable public product listing.

    Only active products are returned.

    Response (200):
        {
            "status": "success",
            "data": [ { ... }, ... ],
            "pagination": {
                "page": 1, "per_page": 20, "total": 100,
                "pages": 5, "has_next": true, "has_prev": false
            }
        }
    """
    params = _build_params()

    # Validate sort
    sort_key = params.get("sort", "newest")
    if sort_key not in VALID_SORTS:
        return jsonify({
            "status":  "error",
            "message": f"Invalid sort value. Allowed: {', '.join(VALID_SORTS.keys())}.",
        }), 400

    result = ProductService.get_products_paginated(params)

    return jsonify({
        "status":     "success",
        "data":       [ProductService.serialize(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200


@products_bp.get("/<int:product_id>")
def get_product(product_id: int):
    """
    Return full details of one active product.

    Response (200): { "status": "success", "data": { ... } }
    Error   (404):  { "status": "error",   "message": "Product not found." }
    """
    product = ProductService.get_active_product_by_id(product_id)
    if product is None:
        return jsonify({
            "status":  "error",
            "message": "Product not found.",
        }), 404

    return jsonify({
        "status": "success",
        "data":   ProductService.serialize(product),
    }), 200


@products_bp.get("/search")
def search_products():
    """
    GET /api/v1/products/search?q=gold+ring
    """
    # map 'q' to 'search' for the service
    params = _build_params()
    if request.args.get("q"):
        params["search"] = request.args.get("q").strip()
    
    result = ProductService.get_products_paginated(params)
    return jsonify({
        "status":     "success",
        "data":       [ProductService.serialize(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200


@products_bp.get("/featured")
def featured_products():
    """GET /api/v1/products/featured"""
    params = _build_params()
    params["is_featured"] = True
    result = ProductService.get_products_paginated(params)
    return jsonify({
        "status":     "success",
        "data":       [ProductService.serialize(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200


@products_bp.get("/new-arrivals")
def new_arrivals_products():
    """GET /api/v1/products/new-arrivals"""
    params = _build_params()
    params["is_new"] = True
    result = ProductService.get_products_paginated(params)
    return jsonify({
        "status":     "success",
        "data":       [ProductService.serialize(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200


@products_bp.get("/popular")
def popular_products():
    """
    GET /api/v1/products/popular
    Placeholder: returns newest items or items sorted by views/sales when implemented.
    Currently just returns a default sorted list.
    """
    params = _build_params()
    result = ProductService.get_products_paginated(params)
    return jsonify({
        "status":     "success",
        "data":       [ProductService.serialize(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200


@products_bp.get("/<int:product_id>/related")
def related_products(product_id: int):
    """
    GET /api/v1/products/<id>/related
    Returns products in the same category or metal type.
    """
    product = ProductService.get_active_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    params = _build_params()
    params["category_id"] = product.category_id
    
    # We could filter out the current product itself in the service, 
    # but for simplicity we'll just fetch and remove it here if present.
    result = ProductService.get_products_paginated(params)
    
    items = [ProductService.serialize(p) for p in result["items"] if p.id != product_id]
    
    return jsonify({
        "status":     "success",
        "data":       items,
        "pagination": result["pagination"],
    }), 200
