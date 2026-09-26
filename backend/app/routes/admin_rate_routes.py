"""
app/routes/admin_rate_routes.py

Admin endpoints for gold/silver/platinum rate management.

All routes require a valid JWT with any admin role.
Rate updates (POST/PUT) are restricted to admin, super_admin, and inventory_staff.

Endpoints
---------
GET  /api/v1/admin/rates/           Current active rates (all metals).
GET  /api/v1/admin/rates/history    Paginated rate history.
POST /api/v1/admin/rates/           Set a new rate (deactivates current active rate).
PUT  /api/v1/admin/rates/<id>       Minor correction to an existing rate record.

Public
------
GET /api/v1/rates/   Public endpoint to get current rates for frontend display.
"""

import logging
from datetime import date

from flask import Blueprint, jsonify, request

from app.services.pricing_service import PricingService
from app.utils.decorators import (
    require_admin,
    require_role,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_INVENTORY_STAFF,
)
from app.models.metal_rate import MetalRate

logger = logging.getLogger(__name__)

admin_rates_bp = Blueprint("admin_rates", __name__)


# ── GET / — current active rates ──────────────────────────────────────────────

@admin_rates_bp.get("/")
@require_admin
def list_current_rates():
    """
    Return all currently active metal rates.

    Response (200):
        {
            "status": "success",
            "data": [
                { "id": 1, "metal_type": "gold", "purity": "22K", "rate_per_gram": 5700.00, ... },
                ...
            ]
        }
    """
    rates = MetalRate.query.filter_by(is_active=True).order_by(
        MetalRate.metal_type.asc(),
        MetalRate.purity.asc(),
    ).all()

    return jsonify({
        "status": "success",
        "data":   [PricingService.serialize_rate(r) for r in rates],
    }), 200


# ── GET /history — paginated rate history ─────────────────────────────────────

@admin_rates_bp.get("/history")
@require_admin
def rate_history():
    """
    Paginated rate history for all metals (or filtered by metal_type/purity).

    Query parameters:
        metal_type — optional filter
        purity     — optional filter
        page       — integer, default 1
        per_page   — integer, default 20, max 100

    Response (200):
        { "status": "success", "data": [...], "pagination": {...} }
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

    metal_type = args.get("metal_type", "").strip() or None
    purity     = args.get("purity",     "").strip() or None

    result = PricingService.get_rate_history(
        metal_type=metal_type,
        purity=purity,
        page=page,
        per_page=per_page,
    )

    return jsonify({
        "status":     "success",
        "data":       [PricingService.serialize_rate(r) for r in result["items"]],
        "pagination": result["pagination"],
    }), 200


# ── POST / — set a new rate ───────────────────────────────────────────────────

@admin_rates_bp.post("/")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_INVENTORY_STAFF)
def set_rate():
    """
    Set a new metal rate.

    This deactivates the current active rate for the same metal+purity
    and inserts a fresh record.

    Request body:
        {
            "metal_type":    "gold",      (required)
            "purity":        "22K",       (optional)
            "rate_per_gram": 5700.00,     (required, must be > 0)
            "effective_date": "2026-09-24", (optional, defaults to today)
            "source":        "manual"     (optional)
        }

    Response (201):
        { "status": "success", "message": "Rate updated.", "data": { ... } }

    Errors:
        400 — validation error
        401 — missing/invalid JWT
        403 — not admin
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    errors = PricingService.validate_rate_data(data, require_all=True)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    # Parse optional effective_date
    effective_date = None
    if data.get("effective_date"):
        try:
            effective_date = date.fromisoformat(str(data["effective_date"]))
        except ValueError:
            return jsonify({
                "status":  "error",
                "message": "'effective_date' must be a valid ISO date (YYYY-MM-DD).",
            }), 400

    try:
        rate = PricingService.set_rate(
            metal_type=str(data["metal_type"]).strip(),
            purity=data.get("purity") or None,
            rate_per_gram=float(data["rate_per_gram"]),
            effective_date=effective_date,
            source=str(data.get("source", "manual")).strip(),
        )
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({
        "status":  "success",
        "message": "Rate updated.",
        "data":    PricingService.serialize_rate(rate),
    }), 201


# ── PUT /<id> — minor correction ──────────────────────────────────────────────

@admin_rates_bp.put("/<int:rate_id>")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def update_rate(rate_id: int):
    """
    Minor correction to an existing rate record.

    NOTE: For normal rate updates use POST / instead.
    This endpoint is for correcting mistakes on the current record.

    Updateable fields: rate_per_gram, source, effective_date.

    Response (200): { "status": "success", "message": "Rate corrected.", "data": { ... } }
    Errors: 400, 401, 403, 404.
    """
    rate = MetalRate.query.get(rate_id)
    if rate is None:
        return jsonify({"status": "error", "message": "Rate not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    errors = PricingService.validate_rate_data(data, require_all=False)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    # Parse effective_date if supplied
    if "effective_date" in data and data["effective_date"]:
        try:
            data["effective_date"] = date.fromisoformat(str(data["effective_date"]))
        except ValueError:
            return jsonify({
                "status":  "error",
                "message": "'effective_date' must be a valid ISO date (YYYY-MM-DD).",
            }), 400

    try:
        updated = PricingService.update_rate(rate, data)
    except ValueError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 400

    return jsonify({
        "status":  "success",
        "message": "Rate corrected.",
        "data":    PricingService.serialize_rate(updated),
    }), 200
