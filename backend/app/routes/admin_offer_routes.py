"""
app/routes/admin_offer_routes.py

Admin endpoints for Offers, Coupons, and Banners.

All routes require a valid JWT with any admin role.

Offer Endpoints
---------------
GET    /api/v1/admin/offers/          Paginated list.
GET    /api/v1/admin/offers/<id>      Single offer.
POST   /api/v1/admin/offers/          Create.
PUT    /api/v1/admin/offers/<id>      Update.
DELETE /api/v1/admin/offers/<id>      Soft-delete.

Coupon Endpoints
----------------
GET    /api/v1/admin/coupons/         Paginated list.
GET    /api/v1/admin/coupons/<id>     Single coupon.
POST   /api/v1/admin/coupons/         Create.
PUT    /api/v1/admin/coupons/<id>     Update.
DELETE /api/v1/admin/coupons/<id>     Deactivate.

Banner Endpoints
----------------
GET    /api/v1/admin/banners/         Paginated list.
POST   /api/v1/admin/banners/         Create.
PUT    /api/v1/admin/banners/<id>     Update.
DELETE /api/v1/admin/banners/<id>     Deactivate.

Public Endpoints (registered separately)
-----------------------------------------
GET /api/v1/banners/  — active banners for frontend
POST /api/v1/coupons/validate — validate a coupon code
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.offer import Offer, Coupon, CouponUsage, Banner, DiscountType
from app.utils.decorators import require_admin

logger = logging.getLogger(__name__)

admin_offers_bp  = Blueprint("admin_offers",  __name__)
admin_coupons_bp = Blueprint("admin_coupons", __name__)
admin_banners_bp = Blueprint("admin_banners", __name__)


# ══════════════════════════════════════════════════════════════════════════════
# Serializers
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_offer(o: Offer) -> dict:
    return {
        "id":               o.id,
        "title":            o.title,
        "description":      o.description,
        "discount_type":    o.discount_type,
        "discount_value":   float(o.discount_value),
        "minimum_purchase": float(o.minimum_purchase) if o.minimum_purchase else None,
        "maximum_discount": float(o.maximum_discount) if o.maximum_discount else None,
        "start_date":       o.start_date.isoformat() if o.start_date else None,
        "end_date":         o.end_date.isoformat()   if o.end_date   else None,
        "category_id":      o.category_id,
        "is_active":        o.is_active,
        "computed_status":  o.get_computed_status(),
        "created_at":       o.created_at.isoformat() if o.created_at else None,
    }


def _serialize_coupon(c: Coupon) -> dict:
    return {
        "id":               c.id,
        "code":             c.code,
        "description":      c.description,
        "discount_type":    c.discount_type,
        "discount_value":   float(c.discount_value),
        "minimum_order":    float(c.minimum_order)    if c.minimum_order    else None,
        "maximum_discount": float(c.maximum_discount) if c.maximum_discount else None,
        "usage_limit":      c.usage_limit,
        "per_user_limit":   c.per_user_limit,
        "total_usage":      c.get_total_usage(),
        "start_date":       c.start_date.isoformat() if c.start_date else None,
        "end_date":         c.end_date.isoformat()   if c.end_date   else None,
        "is_active":        c.is_active,
        "computed_status":  c.get_computed_status(),
        "created_at":       c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_banner(b: Banner) -> dict:
    return {
        "id":               b.id,
        "title":            b.title,
        "image_url":        b.image_url,
        "mobile_image_url": b.mobile_image_url,
        "link_url":         b.link_url,
        "display_order":    b.display_order,
        "start_date":       b.start_date.isoformat() if b.start_date else None,
        "end_date":         b.end_date.isoformat()   if b.end_date   else None,
        "is_active":        b.is_active,
        "is_visible":       b.is_currently_visible(),
        "created_at":       b.created_at.isoformat() if b.created_at else None,
    }


def _parse_dt(value: str | None) -> datetime | None:
    """Parse ISO datetime string or return None."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# OFFER ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@admin_offers_bp.get("/")
