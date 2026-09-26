"""
app/services/inventory_service.py

Business logic for inventory management.

Architecture
------------
    routes/admin_inventory_routes.py
        ↓  calls
    InventoryService  (this file)
        ↓  queries
    InventoryTransaction + Product models / db.session

Business Rules
--------------
* stock_quantity on Product is the authoritative current stock value.
  It is updated atomically alongside every InventoryTransaction.
* Stock CANNOT go negative. Any adjustment that would result in
  stock_quantity < 0 raises ValueError.
* LOW_STOCK threshold: product.stock_quantity <= low_stock_threshold
  is determined by the product's own threshold (default 5).
"""

import logging
from datetime import datetime, timezone

from app.extensions import db
from app.models.inventory import InventoryTransaction, TransactionType
from app.models.product import Product

logger = logging.getLogger(__name__)

# Default threshold below which a product is considered "low stock"
DEFAULT_LOW_STOCK_THRESHOLD = 5


class InventoryService:
    """
    Handles stock adjustments and inventory reporting.
    All methods are static — no instance state is needed.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # Serialization
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def serialize_transaction(tx: InventoryTransaction) -> dict:
        """Convert an InventoryTransaction to a JSON-safe dict."""
        return {
            "id":               tx.id,
            "product_id":       tx.product_id,
            "order_id":         tx.order_id,
            "transaction_type": tx.transaction_type,
            "quantity":         tx.quantity,
            "notes":            tx.notes,
            "performed_by_id":  tx.performed_by_id,
            "created_at":       tx.created_at.isoformat() if tx.created_at else None,
        }

    @staticmethod
    def serialize_inventory_status(product: Product) -> dict:
        """Return inventory status for a product."""
        qty = product.stock_quantity
        threshold = DEFAULT_LOW_STOCK_THRESHOLD

        if qty == 0:
            stock_status = "OUT_OF_STOCK"
        elif qty <= threshold:
            stock_status = "LOW_STOCK"
        else:
            stock_status = "IN_STOCK"

        return {
            "product_id":        product.id,
            "sku":               product.sku,
            "name":              product.name,
            "stock_quantity":    qty,
            "low_stock_threshold": threshold,
            "stock_status":      stock_status,
            "is_active":         product.is_active,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Queries
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_inventory_paginated(
        page: int = 1,
        per_page: int = 20,
        search: str = "",
        stock_status: str | None = None,
    ) -> dict:
        """
        Paginated product inventory list.

        Args:
            page:         Page number.
            per_page:     Items per page.
            search:       Filter on SKU / name.
            stock_status: "IN_STOCK" | "LOW_STOCK" | "OUT_OF_STOCK" (optional).

        Returns:
            { "items": [Product, ...], "pagination": {...} }
        """
        query = Product.query

        if search:
            term  = f"%{search}%"
            query = query.filter(
                db.or_(
                    Product.name.ilike(term),
                    Product.sku.ilike(term),
                )
            )

        if stock_status == "OUT_OF_STOCK":
            query = query.filter(Product.stock_quantity == 0)
        elif stock_status == "LOW_STOCK":
            query = query.filter(
                Product.stock_quantity > 0,
                Product.stock_quantity <= DEFAULT_LOW_STOCK_THRESHOLD,
            )
        elif stock_status == "IN_STOCK":
            query = query.filter(Product.stock_quantity > DEFAULT_LOW_STOCK_THRESHOLD)

        query = query.order_by(Product.stock_quantity.asc(), Product.name.asc())
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
    def get_product_transaction_history(
        product_id: int,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """Paginated transaction history for a specific product."""
        query = (
            InventoryTransaction.query
            .filter_by(product_id=product_id)
            .order_by(InventoryTransaction.created_at.desc())
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
    # Adjustments
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def adjust_stock(
        product: Product,
        transaction_type: str,
        quantity: int,
        notes: str | None = None,
        order_id: int | None = None,
        performed_by_id: int | None = None,
    ) -> InventoryTransaction:
        """
        Adjust stock for a product and record the transaction.

        For STOCK_IN / RETURN — quantity must be positive (stock increases).
        For STOCK_OUT / SALE  — quantity must be positive (stock decreases).
        For ADJUSTMENT        — quantity can be positive or negative.

        Args:
            product:          The Product to adjust.
            transaction_type: One of TransactionType values.
            quantity:         Magnitude of the change (always positive for
                              STOCK_IN, STOCK_OUT, SALE, RETURN).
            notes:            Optional reason/comment.
            order_id:         Optional linked order (for SALE/RETURN).
            performed_by_id:  User ID of the staff who made the change.

        Returns:
            The created InventoryTransaction.

        Raises:
            ValueError: If the transaction would result in negative stock,
                        or if the transaction_type is invalid.
        """
        # Validate transaction type
        valid_types = {t.value for t in TransactionType}
        if transaction_type not in valid_types:
            raise ValueError(
                f"Invalid transaction_type '{transaction_type}'. "
                f"Allowed: {', '.join(valid_types)}."
            )

        # Determine the delta to apply to stock_quantity
        if transaction_type in (TransactionType.STOCK_IN, TransactionType.RETURN):
            delta = abs(quantity)  # always increase
        elif transaction_type in (TransactionType.STOCK_OUT, TransactionType.SALE):
            delta = -abs(quantity)  # always decrease
        else:
            # ADJUSTMENT — quantity can be signed (positive = increase)
            delta = quantity

        # Prevent negative stock
        new_qty = product.stock_quantity + delta
        if new_qty < 0:
            raise ValueError(
                f"Insufficient stock. Current stock: {product.stock_quantity}, "
                f"requested delta: {delta}."
            )

        # Apply the adjustment
        product.stock_quantity = new_qty

        # Record the transaction
        tx = InventoryTransaction(
            product_id=product.id,
            order_id=order_id,
            transaction_type=transaction_type,
            quantity=quantity if transaction_type == TransactionType.ADJUSTMENT else abs(quantity),
            notes=notes,
            performed_by_id=performed_by_id,
        )
        db.session.add(tx)
        db.session.commit()

        logger.info(
            "[InventoryService] %s: product_id=%s qty=%s delta=%s → new_stock=%s",
            transaction_type, product.id, quantity, delta, new_qty,
        )
        return tx

    # ══════════════════════════════════════════════════════════════════════════
    # Validation
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def validate_adjustment(data: dict) -> list[str]:
        """
        Validate inventory adjustment request data.

        Required: transaction_type, quantity.
        """
        errors: list[str] = []
        valid_types = {t.value for t in TransactionType}

        if not str(data.get("transaction_type", "")).strip():
            errors.append("'transaction_type' is required.")
        elif data["transaction_type"] not in valid_types:
            errors.append(
                f"'transaction_type' must be one of: {', '.join(sorted(valid_types))}."
            )

        if data.get("quantity") is None:
            errors.append("'quantity' is required.")
        else:
            try:
                qty = int(data["quantity"])
                if qty == 0:
                    errors.append("'quantity' must be non-zero.")
            except (TypeError, ValueError):
                errors.append("'quantity' must be an integer.")

        return errors
