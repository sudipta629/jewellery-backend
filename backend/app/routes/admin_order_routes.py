"""
app/routes/admin_order_routes.py

Admin endpoints for order management.

All routes require a valid JWT with any admin role.
Status updates are available to all admin roles.

Endpoints
---------
GET /api/v1/admin/orders/               Paginated order list with filters.
GET /api/v1/admin/orders/<id>           Full order detail including items + history.
PUT /api/v1/admin/orders/<id>/status    Update order status.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.services.order_service import OrderService, VALID_TRANSITIONS
from app.models.order import OrderStatus
from app.utils.decorators import require_admin

logger = logging.getLogger(__name__)

admin_orders_bp = Blueprint("admin_orders", __name__)


# ── GET / ─────────────────────────────────────────────────────────────────────

@admin_orders_bp.get("/")
@require_admin
def list_orders():
    """
    Paginated, filterable order list for the admin panel.

    Query parameters:
        search         — text search on order_number, customer name, phone
        order_number   — exact/partial match
        user_id        — integer (filter by customer)
        order_status   — PLACED | CONFIRMED | CRAFTING | HALLMARKING |
                         SHIPPED | DELIVERED | CANCELLED | RETURNED | REFUNDED
        payment_status — PENDING | PAID | FAILED | REFUNDED
        date_from      — ISO date (YYYY-MM-DD)
        date_to        — ISO date (YYYY-MM-DD)
        page           — integer, default 1
        per_page       — integer, default 20, max 100

    Response (200):
        { "status": "success", "data": [...], "pagination": {...} }
    """
    args = request.args
    params = {
        "search":         args.get("search", "").strip(),
        "order_number":   args.get("order_number", "").strip(),
        "user_id":        args.get("user_id"),
        "order_status":   args.get("order_status", "").strip() or None,
        "payment_status": args.get("payment_status", "").strip() or None,
        "date_from":      args.get("date_from"),
        "date_to":        args.get("date_to"),
        "page":           args.get("page", 1),
        "per_page":       args.get("per_page", 20),
    }

    result = OrderService.get_orders_paginated(params)

    return jsonify({
        "status":     "success",
        "data":       [OrderService.serialize(o, include_items=False) for o in result["items"]],
        "pagination": result["pagination"],
    }), 200


# ── GET /<id> ─────────────────────────────────────────────────────────────────

@admin_orders_bp.get("/<int:order_id>")
@require_admin
def get_order(order_id: int):
    """
    Return full order details including items and status history.

    Response (200):
        { "status": "success", "data": { ... order with items + history ... } }
    Error (404): order not found.
    """
    order = OrderService.get_order_by_id(order_id)
    if order is None:
        return jsonify({"status": "error", "message": "Order not found."}), 404

    return jsonify({
        "status": "success",
        "data":   OrderService.serialize(order, include_items=True, include_history=True),
    }), 200


# ── PUT /<id>/status ──────────────────────────────────────────────────────────

@admin_orders_bp.put("/<int:order_id>/status")
@require_admin
def update_order_status(order_id: int):
    """
    Update the status of an order.

    Valid transitions are enforced server-side.
    Inventory is automatically adjusted when order is CONFIRMED or CANCELLED.

    Request body:
        {
            "status": "CONFIRMED",        (required)
            "notes":  "Verified payment"  (optional)
        }

    Valid status values:
        PLACED, CONFIRMED, CRAFTING, HALLMARKING, SHIPPED,
        DELIVERED, CANCELLED, RETURNED, REFUNDED

    Response (200):
        { "status": "success", "message": "Order status updated.", "data": { ... } }

    Errors:
        400 — missing status field
        404 — order not found
        409 — invalid status transition
        422 — insufficient stock (on CONFIRMED)
    """
    order = OrderService.get_order_by_id(order_id)
    if order is None:
        return jsonify({"status": "error", "message": "Order not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    new_status = str(data.get("status", "")).strip()
    if not new_status:
        return jsonify({"status": "error", "message": "'status' is required."}), 400

    staff_id = int(get_jwt_identity())
    notes    = data.get("notes") or None

    try:
        updated = OrderService.update_status(
            order=order,
            new_status=new_status,
            changed_by=staff_id,
            notes=notes,
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 409

    return jsonify({
        "status":  "success",
        "message": "Order status updated.",
        "data":    OrderService.serialize(updated, include_items=True, include_history=True),
    }), 200
