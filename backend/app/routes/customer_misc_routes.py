"""
app/routes/customer_misc_routes.py

Miscellaneous public and customer endpoints:
- Gold/Silver Rates
- Offers
- Coupons (validation)
- Banners
- Contact
- Store Visits
- Notifications
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.extensions import db
from app.models.metal_rate import MetalRate
from app.models.offer import Offer, Coupon, Banner
from app.models.misc import ContactMessage, Notification
from app.models.store_visit import StoreVisit
from app.utils.decorators import require_auth

logger = logging.getLogger(__name__)

rates_bp         = Blueprint("customer_rates", __name__)
offers_bp        = Blueprint("customer_offers", __name__)
coupons_bp       = Blueprint("customer_coupons", __name__)
banners_bp       = Blueprint("customer_banners", __name__)
contact_bp       = Blueprint("customer_contact", __name__)
store_visits_bp  = Blueprint("customer_store_visits", __name__)
notifications_bp = Blueprint("customer_notifications", __name__)


# ══════════════════════════════════════════════════════════════════════════════
# GOLD RATE
# ══════════════════════════════════════════════════════════════════════════════

@rates_bp.get("/")
def get_metal_rates():
    """GET /api/v1/gold-price"""
    rates = MetalRate.query.filter_by(is_active=True).all()
    
    data = []
    for r in rates:
        data.append({
            "metal_type": r.metal_type,
            "purity":     r.purity,
            "price":      float(r.rate_per_gram * 10), # Typically requested per 10g in UI
            "unit":       "10g",
            "updated_at": r.updated_at.isoformat() if r.updated_at else None,
        })
        
    return jsonify({"status": "success", "data": data}), 200


# ══════════════════════════════════════════════════════════════════════════════
# OFFERS
# ══════════════════════════════════════════════════════════════════════════════

@offers_bp.get("/")
def get_active_offers():
    """GET /api/v1/offers"""
    now = datetime.now(timezone.utc)
    # Get active offers that have started and not yet ended
    offers = Offer.query.filter(
        Offer.is_active == True,
        (Offer.start_date == None) | (Offer.start_date <= now),
        (Offer.end_date == None) | (Offer.end_date > now)
    ).all()
    
    data = []
    for o in offers:
        data.append({
            "id":               o.id,
            "title":            o.title,
            "description":      o.description,
            "discount_type":    o.discount_type,
            "discount_value":   float(o.discount_value),
            "minimum_purchase": float(o.minimum_purchase) if o.minimum_purchase else None,
            "maximum_discount": float(o.maximum_discount) if o.maximum_discount else None,
            "end_date":         o.end_date.isoformat() if o.end_date else None,
        })
        
    return jsonify({"status": "success", "data": data}), 200


# ══════════════════════════════════════════════════════════════════════════════
# COUPONS
# ══════════════════════════════════════════════════════════════════════════════

@coupons_bp.post("/validate")
@require_auth
def validate_coupon():
    """
    POST /api/v1/coupons/validate
    { "code": "SUMMER50", "cart_total": 5000 }
    """
    data = request.get_json(silent=True)
    if not data or not data.get("code"):
        return jsonify({"status": "error", "message": "Coupon code is required."}), 400
        
    code = str(data["code"]).strip().upper()
    cart_total = float(data.get("cart_total", 0))
    
    coupon = Coupon.query.filter_by(code=code).first()
    if not coupon:
        return jsonify({"status": "error", "message": "Invalid coupon code."}), 404
        
    if coupon.get_computed_status() != "ACTIVE":
        return jsonify({"status": "error", "message": "Coupon is expired or inactive."}), 400
        
    if coupon.minimum_order and cart_total < float(coupon.minimum_order):
        return jsonify({
            "status": "error", 
            "message": f"Minimum order amount of {float(coupon.minimum_order)} required for this coupon."
        }), 400
        
    # Valid coupon
    return jsonify({
        "status": "success",
        "message": "Coupon applied successfully.",
        "data": {
            "code": coupon.code,
            "discount_type": coupon.discount_type,
            "discount_value": float(coupon.discount_value),
            "maximum_discount": float(coupon.maximum_discount) if coupon.maximum_discount else None
        }
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
# BANNERS
# ══════════════════════════════════════════════════════════════════════════════

@banners_bp.get("/")
def get_banners():
    """GET /api/v1/banners"""
    now = datetime.now(timezone.utc)
    banners = Banner.query.filter(
        Banner.is_active == True,
        (Banner.start_date == None) | (Banner.start_date <= now),
        (Banner.end_date == None) | (Banner.end_date > now)
    ).order_by(Banner.display_order.asc()).all()
    
    data = []
    for b in banners:
        data.append({
            "id":               b.id,
            "title":            b.title,
            "image_url":        b.image_url,
            "mobile_image_url": b.mobile_image_url,
            "link_url":         b.link_url,
        })
        
    return jsonify({"status": "success", "data": data}), 200


# ══════════════════════════════════════════════════════════════════════════════
# CONTACT
# ══════════════════════════════════════════════════════════════════════════════

@contact_bp.post("/")
def submit_contact():
    """POST /api/v1/contact"""
    data = request.get_json(silent=True)
    if not data or not data.get("name") or not data.get("message"):
        return jsonify({"status": "error", "message": "Name and message are required."}), 400
        
    # Optional JWT parsing to link to user if logged in
    from flask_jwt_extended import verify_jwt_in_request
    user_id = None
    try:
        verify_jwt_in_request(optional=True)
        identity = get_jwt_identity()
        if identity:
            user_id = int(identity)
    except Exception:
        pass

    msg = ContactMessage(
        user_id=user_id,
        name=str(data["name"]).strip(),
        email=data.get("email"),
        phone=data.get("phone"),
        subject=data.get("subject"),
        message=str(data["message"]).strip()
    )
    db.session.add(msg)
    db.session.commit()
    
    return jsonify({"status": "success", "message": "Message sent successfully."}), 201


# ══════════════════════════════════════════════════════════════════════════════
# STORE VISITS
# ══════════════════════════════════════════════════════════════════════════════

@store_visits_bp.post("/")
@require_auth
def book_visit():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True)
    if not data or not data.get("visit_date") or not data.get("contact_name") or not data.get("contact_phone"):
        return jsonify({"status": "error", "message": "visit_date, contact_name, and contact_phone are required."}), 400
        
    try:
        visit_date = datetime.strptime(data["visit_date"], "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"status": "error", "message": "visit_date must be YYYY-MM-DD."}), 400

    visit = StoreVisit(
        user_id=user_id,
        contact_name=str(data["contact_name"]).strip(),
        contact_phone=str(data["contact_phone"]).strip(),
        contact_email=data.get("contact_email"),
        visit_date=visit_date,
        visit_time=data.get("visit_time"),
        purpose=data.get("purpose"),
        notes=data.get("notes")
    )
    db.session.add(visit)
    db.session.commit()
    
    return jsonify({"status": "success", "message": "Store visit booked successfully."}), 201


@store_visits_bp.get("/")
@require_auth
def get_visits():
    user_id = int(get_jwt_identity())
    visits = StoreVisit.query.filter_by(user_id=user_id).order_by(StoreVisit.visit_date.desc()).all()
    
    data = []
    for v in visits:
        data.append({
            "id":            v.id,
            "visit_date":    v.visit_date.isoformat(),
            "visit_time":    v.visit_time,
            "purpose":       v.purpose,
            "status":        v.status,
            "created_at":    v.created_at.isoformat() if v.created_at else None,
        })
    return jsonify({"status": "success", "data": data}), 200


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

@notifications_bp.get("/")
@require_auth
def get_notifications():
    user_id = int(get_jwt_identity())
    notifs = Notification.query.filter_by(user_id=user_id).order_by(Notification.created_at.desc()).limit(50).all()
    
    data = []
    for n in notifs:
        data.append({
            "id":                n.id,
            "title":             n.title,
            "message":           n.message,
            "notification_type": n.notification_type,
            "is_read":           n.is_read,
            "created_at":        n.created_at.isoformat() if n.created_at else None,
        })
    return jsonify({"status": "success", "data": data}), 200


@notifications_bp.put("/<int:notif_id>/read")
@require_auth
def mark_notification_read(notif_id: int):
    user_id = int(get_jwt_identity())
    notif = Notification.query.filter_by(id=notif_id, user_id=user_id).first()
    if not notif:
        return jsonify({"status": "error", "message": "Notification not found."}), 404
        
    notif.is_read = True
    db.session.commit()
    return jsonify({"status": "success", "message": "Notification marked as read."}), 200