@require_admin
def list_offers():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    query    = Offer.query.order_by(Offer.created_at.desc())
    pg       = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "status": "success",
        "data":   [_serialize_offer(o) for o in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_offers_bp.get("/<int:offer_id>")
@require_admin
def get_offer(offer_id: int):
    offer = db.session.get(Offer, offer_id)
    if offer is None:
        return jsonify({"status": "error", "message": "Offer not found."}), 404
    return jsonify({"status": "success", "data": _serialize_offer(offer)}), 200


@admin_offers_bp.post("/")
@require_admin
def create_offer():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    if not str(data.get("title", "")).strip():
        return jsonify({"status": "error", "message": "'title' is required."}), 400
    if not data.get("discount_type") or data["discount_type"] not in {"PERCENTAGE", "FIXED"}:
        return jsonify({"status": "error", "message": "'discount_type' must be PERCENTAGE or FIXED."}), 400
    try:
        val = float(data.get("discount_value", -1))
        if val <= 0:
            raise ValueError()
    except (TypeError, ValueError):
        return jsonify({"status": "error", "message": "'discount_value' must be a positive number."}), 400

    offer = Offer(
        title=str(data["title"]).strip(),
        description=data.get("description") or None,
        discount_type=data["discount_type"],
        discount_value=float(data["discount_value"]),
        minimum_purchase=data.get("minimum_purchase"),
        maximum_discount=data.get("maximum_discount"),
        start_date=_parse_dt(data.get("start_date")),
        end_date=_parse_dt(data.get("end_date")),
        category_id=data.get("category_id"),
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(offer)
    db.session.commit()
    return jsonify({"status": "success", "message": "Offer created.", "data": _serialize_offer(offer)}), 201


@admin_offers_bp.put("/<int:offer_id>")
@require_admin
def update_offer(offer_id: int):
    offer = db.session.get(Offer, offer_id)
    if offer is None:
        return jsonify({"status": "error", "message": "Offer not found."}), 404
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    for field in ("title", "description"):
        if field in data:
            setattr(offer, field, data[field])
    for field in ("discount_type", "minimum_purchase", "maximum_discount", "category_id", "is_active"):
        if field in data:
            setattr(offer, field, data[field])
    if "discount_value" in data:
        offer.discount_value = float(data["discount_value"])
    if "start_date" in data:
        offer.start_date = _parse_dt(data["start_date"])
    if "end_date" in data:
        offer.end_date = _parse_dt(data["end_date"])

    db.session.commit()
    return jsonify({"status": "success", "message": "Offer updated.", "data": _serialize_offer(offer)}), 200


@admin_offers_bp.delete("/<int:offer_id>")
@require_admin
def delete_offer(offer_id: int):
    offer = db.session.get(Offer, offer_id)
    if offer is None:
        return jsonify({"status": "error", "message": "Offer not found."}), 404
    offer.is_active = False
    db.session.commit()
    return jsonify({"status": "success", "message": "Offer deactivated."}), 200


# ══════════════════════════════════════════════════════════════════════════════
# COUPON ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@admin_coupons_bp.get("/")
@require_admin
def list_coupons():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    query    = Coupon.query.order_by(Coupon.created_at.desc())
    pg       = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "status": "success",
        "data":   [_serialize_coupon(c) for c in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_coupons_bp.get("/<int:coupon_id>")
@require_admin
def get_coupon(coupon_id: int):
    coupon = db.session.get(Coupon, coupon_id)
    if coupon is None:
        return jsonify({"status": "error", "message": "Coupon not found."}), 404
    return jsonify({"status": "success", "data": _serialize_coupon(coupon)}), 200


@admin_coupons_bp.post("/")
@require_admin
def create_coupon():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    code = str(data.get("code", "")).strip().upper()
    if not code:
        return jsonify({"status": "error", "message": "'code' is required."}), 400
    if Coupon.query.filter_by(code=code).first():
        return jsonify({"status": "error", "message": "Coupon code already exists."}), 409

    if not data.get("discount_type") or data["discount_type"] not in {"PERCENTAGE", "FIXED"}:
        return jsonify({"status": "error", "message": "'discount_type' must be PERCENTAGE or FIXED."}), 400
    try:
        float(data["discount_value"])
    except (TypeError, ValueError, KeyError):
        return jsonify({"status": "error", "message": "'discount_value' is required and must be a number."}), 400

    coupon = Coupon(
        code=code,
        description=data.get("description") or None,
        discount_type=data["discount_type"],
        discount_value=float(data["discount_value"]),
        minimum_order=data.get("minimum_order"),
        maximum_discount=data.get("maximum_discount"),
        usage_limit=data.get("usage_limit"),
        per_user_limit=data.get("per_user_limit", 1),
        start_date=_parse_dt(data.get("start_date")),
        end_date=_parse_dt(data.get("end_date")),
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(coupon)
    db.session.commit()
    return jsonify({"status": "success", "message": "Coupon created.", "data": _serialize_coupon(coupon)}), 201


@admin_coupons_bp.put("/<int:coupon_id>")
@require_admin
def update_coupon(coupon_id: int):
    coupon = db.session.get(Coupon, coupon_id)
    if coupon is None:
        return jsonify({"status": "error", "message": "Coupon not found."}), 404
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    if "code" in data:
        new_code = str(data["code"]).strip().upper()
        if Coupon.query.filter(Coupon.code == new_code, Coupon.id != coupon_id).first():
            return jsonify({"status": "error", "message": "Coupon code already exists."}), 409
        coupon.code = new_code

    for field in ("description", "discount_type", "minimum_order", "maximum_discount",
                  "usage_limit", "per_user_limit", "is_active"):
        if field in data:
            setattr(coupon, field, data[field])
    if "discount_value" in data:
        coupon.discount_value = float(data["discount_value"])
    if "start_date" in data:
        coupon.start_date = _parse_dt(data["start_date"])
    if "end_date" in data:
        coupon.end_date = _parse_dt(data["end_date"])

    db.session.commit()
    return jsonify({"status": "success", "message": "Coupon updated.", "data": _serialize_coupon(coupon)}), 200


@admin_coupons_bp.delete("/<int:coupon_id>")
@require_admin
def delete_coupon(coupon_id: int):
    coupon = db.session.get(Coupon, coupon_id)
    if coupon is None:
        return jsonify({"status": "error", "message": "Coupon not found."}), 404
    coupon.is_active = False
    db.session.commit()
    return jsonify({"status": "success", "message": "Coupon deactivated."}), 200


# ══════════════════════════════════════════════════════════════════════════════
# BANNER ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@admin_banners_bp.get("/")
@require_admin
def list_banners():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    pg       = Banner.query.order_by(Banner.display_order.asc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({
        "status": "success",
        "data":   [_serialize_banner(b) for b in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_banners_bp.post("/")
@require_admin
def create_banner():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400
    if not str(data.get("title", "")).strip():
        return jsonify({"status": "error", "message": "'title' is required."}), 400
    if not str(data.get("image_url", "")).strip():
        return jsonify({"status": "error", "message": "'image_url' is required."}), 400

    banner = Banner(
        title=str(data["title"]).strip(),
        image_url=str(data["image_url"]).strip(),
        mobile_image_url=data.get("mobile_image_url") or None,
        link_url=data.get("link_url") or None,
        display_order=int(data.get("display_order", 0)),
        start_date=_parse_dt(data.get("start_date")),
        end_date=_parse_dt(data.get("end_date")),
        is_active=bool(data.get("is_active", True)),
    )
    db.session.add(banner)
    db.session.commit()
    return jsonify({"status": "success", "message": "Banner created.", "data": _serialize_banner(banner)}), 201


@admin_banners_bp.put("/<int:banner_id>")
@require_admin
def update_banner(banner_id: int):
    banner = db.session.get(Banner, banner_id)
    if banner is None:
        return jsonify({"status": "error", "message": "Banner not found."}), 404
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    for field in ("title", "image_url", "mobile_image_url", "link_url", "is_active"):
        if field in data:
            setattr(banner, field, data[field])
    if "display_order" in data:
        banner.display_order = int(data["display_order"])
    if "start_date" in data:
        banner.start_date = _parse_dt(data["start_date"])
    if "end_date" in data:
        banner.end_date = _parse_dt(data["end_date"])

    db.session.commit()
    return jsonify({"status": "success", "message": "Banner updated.", "data": _serialize_banner(banner)}), 200


@admin_banners_bp.delete("/<int:banner_id>")
@require_admin
def delete_banner(banner_id: int):
    banner = db.session.get(Banner, banner_id)
    if banner is None:
        return jsonify({"status": "error", "message": "Banner not found."}), 404
    banner.is_active = False
    db.session.commit()
    return jsonify({"status": "success", "message": "Banner deactivated."}), 200
