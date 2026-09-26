"""
app/routes/admin_misc_routes.py

Admin routes for:
- Payments          GET /api/v1/admin/payments/, GET /<id>, PUT /<id>/status
- Invoices          GET /api/v1/admin/invoices/, GET /<id>
- Store Visits      GET /api/v1/admin/store-visits/, GET /<id>, PUT /<id>/status
- Chat              GET/POST /api/v1/admin/chat/conversations/
- Notifications     POST /api/v1/admin/notifications/
- Staff Management  GET/POST/PUT/DELETE /api/v1/admin/staff/
- Settings          GET/PUT /api/v1/admin/settings/
- Contact Messages  GET /api/v1/admin/contact-messages/, GET /<id>, PUT /<id>/status
- Reports           GET /api/v1/admin/reports/*
- Dashboard         GET /api/v1/admin/dashboard
"""

import logging
from datetime import datetime, timezone, timedelta

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, get_jwt
from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.product import Product
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.invoice import Invoice, PurityCertificate
from app.models.store_visit import StoreVisit, VisitStatus
from app.models.chat import Conversation, Message, MessageType, ConversationParticipant
from app.models.misc import Notification, StoreSettings, ContactMessage, ContactStatus
from app.models.kyc import KYC, KYCStatus
from app.services.order_service import OrderService
from app.utils.decorators import (
    require_admin,
    require_auth,
    require_super_admin,
    require_role,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_SALES_STAFF,
    ROLE_INVENTORY_STAFF,
)

logger = logging.getLogger(__name__)

# ── Blueprints ─────────────────────────────────────────────────────────────────
admin_payments_bp      = Blueprint("admin_payments",       __name__)
admin_invoices_bp      = Blueprint("admin_invoices",       __name__)
admin_store_visits_bp  = Blueprint("admin_store_visits",   __name__)
admin_chat_bp          = Blueprint("admin_chat",           __name__)
admin_notifications_bp = Blueprint("admin_notifications",  __name__)
admin_staff_bp         = Blueprint("admin_staff",          __name__)
admin_settings_bp      = Blueprint("admin_settings",       __name__)
admin_contact_bp       = Blueprint("admin_contact",        __name__)
admin_reports_bp       = Blueprint("admin_reports",        __name__)
admin_dashboard_bp     = Blueprint("admin_dashboard",      __name__)


# ══════════════════════════════════════════════════════════════════════════════
# PAYMENTS
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_payment(p: Payment) -> dict:
    return {
        "id":             p.id,
        "order_id":       p.order_id,
        "user_id":        p.user_id,
        "payment_method": p.payment_method,
        "transaction_id": p.transaction_id,
        "gateway":        p.gateway,
        "amount":         float(p.amount),
        "status":         p.status,
        "paid_at":        p.paid_at.isoformat() if p.paid_at else None,
        "created_at":     p.created_at.isoformat() if p.created_at else None,
    }


