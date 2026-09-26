"""
app/routes/customer_cart_routes.py

Customer cart and wishlist endpoints.
All endpoints require a valid JWT token (role: customer).

Endpoints
---------
Cart:
GET    /api/v1/cart
POST   /api/v1/cart           (add item)
PUT    /api/v1/cart/<id>      (update item quantity)
DELETE /api/v1/cart/<id>      (remove item)
DELETE /api/v1/cart           (clear cart)

Wishlist:
GET    /api/v1/users/wishlist
POST   /api/v1/users/wishlist
DELETE /api/v1/users/wishlist/<product_id>
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity

from app.extensions import db
from app.models.cart import Cart, CartItem, Wishlist
from app.models.product import Product
from app.services.product_service import ProductService
from app.utils.decorators import require_auth

logger = logging.getLogger(__name__)

cart_bp = Blueprint("cart", __name__)
wishlist_bp = Blueprint("wishlist", __name__)


# ══════════════════════════════════════════════════════════════════════════════
# CART
# ══════════════════════════════════════════════════════════════════════════════

def _get_or_create_cart(user_id: int) -> Cart:
    cart = Cart.query.filter_by(user_id=user_id).first()
    if not cart:
        cart = Cart(user_id=user_id)
        db.session.add(cart)
        db.session.commit()
    return cart

def _serialize_cart(cart: Cart) -> dict:
    items = []
    for item in cart.items:
        items.append({
            "id":             item.id,
            "product_id":     item.product_id,
            "quantity":       item.quantity,
            "price_snapshot": float(item.price_snapshot) if item.price_snapshot else None,
            "product":        ProductService.serialize(item.product, include_images=True) if item.product else None,
        })
    return {
        "id":      cart.id,
        "user_id": cart.user_id,
        "items":   items,
    }


@cart_bp.get("/")
@require_auth
def get_cart():
    user_id = int(get_jwt_identity())
    cart = _get_or_create_cart(user_id)
    return jsonify({"status": "success", "data": _serialize_cart(cart)}), 200


@cart_bp.post("/")
@require_auth
def add_to_cart():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True)
    if not data or not data.get("productId") or not data.get("quantity"):
        return jsonify({"status": "error", "message": "productId and quantity are required."}), 400

    product_id = int(data["productId"])
    quantity = int(data["quantity"])

    if quantity <= 0:
        return jsonify({"status": "error", "message": "Quantity must be greater than 0."}), 400

    product = Product.query.filter_by(id=product_id, is_active=True).first()
    if not product:
        return jsonify({"status": "error", "message": "Product not found or inactive."}), 404

    if product.stock_quantity < quantity:
        return jsonify({"status": "error", "message": f"Insufficient stock. Only {product.stock_quantity} available."}), 400

    cart = _get_or_create_cart(user_id)
    
    # Check if item already in cart
    existing_item = CartItem.query.filter_by(cart_id=cart.id, product_id=product_id).first()
    if existing_item:
        if product.stock_quantity < (existing_item.quantity + quantity):
            return jsonify({"status": "error", "message": f"Insufficient stock to add more."}), 400
        existing_item.quantity += quantity
    else:
        # Note: price_snapshot would ideally be fetched from PricingService
        new_item = CartItem(cart_id=cart.id, product_id=product_id, quantity=quantity)
        db.session.add(new_item)
        
    db.session.commit()
    return jsonify({"status": "success", "message": "Item added to cart.", "data": _serialize_cart(cart)}), 200


@cart_bp.put("/<int:item_id>")
@require_auth
def update_cart_item(item_id: int):
    user_id = int(get_jwt_identity())
    cart = _get_or_create_cart(user_id)
    
    item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first()
    if not item:
        return jsonify({"status": "error", "message": "Cart item not found."}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("quantity"):
        return jsonify({"status": "error", "message": "quantity is required."}), 400

    quantity = int(data["quantity"])
    if quantity <= 0:
        return jsonify({"status": "error", "message": "Quantity must be greater than 0."}), 400

    if item.product.stock_quantity < quantity:
        return jsonify({"status": "error", "message": f"Insufficient stock. Only {item.product.stock_quantity} available."}), 400

    item.quantity = quantity
    db.session.commit()
    return jsonify({"status": "success", "message": "Cart updated.", "data": _serialize_cart(cart)}), 200


@cart_bp.delete("/<int:item_id>")
@require_auth
def remove_cart_item(item_id: int):
    user_id = int(get_jwt_identity())
    cart = _get_or_create_cart(user_id)
    
    item = CartItem.query.filter_by(id=item_id, cart_id=cart.id).first()
    if not item:
        return jsonify({"status": "error", "message": "Cart item not found."}), 404

    db.session.delete(item)
    db.session.commit()
    return jsonify({"status": "success", "message": "Item removed from cart.", "data": _serialize_cart(cart)}), 200


@cart_bp.delete("/")
@require_auth
def clear_cart():
    user_id = int(get_jwt_identity())
    cart = _get_or_create_cart(user_id)
    
    CartItem.query.filter_by(cart_id=cart.id).delete()
    db.session.commit()
    return jsonify({"status": "success", "message": "Cart cleared.", "data": _serialize_cart(cart)}), 200


# ══════════════════════════════════════════════════════════════════════════════
# WISHLIST
# ══════════════════════════════════════════════════════════════════════════════

@wishlist_bp.get("/")
@require_auth
def get_wishlist():
    user_id = int(get_jwt_identity())
    wishlist_items = Wishlist.query.filter_by(user_id=user_id).all()
    
    data = []
    for w in wishlist_items:
        data.append({
            "id": w.id,
            "product_id": w.product_id,
            "product": ProductService.serialize(w.product, include_images=True) if w.product else None,
            "created_at": w.created_at.isoformat() if w.created_at else None,
        })
        
    return jsonify({"status": "success", "data": data}), 200


@wishlist_bp.post("/")
@require_auth
def add_to_wishlist():
    user_id = int(get_jwt_identity())
    data = request.get_json(silent=True)
    if not data or not data.get("productId"):
        return jsonify({"status": "error", "message": "productId is required."}), 400

    product_id = int(data["productId"])
    product = Product.query.filter_by(id=product_id, is_active=True).first()
    if not product:
        return jsonify({"status": "error", "message": "Product not found or inactive."}), 404

    existing = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    if existing:
        return jsonify({"status": "error", "message": "Product already in wishlist."}), 409

    w = Wishlist(user_id=user_id, product_id=product_id)
    db.session.add(w)
    db.session.commit()
    
    return jsonify({"status": "success", "message": "Added to wishlist."}), 201


@wishlist_bp.delete("/<int:product_id>")
@require_auth
def remove_from_wishlist(product_id: int):
    user_id = int(get_jwt_identity())
    w = Wishlist.query.filter_by(user_id=user_id, product_id=product_id).first()
    if not w:
        return jsonify({"status": "error", "message": "Product not in wishlist."}), 404

    db.session.delete(w)
    db.session.commit()
    return jsonify({"status": "success", "message": "Removed from wishlist."}), 200
