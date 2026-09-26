"""
app/routes/customer_order_routes.py

Customer order, invoice, and certificate endpoints.
All endpoints require a valid JWT token (role: customer).

Endpoints
---------
POST   /api/v1/orders                 (place a new order)
GET    /api/v1/orders                 (list customer's orders)
GET    /api/v1/orders/<id>            (get specific order details)
PUT    /api/v1/orders/<id>/cancel     (cancel an order)

GET    /api/v1/orders/<id>/invoice       (get invoice details/pdf link)
GET    /api/v1/orders/<id>/certificate   (get purity certificate details/pdf link)
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.order import Order, OrderItem, OrderStatus
from app.models.invoice import Invoice, PurityCertificate
from app.services.order_service import OrderService
from app.utils.decorators import require_auth

logger = logging.getLogger(__name__)

orders_bp = Blueprint("customer_orders", __name__)


def _serialize_order(order: Order, include_items: bool = False) -> dict:
    data = {
        "id":             order.id,
        "order_number":   order.order_number,
        "user_id":        order.user_id,
        "total_amount":   float(order.total_amount),
        "order_status":   order.order_status,
        "payment_status": order.payment_status,
        "payment_method": order.payment_method,
        "shipping_address": {
            "name": order.shipping_name,
            "phone": order.shipping_phone,
            "line1": order.shipping_line1,
            "city": order.shipping_city,
            "state": order.shipping_state,
            "pincode": order.shipping_pincode,
        },
        "created_at":     order.created_at.isoformat() if order.created_at else None,
        "updated_at":     order.updated_at.isoformat() if order.updated_at else None,
    }
    
    if include_items:
        items = []
        for item in order.items:
            items.append({
                "id":             item.id,
                "product_id":     item.product_id,
                "quantity":       item.quantity,
                "rate_per_gram":  float(item.rate_per_gram) if item.rate_per_gram else None,
                "making_charge":  float(item.making_charge),
                "stone_charge":   float(item.stone_charge),
                "gst_percentage": float(item.gst_percentage),
                "item_total":     float(item.item_total),
            })
        data["items"] = items
        
        history = []
        for h in order.status_history:
            history.append({
                "status": h.new_status,
                "notes":  h.notes,
                "created_at": h.created_at.isoformat() if h.created_at else None,
            })
        data["history"] = history
        
    return data


@orders_bp.post("/")
@require_auth
def create_order():
    """
    POST /api/v1/orders
    {
      "items": [{"productId": 123, "quantity": 1}],
      "shippingAddressId": 1,
      "billingAddressId": 1,
      "paymentMethod": "UPI"
    }
    """
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    items_data = data.get("items", [])
    if not items_data or not isinstance(items_data, list):
        return jsonify({"status": "error", "message": "'items' must be a non-empty list."}), 400

    shipping_addr_id = data.get("shippingAddressId")
    billing_addr_id = data.get("billingAddressId") or shipping_addr_id
    payment_method = data.get("paymentMethod", "UPI")

    if not shipping_addr_id:
        return jsonify({"status": "error", "message": "'shippingAddressId' is required."}), 400

    from app.models.address import Address
    shipping_addr = Address.query.filter_by(id=shipping_addr_id, user_id=user_id).first()
    if not shipping_addr:
        return jsonify({"status": "error", "message": "Invalid shipping address."}), 400
        
    billing_addr = Address.query.filter_by(id=billing_addr_id, user_id=user_id).first()
    if not billing_addr:
        return jsonify({"status": "error", "message": "Invalid billing address."}), 400

    formatted_items = []
    for item in items_data:
        if not item.get("productId") or not item.get("quantity"):
            return jsonify({"status": "error", "message": "Each item must have productId and quantity."}), 400
        formatted_items.append({
            "product_id": int(item["productId"]),
            "quantity":   int(item["quantity"])
        })

    try:
        order = OrderService.create_order(
            user_id=user_id,
            items=formatted_items,
            shipping_address=shipping_addr.to_dict(),
            billing_address=billing_addr.to_dict(),
            payment_method=payment_method,
            coupon_code=data.get("couponCode")
        )
        return jsonify({
            "status": "success",
            "message": "Order placed successfully.",
            "data": _serialize_order(order, include_items=True)
        }), 201
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400
    except Exception as e:
        logger.error(f"Error creating order: {str(e)}")
        return jsonify({"status": "error", "message": "Failed to create order due to an internal error."}), 500


@orders_bp.get("/")
@require_auth
def list_orders():
    user_id = int(get_jwt_identity())
    page     = max(1, int(request.args.get("page", 1) or 1))
    per_page = min(100, max(1, int(request.args.get("per_page", 20) or 20)))
    
    query = Order.query.filter_by(user_id=user_id).order_by(Order.created_at.desc())
    pg = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return jsonify({
        "status": "success",
        "data":   [_serialize_order(o) for o in pg.items],
        "pagination": {"page": page, "per_page": per_page, "total": pg.total, "pages": pg.pages,
                        "has_next": pg.has_next, "has_prev": pg.has_prev},
    }), 200


@orders_bp.get("/<int:order_id>")
@require_auth
def get_order(order_id: int):
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    
    if not order:
        return jsonify({"status": "error", "message": "Order not found."}), 404
        
    return jsonify({
        "status": "success",
        "data": _serialize_order(order, include_items=True)
    }), 200


@orders_bp.put("/<int:order_id>/cancel")
@require_auth
def cancel_order(order_id: int):
    user_id = int(get_jwt_identity())
    order = Order.query.filter_by(id=order_id, user_id=user_id).first()
    
    if not order:
        return jsonify({"status": "error", "message": "Order not found."}), 404
        
    if order.order_status not in (OrderStatus.PLACED, OrderStatus.CONFIRMED):
        return jsonify({"status": "error", "message": "Order cannot be cancelled at this stage."}), 400

    try:
        OrderService.update_status(
            order=order,
            new_status=OrderStatus.CANCELLED.value,
            notes="Cancelled by customer"
        )
        return jsonify({
            "status": "success",
            "message": "Order cancelled successfully.",
            "data": _serialize_order(order)
        }), 200
    except ValueError as e:
        return jsonify({"status": "error", "message": str(e)}), 400


# ══════════════════════════════════════════════════════════════════════════════
# INVOICES & CERTIFICATES
# ══════════════════════════════════════════════════════════════════════════════

@orders_bp.get("/<int:order_id>/invoice")
@require_auth
def get_invoice(order_id: int):
    user_id = int(get_jwt_identity())
    invoice = Invoice.query.filter_by(order_id=order_id, user_id=user_id).first()
    
    if not invoice:
        # In a real app, you might want to generate it on the fly if the order is delivered
        return jsonify({"status": "error", "message": "Invoice not yet generated for this order."}), 404

    return jsonify({
        "status": "success",
        "data": {
            "invoice_number": invoice.invoice_number,
            "subtotal":       float(invoice.subtotal),
            "gst_amount":     float(invoice.gst_amount),
            "discount_amount":float(invoice.discount_amount),
            "total_amount":   float(invoice.total_amount),
            "pdf_url":        invoice.pdf_url,
            "created_at":     invoice.created_at.isoformat() if invoice.created_at else None,
        }
    }), 200


@orders_bp.get("/<int:order_id>/certificate")
@require_auth
def get_certificates(order_id: int):
    user_id = int(get_jwt_identity())
    certificates = PurityCertificate.query.filter_by(order_id=order_id, user_id=user_id).all()
    
    if not certificates:
        return jsonify({"status": "error", "message": "Certificates not found for this order."}), 404

    data = []
    for cert in certificates:
        data.append({
            "certificate_number": cert.certificate_number,
            "product_id":         cert.product_id,
            "metal_type":         cert.metal_type,
            "purity":             cert.purity,
            "gross_weight":       float(cert.gross_weight) if cert.gross_weight else None,
            "net_weight":         float(cert.net_weight) if cert.net_weight else None,
            "pdf_url":            cert.pdf_url,
            "issue_date":         cert.issue_date.isoformat() if cert.issue_date else None,
        })

    return jsonify({"status": "success", "data": data}), 200
