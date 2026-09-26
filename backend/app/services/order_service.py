"""
app/services/order_service.py

Business logic for order management.

Architecture
------------
    routes/admin_order_routes.py
        ↓  calls
    OrderService  (this file)
        ↓  calls
    InventoryService (for stock deduction on CONFIRMED)
    PricingService   (for price validation)
    db.session

Order Number Format
-------------------
    JWE-YYYYMMDD-XXXX
    Example: JWE-20260924-0001

Order Status Flow
-----------------
    PLACED → CONFIRMED → CRAFTING → HALLMARKING → SHIPPED → DELIVERED
                       ↘ CANCELLED
    DELIVERED → RETURNED → REFUNDED
"""

import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models.order import Order, OrderItem, OrderStatus, OrderStatusHistory, PaymentStatus
from app.models.product import Product
from app.services.inventory_service import InventoryService

logger = logging.getLogger(__name__)

# Valid forward transitions (from_status → set of allowed to_statuses)
VALID_TRANSITIONS: dict[str, set[str]] = {
    OrderStatus.PLACED:      {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
    OrderStatus.CONFIRMED:   {OrderStatus.CRAFTING,  OrderStatus.CANCELLED},
    OrderStatus.CRAFTING:    {OrderStatus.HALLMARKING, OrderStatus.CANCELLED},
    OrderStatus.HALLMARKING: {OrderStatus.SHIPPED, OrderStatus.CANCELLED},
    OrderStatus.SHIPPED:     {OrderStatus.DELIVERED, OrderStatus.RETURNED},
    OrderStatus.DELIVERED:   {OrderStatus.RETURNED},
    OrderStatus.RETURNED:    {OrderStatus.REFUNDED},
    OrderStatus.CANCELLED:   set(),
    OrderStatus.REFUNDED:    set(),
}


class OrderService:
    """
    Handles order creation, status transitions, and queries.
    All methods are static — no instance state is needed.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # Order number generation
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def generate_order_number() -> str:
        """
        Generate a unique, human-readable order number.

        Format: JWE-YYYYMMDD-XXXX
        XXXX is a 4-digit counter for orders placed on the same day (01-based).
        """
        today_str = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix    = f"JWE-{today_str}-"

        # Count orders placed today to get the next number
        today_count = Order.query.filter(
            Order.order_number.like(f"{prefix}%")
        ).count()

        return f"{prefix}{str(today_count + 1).zfill(4)}"
    @staticmethod
    def create_order(
        user_id: int,
        items: list[dict],
        shipping_address: dict,
        billing_address: dict,
        payment_method: str = "UPI",
        coupon_code: str | None = None
    ) -> Order:
        from app.services.pricing_service import PricingService
        
        # 1. Create order instance
        order = Order(
            order_number=OrderService.generate_order_number(),
            user_id=user_id,
            shipping_name=shipping_address.get("full_name"),
            shipping_phone=shipping_address.get("phone"),
            shipping_line1=shipping_address.get("address_line"),
            shipping_line2=shipping_address.get("address_line2"),
            shipping_city=shipping_address.get("city"),
            shipping_state=shipping_address.get("state"),
            shipping_pincode=shipping_address.get("pincode"),
            shipping_country=shipping_address.get("country", "India"),
            payment_method=payment_method,
            coupon_code=coupon_code,
        )
        db.session.add(order)
        
        # 2. Process items
        subtotal = 0
        total_making = 0
        total_stone = 0
        total_gst = 0
        
        for item_data in items:
            product_id = item_data["product_id"]
            qty = item_data["quantity"]
            
            product = db.session.get(Product, product_id)
            if not product or not product.is_active:
                raise ValueError(f"Product ID {product_id} is unavailable.")
            if product.stock_quantity < qty:
                raise ValueError(f"Insufficient stock for {product.name}.")
                
            price_details = PricingService.calculate_product_price(
                net_weight=product.net_weight,
                making_charge=product.making_charge,
                stone_charge=product.stone_charge,
                gst_percentage=product.gst_percentage,
                metal_type=product.metal_type,
                purity=product.purity,
            )
            
            order_item = OrderItem(
                order=order,
                product_id=product.id,
                product_name=product.name,
                product_sku=product.sku,
                metal_type=product.metal_type,
                purity=product.purity,
                net_weight=product.net_weight,
                gross_weight=product.gross_weight,
                quantity=qty,
                rate_per_gram=price_details["rate_per_gram"],
                base_metal_value=price_details["base_metal_value"],
                making_charge=price_details["making_charge"],
                stone_charge=price_details["stone_charge"],
                gst_percentage=price_details["gst_percentage"],
                gst_amount=price_details["gst_amount"],
                item_total=price_details["final_price"],
            )
            db.session.add(order_item)
            
            subtotal += price_details["base_metal_value"] * qty
            total_making += price_details["making_charge"] * qty
            total_stone += price_details["stone_charge"] * qty
            total_gst += price_details["gst_amount"] * qty
            
        order.subtotal = subtotal
        order.making_charges = total_making
        order.stone_charges = total_stone
        order.gst_amount = total_gst
        
        discount = 0
        order.discount_amount = discount
        order.total_amount = subtotal + total_making + total_stone + total_gst - discount
        
        # Record initial status history
        history = OrderStatusHistory(
            order=order,
            old_status=None,
            new_status=OrderStatus.PLACED.value,
            notes="Order placed by customer."
        )
        db.session.add(history)
        
        db.session.commit()
        return order

    # ══════════════════════════════════════════════════════════════════════════
    # Serialization
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def serialize_item(item: OrderItem) -> dict:
        return {
            "id":              item.id,
            "product_id":      item.product_id,
            "product_name":    item.product_name,
            "product_sku":     item.product_sku,
            "metal_type":      item.metal_type,
            "purity":          item.purity,
            "net_weight":      float(item.net_weight)    if item.net_weight    else None,
            "gross_weight":    float(item.gross_weight)  if item.gross_weight  else None,
            "quantity":        item.quantity,
            "rate_per_gram":   float(item.rate_per_gram) if item.rate_per_gram else None,
            "base_metal_value":float(item.base_metal_value) if item.base_metal_value else None,
            "making_charge":   float(item.making_charge),
            "stone_charge":    float(item.stone_charge),
            "gst_percentage":  float(item.gst_percentage),
            "gst_amount":      float(item.gst_amount),
            "item_total":      float(item.item_total),
        }

    @staticmethod
    def serialize_status_history(h: OrderStatusHistory) -> dict:
        return {
            "id":         h.id,
            "old_status": h.old_status,
            "new_status": h.new_status,
            "changed_by": h.changed_by,
            "notes":      h.notes,
            "created_at": h.created_at.isoformat() if h.created_at else None,
        }

    @staticmethod
    def serialize(order: Order, include_items: bool = True, include_history: bool = False) -> dict:
        data = {
            "id":             order.id,
            "order_number":   order.order_number,
            "user_id":        order.user_id,
            "shipping": {
                "name":    order.shipping_name,
                "phone":   order.shipping_phone,
                "line1":   order.shipping_line1,
                "line2":   order.shipping_line2,
                "city":    order.shipping_city,
                "state":   order.shipping_state,
                "pincode": order.shipping_pincode,
                "country": order.shipping_country,
            },
            "subtotal":        float(order.subtotal),
            "making_charges":  float(order.making_charges),
            "stone_charges":   float(order.stone_charges),
            "gst_amount":      float(order.gst_amount),
            "discount_amount": float(order.discount_amount),
            "total_amount":    float(order.total_amount),
            "coupon_code":     order.coupon_code,
            "order_status":    order.order_status,
            "payment_status":  order.payment_status,
            "notes":           order.notes,
            "created_at":      order.created_at.isoformat() if order.created_at else None,
            "updated_at":      order.updated_at.isoformat() if order.updated_at else None,
        }
        if include_items:
            data["items"] = [OrderService.serialize_item(i) for i in order.items]
        if include_history:
            data["status_history"] = [OrderService.serialize_status_history(h) for h in order.status_history]
        return data

    # ══════════════════════════════════════════════════════════════════════════
    # Queries
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_orders_paginated(params: dict) -> dict:
        """
        Admin: paginated, filtered order list.

        Supported params:
            search, order_number, user_id, order_status, payment_status,
            date_from, date_to, page, per_page.
        """
        from sqlalchemy import cast, String
        query = Order.query

        search = str(params.get("search", "")).strip()
        if search:
            term  = f"%{search}%"
            query = query.filter(
                db.or_(
                    Order.order_number.ilike(term),
                    Order.shipping_name.ilike(term),
                    Order.shipping_phone.ilike(term),
                )
            )

        if params.get("order_number"):
            query = query.filter(Order.order_number.ilike(f"%{params['order_number']}%"))

        if params.get("user_id"):
            try:
                query = query.filter(Order.user_id == int(params["user_id"]))
            except (TypeError, ValueError):
                pass

        if params.get("order_status"):
            query = query.filter(Order.order_status == params["order_status"])

        if params.get("payment_status"):
            query = query.filter(Order.payment_status == params["payment_status"])

        if params.get("date_from"):
            try:
                from datetime import date
                d = date.fromisoformat(str(params["date_from"]))
                query = query.filter(Order.created_at >= d)
            except ValueError:
                pass

        if params.get("date_to"):
            try:
                from datetime import date
                d = date.fromisoformat(str(params["date_to"]))
                query = query.filter(Order.created_at <= d)
            except ValueError:
                pass

        query = query.order_by(Order.created_at.desc())

        try:
            page = max(1, int(params.get("page", 1)))
        except (TypeError, ValueError):
            page = 1
        try:
            per_page = min(100, max(1, int(params.get("per_page", 20))))
        except (TypeError, ValueError):
            per_page = 20

        pagination = query.paginate(page=page, per_page=per_page, error_out=False)

        return {
            "items": pagination.items,
            "pagination": {
                "page":     page,
                "per_page": per_page,
                "total":    pagination.total,
                "pages":    pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }

    @staticmethod
    def get_order_by_id(order_id: int) -> Order | None:
        return db.session.get(Order, order_id)

    @staticmethod
    def get_customer_orders(user_id: int, page: int = 1, per_page: int = 20) -> dict:
        """Customer-facing paginated order list."""
        query = (
            Order.query
            .filter_by(user_id=user_id)
            .order_by(Order.created_at.desc())
        )
        pagination = query.paginate(page=page, per_page=per_page, error_out=False)
        return {
            "items": pagination.items,
            "pagination": {
                "page":     page,
                "per_page": per_page,
                "total":    pagination.total,
                "pages":    pagination.pages,
                "has_next": pagination.has_next,
                "has_prev": pagination.has_prev,
            },
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Status management
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def update_status(
        order: Order,
        new_status: str,
        changed_by: int | None = None,
        notes: str | None = None,
    ) -> Order:
        """
        Update an order's status with validation and audit logging.

        Also handles automatic inventory deduction on CONFIRMED,
        and automatic stock return on CANCELLED/RETURNED.

        Args:
            order:      The Order to update.
            new_status: Target OrderStatus value.
            changed_by: User ID of the staff making the change.
            notes:      Optional comment.

        Returns:
            The updated Order.

        Raises:
            ValueError: If the transition is not allowed.
        """
        valid_statuses = {s.value for s in OrderStatus}
        if new_status not in valid_statuses:
            raise ValueError(f"Invalid status '{new_status}'.")

        current = order.order_status
        allowed = VALID_TRANSITIONS.get(current, set())

        if new_status not in allowed:
            raise ValueError(
                f"Cannot transition from '{current}' to '{new_status}'. "
                f"Allowed transitions: {', '.join(allowed) or 'none'}."
            )

        # ── Deduct inventory on CONFIRMED ─────────────────────────────────────
        if new_status == OrderStatus.CONFIRMED:
            for item in order.items:
                product = db.session.get(Product, item.product_id)
                if product:
                    try:
                        InventoryService.adjust_stock(
                            product=product,
                            transaction_type="SALE",
                            quantity=item.quantity,
                            order_id=order.id,
                            notes=f"Order {order.order_number} confirmed.",
                            performed_by_id=changed_by,
                        )
                    except ValueError as exc:
                        raise ValueError(
                            f"Cannot confirm order: insufficient stock for "
                            f"'{product.name}'. {exc}"
                        )

        # ── Return inventory on CANCELLED / RETURNED ──────────────────────────
        elif new_status in (OrderStatus.CANCELLED, OrderStatus.RETURNED):
            # Only return stock if order was previously CONFIRMED or later
            confirmed_statuses = {
                OrderStatus.CONFIRMED, OrderStatus.CRAFTING,
                OrderStatus.HALLMARKING, OrderStatus.SHIPPED, OrderStatus.DELIVERED,
            }
            if current in confirmed_statuses:
                for item in order.items:
                    product = db.session.get(Product, item.product_id)
                    if product:
                        InventoryService.adjust_stock(
                            product=product,
                            transaction_type="RETURN",
                            quantity=item.quantity,
                            order_id=order.id,
                            notes=f"Order {order.order_number} {new_status.lower()}.",
                            performed_by_id=changed_by,
                        )

        # ── Record history entry ──────────────────────────────────────────────
        history = OrderStatusHistory(
            order_id=order.id,
            old_status=current,
            new_status=new_status,
            changed_by=changed_by,
            notes=notes,
        )
        db.session.add(history)

        order.order_status = new_status
        db.session.commit()

        logger.info(
            "[OrderService] Order %s: %s → %s (by user_id=%s)",
            order.order_number, current, new_status, changed_by,
        )
        return order
