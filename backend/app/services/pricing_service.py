"""
app/services/pricing_service.py

Reusable jewellery pricing engine.

Architecture
------------
    routes/* (customer, admin, cart, order, invoice)
        ↓  calls
    PricingService  (this file)
        ↓  queries
    MetalRate / Product models

Pricing Formula
---------------
    Final Price = (metal_rate_per_gram × net_weight)
                + making_charge
                + stone_charge
                + GST_amount

Where:
    base_metal_value = rate_per_gram × net_weight
    taxable_amount   = base_metal_value + making_charge + stone_charge
    gst_amount       = taxable_amount × (gst_percentage / 100)
    final_price      = taxable_amount + gst_amount

CRITICAL RULE: Never trust price values from the frontend.
All pricing must be calculated server-side using this service.
The rate used must be the current active server-side rate.

Price Snapshot Rule
-------------------
When an order is placed, a SNAPSHOT of the price components is stored
(rate_used, metal_value, making_charge, stone_charge, gst, total).
This ensures historical order prices do not change when future metal
rates are updated.
"""

import logging
from decimal import Decimal, ROUND_HALF_UP
from datetime import date

from app.extensions import db
from app.models.metal_rate import MetalRate

logger = logging.getLogger(__name__)

# Rounding: 2 decimal places, ROUND_HALF_UP (standard accounting)
TWO_PLACES = Decimal("0.01")


