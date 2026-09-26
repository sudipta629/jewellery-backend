"""
app/routes/admin_customer_routes.py

Admin endpoints for customer and KYC management.

All routes require a valid JWT with any admin role.

Customer Endpoints
------------------
GET /api/v1/admin/customers/          Paginated customer list with filters.
GET /api/v1/admin/customers/<id>      Customer profile + addresses + orders + KYC.

KYC Endpoints
-------------
GET /api/v1/admin/kyc/                Paginated KYC submissions.
GET /api/v1/admin/kyc/<id>            Single KYC record.
PUT /api/v1/admin/kyc/<id>/approve    Approve KYC.
PUT /api/v1/admin/kyc/<id>/reject     Reject KYC with reason.

Security
--------
* Customer-sensitive fields (full phone numbers) are included since
  this is an admin endpoint.
* Do NOT expose OTP hashes, password equivalents, or JWT secrets.
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity
from sqlalchemy import func

from app.extensions import db
from app.models.user import User
from app.models.kyc import KYC, KYCStatus
from app.models.order import Order
from app.utils.decorators import (
    require_admin,
    require_role,
    ROLE_ADMIN,
    ROLE_SUPER_ADMIN,
    ROLE_SALES_STAFF,
)

logger = logging.getLogger(__name__)

admin_customers_bp = Blueprint("admin_customers", __name__)


# ══════════════════════════════════════════════════════════════════════════════
# CUSTOMER MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

@admin_customers_bp.get("/customers/")
@require_admin
def list_customers():
    """
    Paginated list of all customers (role == 'customer').

    Query parameters:
        search   — name / email / phone search
        page     — integer, default 1
        per_page — integer, default 20, max 100

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

    search = args.get("search", "").strip()

    query = User.query.filter_by(role="customer")

    if search:
        term  = f"%{search}%"
        query = query.filter(
            db.or_(
                User.name.ilike(term),
                User.email.ilike(term),
                User.phone.ilike(term),
            )
        )

    query = query.order_by(User.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    def _serialize_customer_summary(u: User) -> dict:
        return {
            "id":          u.id,
            "name":        u.name,
            "email":       u.email,
            "phone":       u.phone,
            "is_verified": u.is_verified,
            "created_at":  u.created_at.isoformat() if u.created_at else None,
        }

    return jsonify({
        "status":     "success",
        "data":       [_serialize_customer_summary(u) for u in pagination.items],
        "pagination": {
            "page":     page,
            "per_page": per_page,
            "total":    pagination.total,
            "pages":    pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        },
    }), 200


@admin_customers_bp.get("/customers/<int:user_id>")
@require_admin
def get_customer(user_id: int):
    """
    Return full customer profile including addresses, orders summary, and KYC.

    Response (200): { "status": "success", "data": { ... } }
    Error    (404): customer not found / not a customer role.
    """
    customer = db.session.get(User, user_id)
    if customer is None or customer.role != "customer":
        return jsonify({"status": "error", "message": "Customer not found."}), 404

    # Order stats
    order_stats = db.session.query(
        func.count(Order.id).label("total_orders"),
        func.coalesce(func.sum(Order.total_amount), 0).label("total_spending"),
    ).filter_by(user_id=user_id).first()

    # KYC
    kyc_records = KYC.query.filter_by(user_id=user_id).order_by(KYC.created_at.desc()).all()

    # Addresses
    addresses = [
        {
            "id":         a.id,
            "label":      a.label,
            "line1":      a.line1,
            "line2":      a.line2,
            "city":       a.city,
            "state":      a.state,
            "pincode":    a.pincode,
            "country":    a.country,
            "is_default": a.is_default,
        }
        for a in customer.addresses
    ]

    return jsonify({
        "status": "success",
        "data": {
            "id":          customer.id,
            "name":        customer.name,
            "email":       customer.email,
            "phone":       customer.phone,
            "role":        customer.role,
            "is_verified": customer.is_verified,
            "created_at":  customer.created_at.isoformat() if customer.created_at else None,
            "addresses":   addresses,
            "order_summary": {
                "total_orders":   order_stats.total_orders if order_stats else 0,
                "total_spending": float(order_stats.total_spending) if order_stats else 0.0,
            },
            "kyc": [_serialize_kyc(k) for k in kyc_records],
        },
    }), 200


# ══════════════════════════════════════════════════════════════════════════════
# KYC MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def _serialize_kyc(kyc: KYC) -> dict:
    return {
        "id":               kyc.id,
        "user_id":          kyc.user_id,
        "document_type":    kyc.document_type,
        "document_number":  kyc.document_number,
        "document_url":     kyc.document_url,
        "status":           kyc.status,
        "submitted_at":     kyc.submitted_at.isoformat() if kyc.submitted_at else None,
        "reviewed_at":      kyc.reviewed_at.isoformat() if kyc.reviewed_at else None,
        "reviewed_by":      kyc.reviewed_by,
        "rejection_reason": kyc.rejection_reason,
        "created_at":       kyc.created_at.isoformat() if kyc.created_at else None,
    }


@admin_customers_bp.get("/kyc/")
@require_admin
def list_kyc():
    """
    Paginated list of all KYC submissions.

    Query parameters:
        status   — PENDING | APPROVED | REJECTED
        page     — integer, default 1
        per_page — integer, default 20, max 100

    Response (200): { "status": "success", "data": [...], "pagination": {...} }
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

    status_filter = args.get("status", "").strip() or None

    query = KYC.query
    if status_filter:
        query = query.filter(KYC.status == status_filter)

    query = query.order_by(KYC.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return jsonify({
        "status":     "success",
        "data":       [_serialize_kyc(k) for k in pagination.items],
        "pagination": {
            "page":     page,
            "per_page": per_page,
            "total":    pagination.total,
            "pages":    pagination.pages,
            "has_next": pagination.has_next,
            "has_prev": pagination.has_prev,
        },
    }), 200


@admin_customers_bp.get("/kyc/<int:kyc_id>")
@require_admin
def get_kyc(kyc_id: int):
    """
    Return a single KYC record.

    Response (200): { "status": "success", "data": { ... } }
    Error    (404): KYC not found.
    """
    kyc = db.session.get(KYC, kyc_id)
    if kyc is None:
        return jsonify({"status": "error", "message": "KYC record not found."}), 404

    return jsonify({"status": "success", "data": _serialize_kyc(kyc)}), 200


@admin_customers_bp.put("/kyc/<int:kyc_id>/approve")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_SALES_STAFF)
def approve_kyc(kyc_id: int):
    """
    Approve a pending KYC submission.

    Response (200): { "status": "success", "message": "KYC approved.", "data": { ... } }
    Errors: 400 (already approved/rejected), 404.
    """
    kyc = db.session.get(KYC, kyc_id)
    if kyc is None:
        return jsonify({"status": "error", "message": "KYC record not found."}), 404

    if kyc.status != KYCStatus.PENDING:
        return jsonify({
            "status":  "error",
            "message": f"KYC is already '{kyc.status}' and cannot be re-approved.",
        }), 400

    reviewer_id   = int(get_jwt_identity())
    kyc.status      = KYCStatus.APPROVED
    kyc.reviewed_at = datetime.now(timezone.utc)
    kyc.reviewed_by = reviewer_id
    db.session.commit()

    logger.info("[KYC] Approved kyc_id=%s by user_id=%s", kyc_id, reviewer_id)
    return jsonify({"status": "success", "message": "KYC approved.", "data": _serialize_kyc(kyc)}), 200


@admin_customers_bp.put("/kyc/<int:kyc_id>/reject")
@require_role(ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_SALES_STAFF)
def reject_kyc(kyc_id: int):
    """
    Reject a pending KYC submission with a reason.

    Request body:
        { "reason": "Document is blurry." }

    Response (200): { "status": "success", "message": "KYC rejected.", "data": { ... } }
    Errors: 400 (already reviewed / missing reason), 404.
    """
    kyc = db.session.get(KYC, kyc_id)
    if kyc is None:
        return jsonify({"status": "error", "message": "KYC record not found."}), 404

    if kyc.status != KYCStatus.PENDING:
        return jsonify({
            "status":  "error",
            "message": f"KYC is already '{kyc.status}' and cannot be rejected.",
        }), 400

    data = request.get_json(silent=True) or {}
    reason = str(data.get("reason", "")).strip()
    if not reason:
        return jsonify({"status": "error", "message": "'reason' is required for rejection."}), 400

    reviewer_id        = int(get_jwt_identity())
    kyc.status          = KYCStatus.REJECTED
    kyc.reviewed_at     = datetime.now(timezone.utc)
    kyc.reviewed_by     = reviewer_id
    kyc.rejection_reason = reason
    db.session.commit()

    logger.info("[KYC] Rejected kyc_id=%s by user_id=%s", kyc_id, reviewer_id)
    return jsonify({"status": "success", "message": "KYC rejected.", "data": _serialize_kyc(kyc)}), 200
