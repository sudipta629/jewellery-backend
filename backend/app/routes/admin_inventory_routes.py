"""
app/routes/admin_inventory_routes.py

Admin endpoints for inventory management.

All routes require a valid JWT with any admin role.
Stock adjustments require admin, super_admin, or inventory_staff role.

Endpoints
---------
GET  /api/v1/admin/inventory/                      Paginated inventory list.
GET  /api/v1/admin/inventory/<product_id>          Inventory status for one product.
POST /api/v1/admin/inventory/<product_id>/adjust   Adjust stock for a product.
GET  /api/v1/admin/inventory/<product_id>/history  Transaction history for one product.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.services.inventory_service import InventoryService
from app.services.product_service import ProductService
from app.utils.decorators import (
    require_admin,
    require_role,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_INVENTORY_STAFF,
    ROLE_SALES_STAFF,
)

logger = logging.getLogger(__name__)

admin_inventory_bp = Blueprint("admin_inventory", __name__)


# ── GET / ─────────────────────────────────────────────────────────────────────

@admin_inventory_bp.get("/")
@require_admin
def list_inventory():
    """
    Paginated list of all products with their stock status.

    Query parameters:
        search       — filter on name / SKU
        stock_status — IN_STOCK | LOW_STOCK | OUT_OF_STOCK
        page         — integer, default 1
        per_page     — integer, default 20, max 100

    Response (200):
        {
            "status": "success",
            "data": [ { "product_id": 1, "sku": "...", "stock_quantity": 10, ... }, ... ],
            "pagination": { ... }
        }
    """
    args = request.args

    try:
        page = max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(100, max(1, int(args.get("per_page", 20))))
    except (TypeError, ValueError):
        per_page = 20

    search       = args.get("search", "").strip()
    stock_status = args.get("stock_status", "").strip() or None

    result = InventoryService.get_inventory_paginated(
        page=page,
        per_page=per_page,
        search=search,
        stock_status=stock_status,
    )

    return jsonify({
        "status":     "success",
        "data":       [InventoryService.serialize_inventory_status(p) for p in result["items"]],
        "pagination": result["pagination"],
    }), 200


# ── GET /<product_id> ─────────────────────────────────────────────────────────

@admin_inventory_bp.get("/<int:product_id>")
@require_admin
def get_product_inventory(product_id: int):
    """
    Return inventory status for one product.

    Response (200):
        { "status": "success", "data": { "product_id": 1, "stock_quantity": 5, ... } }
    Error (404): product not found.
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    return jsonify({
        "status": "success",
        "data":   InventoryService.serialize_inventory_status(product),
    }), 200


# ── POST /<product_id>/adjust ─────────────────────────────────────────────────

@admin_inventory_bp.post("/<int:product_id>/adjust")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_STAFF)
def adjust_inventory(product_id: int):
    """
    Adjust the stock quantity for a product.

    Request body:
        {
            "transaction_type": "STOCK_IN",   (required)
            "quantity":         100,           (required, non-zero)
            "notes":            "Received from supplier"   (optional)
        }

    Allowed transaction types: STOCK_IN, STOCK_OUT, ADJUSTMENT.
    (SALE and RETURN are created automatically by the order system.)

    Response (200):
        { "status": "success", "message": "Stock adjusted.", "data": { ... } }

    Errors:
        400 — validation error
        404 — product not found
        422 — would result in negative stock
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    # Restrict manual types to STOCK_IN, STOCK_OUT, ADJUSTMENT
    allowed_manual = {"STOCK_IN", "STOCK_OUT", "ADJUSTMENT"}
    tx_type = str(data.get("transaction_type", "")).strip()
    if tx_type and tx_type not in allowed_manual:
        return jsonify({
            "status":  "error",
            "message": f"Manual adjustment only allows: {', '.join(sorted(allowed_manual))}. "
                       f"SALE and RETURN are managed by the order system.",
        }), 400

    errors = InventoryService.validate_adjustment(data)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    staff_id = int(get_jwt_identity())

    try:
        tx = InventoryService.adjust_stock(
            product=product,
            transaction_type=data["transaction_type"],
            quantity=int(data["quantity"]),
            notes=data.get("notes") or None,
            performed_by_id=staff_id,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 422

    return jsonify({
        "status":  "success",
        "message": "Stock adjusted.",
        "data":    InventoryService.serialize_transaction(tx),
    }), 200


# ── GET /<product_id>/history ─────────────────────────────────────────────────

@admin_inventory_bp.get("/<int:product_id>/history")
@require_admin
def transaction_history(product_id: int):
    """
    Paginated transaction history for a product.

    Query parameters:
        page     — integer, default 1
        per_page — integer, default 20, max 100

    Response (200):
        { "status": "success", "data": [...], "pagination": {...} }
    Error (404): product not found.
    """
    product = ProductService.get_product_by_id(product_id)
    if product is None:
        return jsonify({"status": "error", "message": "Product not found."}), 404

    args = request.args
    try:
        page = max(1, int(args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1
    try:
        per_page = min(100, max(1, int(args.get("per_page", 20))))
    except (TypeError, ValueError):
        per_page = 20

    result = InventoryService.get_product_transaction_history(
        product_id=product_id,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "status":     "success",
        "data":       [InventoryService.serialize_transaction(tx) for tx in result["items"]],
        "pagination": result["pagination"],
    }), 200