class PricingService:
    """
    Central pricing engine for jewellery products.

    All methods are static — no instance state is needed.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # Rate queries
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_current_rate(metal_type: str, purity: str | None = None) -> MetalRate | None:
        """
        Return the currently active metal rate for the given metal + purity.

        Queries the row with is_active=True and the most recent effective_date.

        Args:
            metal_type: e.g. "gold", "silver", "platinum"
            purity:     e.g. "24K", "22K", "925" (optional)

        Returns:
            The active MetalRate instance, or None if no rate is configured.
        """
        query = MetalRate.query.filter_by(is_active=True)
        query = query.filter(MetalRate.metal_type.ilike(metal_type))

        if purity:
            query = query.filter(MetalRate.purity.ilike(purity))
        else:
            query = query.filter(MetalRate.purity.is_(None))

        rate = query.order_by(MetalRate.effective_date.desc()).first()
        return rate

    @staticmethod
    def get_rate_history(
        metal_type: str | None = None,
        purity: str | None = None,
        page: int = 1,
        per_page: int = 20,
    ) -> dict:
        """
        Return paginated rate history (all rows, not just active ones).

        Args:
            metal_type: Optional filter.
            purity:     Optional filter.
            page:       Page number.
            per_page:   Items per page.

        Returns:
            { "items": [MetalRate, ...], "pagination": {...} }
        """
        query = MetalRate.query

        if metal_type:
            query = query.filter(MetalRate.metal_type.ilike(metal_type))
        if purity:
            query = query.filter(MetalRate.purity.ilike(purity))

        query = query.order_by(
            MetalRate.metal_type.asc(),
            MetalRate.effective_date.desc(),
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
    # Rate CRUD
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def set_rate(
        metal_type: str,
        purity: str | None,
        rate_per_gram: float,
        effective_date: date | None = None,
        source: str = "manual",
    ) -> MetalRate:
        """
        Create a new rate record and deactivate all previous records for the
        same metal + purity combination.

        Args:
            metal_type:     e.g. "gold"
            purity:         e.g. "22K" (or None)
            rate_per_gram:  Rate in INR per gram.
            effective_date: Date the rate is effective (defaults to today).
            source:         Who/what set the rate (e.g. "manual", "mcx_api").

        Returns:
            The newly created MetalRate instance.

        Raises:
            ValueError: If rate_per_gram <= 0.
        """
        if float(rate_per_gram) <= 0:
            raise ValueError("rate_per_gram must be a positive number.")

        if effective_date is None:
            from datetime import date as _date
            effective_date = _date.today()

        # Deactivate all existing active records for this metal+purity
        query = MetalRate.query.filter_by(is_active=True)
        query = query.filter(MetalRate.metal_type.ilike(metal_type))
        if purity:
            query = query.filter(MetalRate.purity.ilike(purity))
        else:
            query = query.filter(MetalRate.purity.is_(None))

        query.update({"is_active": False}, synchronize_session=False)

        new_rate = MetalRate(
            metal_type=metal_type.strip().lower(),
            purity=purity.strip().upper() if purity else None,
            rate_per_gram=Decimal(str(rate_per_gram)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP),
            effective_date=effective_date,
            source=source,
            is_active=True,
        )
        db.session.add(new_rate)
        db.session.commit()

        logger.info(
            "[PricingService] Set rate: %s/%s = %s/gram (source=%s)",
            metal_type, purity, rate_per_gram, source,
        )
        return new_rate

    @staticmethod
    def update_rate(rate: MetalRate, data: dict) -> MetalRate:
        """
        Update a metal rate record's source or effective date.

        NOTE: Changing rate_per_gram on an existing record creates a
        discrepancy in audit history.  Prefer calling set_rate() which
        creates a fresh record and deactivates the old one.

        This method is provided for minor corrections only.
        """
        if "rate_per_gram" in data:
            val = float(data["rate_per_gram"])
            if val <= 0:
                raise ValueError("rate_per_gram must be positive.")
            rate.rate_per_gram = Decimal(str(val)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        if "source" in data:
            rate.source = data["source"]
        if "effective_date" in data:
            rate.effective_date = data["effective_date"]

        db.session.commit()
        return rate

    # ══════════════════════════════════════════════════════════════════════════
    # Price calculation
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def calculate_product_price(
        net_weight: float | Decimal | None,
        making_charge: float | Decimal,
        stone_charge: float | Decimal,
        gst_percentage: float | Decimal,
        metal_type: str | None = None,
        purity: str | None = None,
        rate_per_gram: float | Decimal | None = None,
    ) -> dict:
        """
        Calculate the final price of a jewellery item.

        This is the SINGLE canonical pricing function used by:
        - Customer product API (display price)
        - Admin product API
        - Cart (validate item totals)
        - Order placement (snapshot price)
        - Invoice generation

        Pricing formula:
            base_metal_value = rate_per_gram × net_weight
            taxable_amount   = base_metal_value + making_charge + stone_charge
            gst_amount       = taxable_amount × (gst_percentage / 100)
            final_price      = taxable_amount + gst_amount

        Args:
            net_weight:     Weight in grams (metal weight only).
            making_charge:  Fixed making charge in INR.
            stone_charge:   Fixed stone/diamond charge in INR.
            gst_percentage: GST rate (e.g. 3.0 for 3%).
            metal_type:     Required if rate_per_gram is not supplied.
            purity:         Required if rate_per_gram is not supplied.
            rate_per_gram:  Override rate (e.g. from a stored order snapshot).
                            If None, the current active DB rate is used.

        Returns:
            {
                "rate_per_gram":    float | None,
                "net_weight":       float | None,
                "base_metal_value": float,
                "making_charge":    float,
                "stone_charge":     float,
                "taxable_amount":   float,
                "gst_percentage":   float,
                "gst_amount":       float,
                "final_price":      float,
                "rate_found":       bool,
            }

        Notes:
        - If no rate is found and rate_per_gram is not supplied, all
          metal-value-dependent fields will be None / 0.
        - All returned values are floats (safe for JSON).
        """

        def to_dec(v) -> Decimal:
            if v is None:
                return Decimal("0")
            return Decimal(str(v))

        # Fetch rate if not explicitly supplied
        _rate_found = True
        if rate_per_gram is None and metal_type:
            rate_obj = PricingService.get_current_rate(metal_type, purity)
            if rate_obj:
                rate_per_gram = rate_obj.rate_per_gram
            else:
                _rate_found = False

        d_rate      = to_dec(rate_per_gram)
        d_weight    = to_dec(net_weight)
        d_making    = to_dec(making_charge)
        d_stone     = to_dec(stone_charge)
        d_gst_pct   = to_dec(gst_percentage)

        base_metal  = (d_rate * d_weight).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        taxable     = (base_metal + d_making + d_stone).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        gst_amount  = (taxable * d_gst_pct / Decimal("100")).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
        final       = (taxable + gst_amount).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)

        return {
            "rate_per_gram":    float(d_rate) if rate_per_gram is not None else None,
            "net_weight":       float(d_weight) if net_weight is not None else None,
            "base_metal_value": float(base_metal),
            "making_charge":    float(d_making),
            "stone_charge":     float(d_stone),
            "taxable_amount":   float(taxable),
            "gst_percentage":   float(d_gst_pct),
            "gst_amount":       float(gst_amount),
            "final_price":      float(final),
            "rate_found":       _rate_found,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Serialization
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def serialize_rate(rate: MetalRate) -> dict:
        """Convert a MetalRate to a JSON-safe dict."""
        return {
            "id":            rate.id,
            "metal_type":    rate.metal_type,
            "purity":        rate.purity,
            "rate_per_gram": float(rate.rate_per_gram),
            "effective_date": rate.effective_date.isoformat() if rate.effective_date else None,
            "source":        rate.source,
            "is_active":     rate.is_active,
            "created_at":    rate.created_at.isoformat() if rate.created_at else None,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Validation
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def validate_rate_data(data: dict, require_all: bool = True) -> list[str]:
        """
        Validate rate input data.

        Args:
            data:        Request body dict.
            require_all: True for POST (required fields must exist).

        Returns:
            List of error messages. Empty = pass.
        """
        errors: list[str] = []

        if require_all:
            if not str(data.get("metal_type", "")).strip():
                errors.append("'metal_type' is required.")
            if data.get("rate_per_gram") is None:
                errors.append("'rate_per_gram' is required.")

        if "rate_per_gram" in data and data["rate_per_gram"] is not None:
            try:
                val = float(data["rate_per_gram"])
                if val <= 0:
                    errors.append("'rate_per_gram' must be a positive number.")
            except (TypeError, ValueError):
                errors.append("'rate_per_gram' must be a valid number.")

        if "effective_date" in data and data["effective_date"]:
            try:
                from datetime import date
                date.fromisoformat(str(data["effective_date"]))
            except ValueError:
                errors.append("'effective_date' must be a valid ISO date (YYYY-MM-DD).")

        return errors