@admin_payments_bp.get("/")
@require_admin
def list_payments():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    status   = request.args.get("status") or None
    query    = Payment.query
    if status:
        query = query.filter(Payment.status == status)
    query = query.order_by(Payment.created_at.desc())
    pg    = query.paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        "status": "success",
        "data":   [_serialize_payment(p) for p in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_payments_bp.get("/<int:payment_id>")
@require_admin
def get_payment(payment_id: int):
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        return jsonify({"status": "error", "message": "Payment not found."}), 404
    return jsonify({"status": "success", "data": _serialize_payment(payment)}), 200


@admin_payments_bp.put("/<int:payment_id>/status")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def update_payment_status(payment_id: int):
    """
    Manually update a payment status.

    CRITICAL: In production this should only be called by verified webhooks.
    Never trust payment status updates from the frontend directly.
    """
    payment = db.session.get(Payment, payment_id)
    if payment is None:
        return jsonify({"status": "error", "message": "Payment not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    new_status = str(data.get("status", "")).strip()
    valid_statuses = {s.value for s in PaymentStatus}
    if new_status not in valid_statuses:
        return jsonify({
            "status":  "error",
            "message": f"Invalid status. Allowed: {', '.join(valid_statuses)}.",
        }), 400

    payment.status = new_status
    if new_status == PaymentStatus.SUCCESS and not payment.paid_at:
        payment.paid_at = datetime.now(timezone.utc)
    db.session.commit()

    return jsonify({"status": "success", "message": "Payment status updated.", "data": _serialize_payment(payment)}), 200


# ══════════════════════════════════════════════════════════════════════════════
# INVOICES
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_invoice(inv: Invoice) -> dict:
    return {
        "id":             inv.id,
        "invoice_number": inv.invoice_number,
        "order_id":       inv.order_id,
        "user_id":        inv.user_id,
        "subtotal":       float(inv.subtotal),
        "making_charges": float(inv.making_charges),
        "stone_charges":  float(inv.stone_charges),
        "gst_amount":     float(inv.gst_amount),
        "discount_amount":float(inv.discount_amount),
        "total_amount":   float(inv.total_amount),
        "pdf_url":        inv.pdf_url,
        "created_at":     inv.created_at.isoformat() if inv.created_at else None,
    }


@admin_invoices_bp.get("/")
@require_admin
def list_invoices():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    pg       = Invoice.query.order_by(Invoice.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({
        "status": "success",
        "data":   [_serialize_invoice(inv) for inv in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_invoices_bp.get("/<int:invoice_id>")
@require_admin
def get_invoice(invoice_id: int):
    inv = db.session.get(Invoice, invoice_id)
    if inv is None:
        return jsonify({"status": "error", "message": "Invoice not found."}), 404
    return jsonify({"status": "success", "data": _serialize_invoice(inv)}), 200


# ══════════════════════════════════════════════════════════════════════════════
# STORE VISITS
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_visit(v: StoreVisit) -> dict:
    return {
        "id":            v.id,
        "user_id":       v.user_id,
        "contact_name":  v.contact_name,
        "contact_phone": v.contact_phone,
        "contact_email": v.contact_email,
        "visit_date":    v.visit_date.isoformat() if v.visit_date else None,
        "visit_time":    v.visit_time,
        "purpose":       v.purpose,
        "status":        v.status,
        "notes":         v.notes,
        "admin_notes":   v.admin_notes,
        "created_at":    v.created_at.isoformat() if v.created_at else None,
    }


@admin_store_visits_bp.get("/")
@require_admin
def list_store_visits():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    status   = request.args.get("status") or None
    query    = StoreVisit.query
    if status:
        query = query.filter(StoreVisit.status == status)
    pg = query.order_by(StoreVisit.visit_date.asc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({
        "status": "success",
        "data":   [_serialize_visit(v) for v in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_store_visits_bp.get("/<int:visit_id>")
@require_admin
def get_store_visit(visit_id: int):
    visit = db.session.get(StoreVisit, visit_id)
    if visit is None:
        return jsonify({"status": "error", "message": "Store visit not found."}), 404
    return jsonify({"status": "success", "data": _serialize_visit(visit)}), 200


@admin_store_visits_bp.put("/<int:visit_id>/status")
@require_admin
def update_store_visit_status(visit_id: int):
    visit = db.session.get(StoreVisit, visit_id)
    if visit is None:
        return jsonify({"status": "error", "message": "Store visit not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    new_status = str(data.get("status", "")).strip()
    valid_statuses = {s.value for s in VisitStatus}
    if new_status not in valid_statuses:
        return jsonify({
            "status":  "error",
            "message": f"Invalid status. Allowed: {', '.join(valid_statuses)}.",
        }), 400

    visit.status     = new_status
    visit.admin_notes = data.get("admin_notes") or visit.admin_notes
    db.session.commit()
    return jsonify({"status": "success", "message": "Visit status updated.", "data": _serialize_visit(visit)}), 200


# ══════════════════════════════════════════════════════════════════════════════
# CHAT
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_message(m: Message) -> dict:
    return {
        "id":              m.id,
        "conversation_id": m.conversation_id,
        "sender_id":       m.sender_id,
        "message_type":    m.message_type,
        "content":         m.content,
        "media_url":       m.media_url,
        "status":          m.status,
        "created_at":      m.created_at.isoformat() if m.created_at else None,
    }


@admin_chat_bp.get("/conversations/")
@require_admin
def list_conversations():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    pg       = Conversation.query.order_by(Conversation.updated_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)

    def _sc(c: Conversation) -> dict:
        return {
            "id":          c.id,
            "customer_id": c.customer_id,
            "order_id":    c.order_id,
            "subject":     c.subject,
            "is_open":     c.is_open,
            "created_at":  c.created_at.isoformat() if c.created_at else None,
        }

    return jsonify({
        "status": "success",
        "data":   [_sc(c) for c in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_chat_bp.get("/conversations/<int:conv_id>")
@require_admin
def get_conversation(conv_id: int):
    conv = db.session.get(Conversation, conv_id)
    if conv is None:
        return jsonify({"status": "error", "message": "Conversation not found."}), 404
    return jsonify({
        "status": "success",
        "data": {
            "id":          conv.id,
            "customer_id": conv.customer_id,
            "order_id":    conv.order_id,
            "subject":     conv.subject,
            "is_open":     conv.is_open,
            "messages":    [_serialize_message(m) for m in conv.messages if not m.is_deleted],
        },
    }), 200


@admin_chat_bp.post("/conversations/<int:conv_id>/messages")
@require_admin
def send_admin_message(conv_id: int):
    conv = db.session.get(Conversation, conv_id)
    if conv is None:
        return jsonify({"status": "error", "message": "Conversation not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    content   = str(data.get("content", "")).strip()
    media_url = data.get("media_url") or None
    if not content and not media_url:
        return jsonify({"status": "error", "message": "Message must have content or media_url."}), 400

    staff_id = int(get_jwt_identity())
    msg = Message(
        conversation_id=conv_id,
        sender_id=staff_id,
        message_type=data.get("message_type", MessageType.TEXT),
        content=content or None,
        media_url=media_url,
    )
    db.session.add(msg)
    db.session.commit()
    return jsonify({"status": "success", "message": "Message sent.", "data": _serialize_message(msg)}), 201


# ══════════════════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ══════════════════════════════════════════════════════════════════════════════

@admin_notifications_bp.post("/")
@require_admin
def send_notification():
    """Send a notification to a specific user or all users."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    title   = str(data.get("title",   "")).strip()
    message = str(data.get("message", "")).strip()
    if not title:
        return jsonify({"status": "error", "message": "'title' is required."}), 400
    if not message:
        return jsonify({"status": "error", "message": "'message' is required."}), 400

    user_id = data.get("user_id")

    if user_id:
        notif = Notification(
            user_id=int(user_id),
            title=title,
            message=message,
            notification_type=data.get("notification_type", "GENERAL"),
            reference_type=data.get("reference_type"),
            reference_id=data.get("reference_id"),
        )
        db.session.add(notif)
        db.session.commit()
        return jsonify({"status": "success", "message": "Notification sent.", "data": {"id": notif.id}}), 201
    else:
        # Broadcast to all customers
        users = User.query.filter_by(role="customer").all()
        for u in users:
            db.session.add(Notification(
                user_id=u.id,
                title=title,
                message=message,
                notification_type=data.get("notification_type", "GENERAL"),
            ))
        db.session.commit()
        return jsonify({
            "status":  "success",
            "message": f"Notification broadcast to {len(users)} customers.",
        }), 201


# ══════════════════════════════════════════════════════════════════════════════
# STAFF MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

STAFF_ROLES = {"admin", "super_admin", "sales_staff", "inventory_staff"}


def _serialize_staff(u: User) -> dict:
    return {
        "id":          u.id,
        "name":        u.name,
        "email":       u.email,
        "phone":       u.phone,
        "role":        u.role,
        "is_verified": u.is_verified,
        "created_at":  u.created_at.isoformat() if u.created_at else None,
    }


@admin_staff_bp.get("/")
@require_admin
def list_staff():
    staff = User.query.filter(User.role != "customer").order_by(User.name.asc()).all()
    return jsonify({"status": "success", "data": [_serialize_staff(u) for u in staff]}), 200


@admin_staff_bp.post("/")
@require_super_admin
def create_staff():
    """Only super_admin can create staff accounts."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    role = str(data.get("role", "")).strip()
    if role not in STAFF_ROLES:
        return jsonify({"status": "error", "message": f"Invalid role. Allowed: {', '.join(STAFF_ROLES)}."}), 400

    # Either email or phone required
    email = str(data.get("email", "")).strip() or None
    phone = str(data.get("phone", "")).strip() or None
    if not email and not phone:
        return jsonify({"status": "error", "message": "Either 'email' or 'phone' is required."}), 400

    name = str(data.get("name", "")).strip()
    if not name:
        return jsonify({"status": "error", "message": "'name' is required."}), 400

    if email and User.query.filter_by(email=email).first():
        return jsonify({"status": "error", "message": "Email already in use."}), 409
    if phone and User.query.filter_by(phone=phone).first():
        return jsonify({"status": "error", "message": "Phone already in use."}), 409

    staff = User(name=name, email=email, phone=phone, role=role, is_verified=True)
    db.session.add(staff)
    db.session.commit()
    return jsonify({"status": "success", "message": "Staff created.", "data": _serialize_staff(staff)}), 201


@admin_staff_bp.put("/<int:staff_id>")
@require_super_admin
def update_staff(staff_id: int):
    staff = db.session.get(User, staff_id)
    if staff is None or staff.role == "customer":
        return jsonify({"status": "error", "message": "Staff member not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    if "name" in data:
        staff.name = str(data["name"]).strip()
    if "role" in data:
        role = str(data["role"]).strip()
        if role not in STAFF_ROLES:
            return jsonify({"status": "error", "message": f"Invalid role. Allowed: {', '.join(STAFF_ROLES)}."}), 400
        staff.role = role

    db.session.commit()
    return jsonify({"status": "success", "message": "Staff updated.", "data": _serialize_staff(staff)}), 200


@admin_staff_bp.delete("/<int:staff_id>")
@require_super_admin
def delete_staff(staff_id: int):
    staff = db.session.get(User, staff_id)
    if staff is None or staff.role == "customer":
        return jsonify({"status": "error", "message": "Staff member not found."}), 404

    requester_id = int(get_jwt_identity())
    if staff.id == requester_id:
        return jsonify({"status": "error", "message": "You cannot delete your own account."}), 400

    # Soft-delete: set role back to customer or deactivate
    staff.is_verified = False
    staff.role = "customer"  # demote rather than hard-delete
    db.session.commit()
    return jsonify({"status": "success", "message": "Staff access revoked."}), 200


# ══════════════════════════════════════════════════════════════════════════════
# STORE SETTINGS
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_settings(s: StoreSettings) -> dict:
    return {
        "id":                    s.id,
        "store_name":            s.store_name,
        "tagline":               s.tagline,
        "address":               s.address,
        "phone":                 s.phone,
        "email":                 s.email,
        "gst_number":            s.gst_number,
        "business_hours":        s.business_hours,
        "logo_url":              s.logo_url,
        "favicon_url":           s.favicon_url,
        "currency_code":         s.currency_code,
        "currency_symbol":       s.currency_symbol,
        "facebook_url":          s.facebook_url,
        "instagram_url":         s.instagram_url,
        "twitter_url":           s.twitter_url,
        "youtube_url":           s.youtube_url,
        "whatsapp_number":       s.whatsapp_number,
        "default_gst_percentage":float(s.default_gst_percentage) if s.default_gst_percentage else None,
        "updated_at":            s.updated_at.isoformat() if s.updated_at else None,
    }


@admin_settings_bp.get("/")
@require_admin
def get_settings():
    settings = StoreSettings.query.first()
    if settings is None:
        settings = StoreSettings(store_name="Jewellery Store")
        db.session.add(settings)
        db.session.commit()
    return jsonify({"status": "success", "data": _serialize_settings(settings)}), 200


@admin_settings_bp.put("/")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN)
def update_settings():
    settings = StoreSettings.query.first()
    if settings is None:
        settings = StoreSettings()
        db.session.add(settings)

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    updatable = [
        "store_name", "tagline", "address", "phone", "email", "gst_number",
        "business_hours", "logo_url", "favicon_url", "currency_code", "currency_symbol",
        "facebook_url", "instagram_url", "twitter_url", "youtube_url", "whatsapp_number",
    ]
    for field in updatable:
        if field in data:
            setattr(settings, field, data[field])

    if "default_gst_percentage" in data:
        settings.default_gst_percentage = float(data["default_gst_percentage"])

    db.session.commit()
    return jsonify({"status": "success", "message": "Settings updated.", "data": _serialize_settings(settings)}), 200


# ══════════════════════════════════════════════════════════════════════════════
# CONTACT MESSAGES
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_contact(c: ContactMessage) -> dict:
    return {
        "id":          c.id,
        "user_id":     c.user_id,
        "name":        c.name,
        "email":       c.email,
        "phone":       c.phone,
        "subject":     c.subject,
        "message":     c.message,
        "status":      c.status,
        "admin_reply": c.admin_reply,
        "created_at":  c.created_at.isoformat() if c.created_at else None,
    }


@admin_contact_bp.get("/")
@require_admin
def list_contact_messages():
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    status   = request.args.get("status") or None
    query    = ContactMessage.query
    if status:
        query = query.filter(ContactMessage.status == status)
    pg = query.order_by(ContactMessage.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False)
    return jsonify({
        "status": "success",
        "data":   [_serialize_contact(c) for c in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@admin_contact_bp.get("/<int:msg_id>")
@require_admin
def get_contact_message(msg_id: int):
    msg = db.session.get(ContactMessage, msg_id)
    if msg is None:
        return jsonify({"status": "error", "message": "Message not found."}), 404
    # Auto-mark as READ
    if msg.status == ContactStatus.NEW:
        msg.status = ContactStatus.READ
        db.session.commit()
    return jsonify({"status": "success", "data": _serialize_contact(msg)}), 200


@admin_contact_bp.put("/<int:msg_id>/status")
@require_admin
def update_contact_status(msg_id: int):
    msg = db.session.get(ContactMessage, msg_id)
    if msg is None:
        return jsonify({"status": "error", "message": "Message not found."}), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    valid_statuses = {s.value for s in ContactStatus}
    new_status = str(data.get("status", "")).strip()
    if new_status not in valid_statuses:
        return jsonify({
            "status":  "error",
            "message": f"Invalid status. Allowed: {', '.join(valid_statuses)}.",
        }), 400

    msg.status = new_status
    if "admin_reply" in data:
        msg.admin_reply = data["admin_reply"]
    db.session.commit()
    return jsonify({"status": "success", "message": "Status updated.", "data": _serialize_contact(msg)}), 200


# ══════════════════════════════════════════════════════════════════════════════
# DASHBOARD
# ══════════════════════════════════════════════════════════════════════════════

@admin_dashboard_bp.get("/")
@require_admin
def dashboard():
    """
    Return comprehensive dashboard statistics.

    Uses database aggregation queries — not manual iteration.
    """
    now   = datetime.now(timezone.utc)
    today = now.date()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ── Customers ─────────────────────────────────────────────────────────────
    total_customers = User.query.filter_by(role="customer").count()

    # ── Products ──────────────────────────────────────────────────────────────
    total_products  = Product.query.count()
    active_products = Product.query.filter_by(is_active=True).count()
    low_stock_count = Product.query.filter(
        Product.stock_quantity > 0, Product.stock_quantity <= 5).count()
    out_of_stock    = Product.query.filter_by(stock_quantity=0).count()

    # ── Orders ────────────────────────────────────────────────────────────────
    total_orders     = Order.query.count()
    pending_orders   = Order.query.filter_by(order_status=OrderStatus.PLACED).count()
    delivered_orders = Order.query.filter_by(order_status=OrderStatus.DELIVERED).count()
    cancelled_orders = Order.query.filter_by(order_status=OrderStatus.CANCELLED).count()

    # ── Sales ─────────────────────────────────────────────────────────────────
    total_sales_row = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(Order.payment_status == "PAID").first()
    total_sales = float(total_sales_row[0]) if total_sales_row else 0.0

    today_sales_row = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.payment_status == "PAID",
        func.date(Order.created_at) == today,
    ).first()
    today_sales = float(today_sales_row[0]) if today_sales_row else 0.0

    monthly_sales_row = db.session.query(
        func.coalesce(func.sum(Order.total_amount), 0)
    ).filter(
        Order.payment_status == "PAID",
        Order.created_at >= month_start,
    ).first()
    monthly_sales = float(monthly_sales_row[0]) if monthly_sales_row else 0.0

    # ── KYC ───────────────────────────────────────────────────────────────────
    pending_kyc = KYC.query.filter_by(status=KYCStatus.PENDING).count()

    # ── Payments ──────────────────────────────────────────────────────────────
    pending_payments = Payment.query.filter_by(status="PENDING").count()

    # ── Store Visits ──────────────────────────────────────────────────────────
    visit_bookings = StoreVisit.query.filter_by(status=VisitStatus.PENDING).count()

    # ── Recent data ───────────────────────────────────────────────────────────
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(5).all()
    recent_customers = User.query.filter_by(role="customer").order_by(
        User.created_at.desc()).limit(5).all()
    low_stock_products = Product.query.filter(
        Product.stock_quantity > 0, Product.stock_quantity <= 5
    ).order_by(Product.stock_quantity.asc()).limit(10).all()

    def _rc(u: User) -> dict:
        return {"id": u.id, "name": u.name, "email": u.email, "phone": u.phone,
                "created_at": u.created_at.isoformat() if u.created_at else None}

    def _ro(o: Order) -> dict:
        return {"id": o.id, "order_number": o.order_number, "user_id": o.user_id,
                "total_amount": float(o.total_amount), "order_status": o.order_status,
                "payment_status": o.payment_status,
                "created_at": o.created_at.isoformat() if o.created_at else None}

    def _rlsp(p: Product) -> dict:
        return {"id": p.id, "sku": p.sku, "name": p.name,
                "stock_quantity": p.stock_quantity, "is_active": p.is_active}

    return jsonify({
        "status": "success",
        "data": {
            "stats": {
                "total_customers":  total_customers,
                "total_products":   total_products,
                "active_products":  active_products,
                "total_orders":     total_orders,
                "pending_orders":   pending_orders,
                "delivered_orders": delivered_orders,
                "cancelled_orders": cancelled_orders,
                "total_sales":      total_sales,
                "today_sales":      today_sales,
                "monthly_sales":    monthly_sales,
                "low_stock_count":  low_stock_count,
                "out_of_stock":     out_of_stock,
                "pending_kyc":      pending_kyc,
                "pending_payments": pending_payments,
                "store_visit_bookings": visit_bookings,
            },
            "recent_orders":     [_ro(o)   for o in recent_orders],
            "recent_customers":  [_rc(u)   for u in recent_customers],
            "low_stock_products":[_rlsp(p) for p in low_stock_products],
        },
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
# REPORTS
# ══════════════════════════════════════════════════════════════════════════════

def _get_date_range(args):
    """Extract and parse date_from / date_to from query args."""
    from datetime import date
    date_from = None
    date_to   = None
    try:
        if args.get("date_from"):
            date_from = date.fromisoformat(args["date_from"])
    except ValueError:
        pass
    try:
        if args.get("date_to"):
            date_to = date.fromisoformat(args["date_to"])
    except ValueError:
        pass
    return date_from, date_to


@admin_reports_bp.get("/sales")
@require_admin
def sales_report():
    args = request.args
    date_from, date_to = _get_date_range(args)

    query = db.session.query(
        func.date(Order.created_at).label("date"),
        func.count(Order.id).label("order_count"),
        func.coalesce(func.sum(Order.total_amount), 0).label("revenue"),
    ).filter(Order.payment_status == "PAID")

    if date_from:
        query = query.filter(Order.created_at >= date_from)
    if date_to:
        query = query.filter(Order.created_at <= date_to)

    rows = query.group_by(func.date(Order.created_at)).order_by(func.date(Order.created_at).asc()).all()

    return jsonify({
        "status": "success",
        "data": [{"date": str(r.date), "order_count": r.order_count, "revenue": float(r.revenue)}
                 for r in rows],
    }), 200


@admin_reports_bp.get("/orders")
@require_admin
def orders_report():
    """Order count grouped by status."""
    rows = db.session.query(
        Order.order_status.label("status"),
        func.count(Order.id).label("count"),
    ).group_by(Order.order_status).all()

    return jsonify({
        "status": "success",
        "data": [{"status": r.status, "count": r.count} for r in rows],
    }), 200


@admin_reports_bp.get("/inventory")
@require_admin
def inventory_report():
    """Top low-stock and out-of-stock products."""
    products = Product.query.order_by(Product.stock_quantity.asc()).limit(50).all()
    return jsonify({
        "status": "success",
        "data": [
            {"id": p.id, "sku": p.sku, "name": p.name,
             "stock_quantity": p.stock_quantity, "is_active": p.is_active}
            for p in products
        ],
    }), 200


@admin_reports_bp.get("/customers")
@require_admin
def customers_report():
    """Customer registration over time."""
    args = request.args
    date_from, date_to = _get_date_range(args)

    query = db.session.query(
        func.date(User.created_at).label("date"),
        func.count(User.id).label("registrations"),
    ).filter(User.role == "customer")

    if date_from:
        query = query.filter(User.created_at >= date_from)
    if date_to:
        query = query.filter(User.created_at <= date_to)

    rows = query.group_by(func.date(User.created_at)).order_by(func.date(User.created_at).asc()).all()

    return jsonify({
        "status": "success",
        "data": [{"date": str(r.date), "registrations": r.registrations} for r in rows],
    }), 200


@admin_reports_bp.get("/products")
@require_admin
def products_report():
    """Product distribution by category and metal type."""
    by_category = db.session.query(
        Product.category_id,
        func.count(Product.id).label("count"),
    ).group_by(Product.category_id).all()

    by_metal = db.session.query(
        Product.metal_type,
        func.count(Product.id).label("count"),
    ).group_by(Product.metal_type).all()

    return jsonify({
        "status": "success",
        "data": {
            "by_category": [{"category_id": r.category_id, "count": r.count} for r in by_category],
            "by_metal":    [{"metal_type":  r.metal_type,  "count": r.count} for r in by_metal],
        },
    }), 200
