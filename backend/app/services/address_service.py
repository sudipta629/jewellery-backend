"""
app/services/address_service.py

Business logic for address management.

Architecture
------------
    routes/addresses.py
        ↓  calls
    AddressService  (this file)
        ↓  queries
    Address model / db.session

Security model
--------------
* Every query that touches an address row includes BOTH the address ID
  and the authenticated user's ID from the JWT.
* The frontend can NEVER supply a user_id — it is always taken from
  the JWT identity.

Default address rules
---------------------
1. A user may have at most ONE default address at any time.
2. When any address is set as default, all OTHER addresses of that user
   are atomically set to non-default in the same transaction.
3. First address created by a user is ALWAYS made default automatically,
   regardless of the is_default value in the request.
4. When the default address is deleted:
   - If other addresses exist, the one with the lowest `id` (oldest)
     becomes the new default.
   - If no other addresses exist, nothing more needs to be done.
"""

import logging

from app.extensions import db
from app.models.address import Address
from app.utils.validators import is_valid_name, is_valid_phone, is_valid_pincode

logger = logging.getLogger(__name__)

# ── Required fields for creating a new address ────────────────────────────────
_REQUIRED_FIELDS = ("full_name", "phone", "address_line", "city", "state", "pincode")

# ── Maximum lengths matching the Address model column definitions ─────────────
_MAX_LENGTHS = {
    "full_name":    120,
    "address_line": 255,
    "city":         100,
    "state":        100,
    "pincode":       10,
}


class AddressService:
    """
    Handles all address CRUD operations and default-address logic.

    All methods are static — no instance state is needed.
    """

    # ══════════════════════════════════════════════════════════════════════════
    # Serialization
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def serialize_address(address: Address) -> dict:
        """
        Convert an Address model instance into a JSON-safe dict.

        Args:
            address: An Address model instance.

        Returns:
            A plain dict with all address fields.
        """
        return {
            "id":           address.id,
            "full_name":    address.full_name,
            "phone":        address.phone,
            "address_line": address.address_line,
            "city":         address.city,
            "state":        address.state,
            "pincode":      address.pincode,
            "is_default":   address.is_default,
            "created_at":   address.created_at.isoformat() if address.created_at else None,
            "updated_at":   address.updated_at.isoformat() if address.updated_at else None,
        }

    # ══════════════════════════════════════════════════════════════════════════
    # Validation
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def validate_address_data(data: dict, require_all: bool = True) -> list[str]:
        """
        Validate address field values.

        Args:
            data:        Dict of address fields from the request body.
            require_all: If True, all required fields must be present
                         (used for POST).  If False, only fields that
                         ARE present are validated (used for PUT).

        Returns:
            A list of human-readable error messages.
            Empty list means validation passed.
        """
        errors: list[str] = []

        if require_all:
            for field in _REQUIRED_FIELDS:
                if field not in data or not str(data.get(field, "")).strip():
                    errors.append(f"'{field}' is required.")

        # ── full_name ─────────────────────────────────────────────────────────
        if "full_name" in data:
            if not is_valid_name(str(data["full_name"]), max_len=120):
                errors.append(
                    "full_name must be a non-empty string of at most 120 characters."
                )

        # ── phone ──────────────────────────────────────────────────────────────
        if "phone" in data:
            if not is_valid_phone(str(data["phone"])):
                errors.append(
                    "phone must contain 7\u201315 digits, optionally prefixed with '+'."
                )

        # ── pincode ───────────────────────────────────────────────────────────
        if "pincode" in data:
            if not is_valid_pincode(str(data["pincode"])):
                errors.append("pincode must be exactly 6 digits (e.g. '700001').")

        # ── max-length checks for free-text fields ────────────────────────────
        for field, max_len in _MAX_LENGTHS.items():
            if field in data and field not in ("full_name", "pincode"):
                value = str(data[field]).strip()
                if len(value) > max_len:
                    errors.append(
                        f"'{field}' must not exceed {max_len} characters."
                    )

        return errors

    # ══════════════════════════════════════════════════════════════════════════
    # Default address helpers
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def _clear_defaults(user_id: int, except_address_id: int | None = None) -> None:
        """
        Set is_default=False for all addresses owned by *user_id*,
        optionally excluding one address by ID.

        Called inside the same transaction as the operation that sets a
        new default, guaranteeing atomicity.

        Args:
            user_id:           The owner whose addresses to update.
            except_address_id: ID of the address that should keep its
                               current value (the new default).
        """
        query = Address.query.filter_by(user_id=user_id, is_default=True)
        if except_address_id is not None:
            query = query.filter(Address.id != except_address_id)
        for addr in query.all():
            addr.is_default = False
        # Caller is responsible for committing the transaction.

    # ══════════════════════════════════════════════════════════════════════════
    # CRUD
    # ══════════════════════════════════════════════════════════════════════════

    @staticmethod
    def get_addresses(user_id: int) -> list[Address]:
        """
        Return all addresses belonging to *user_id*, newest first.

        Args:
            user_id: JWT-derived authenticated user ID.

        Returns:
            List of Address instances (may be empty).
        """
        return (
            Address.query
            .filter_by(user_id=user_id)
            .order_by(Address.id.desc())
            .all()
        )

    @staticmethod
    def get_address_owned_by(address_id: int, user_id: int) -> Address | None:
        """
        Fetch an address only if it belongs to *user_id*.

        This is the ownership-check query used by update and delete.
        If the address belongs to a different user, None is returned —
        the same response as "not found" to prevent user enumeration.

        Args:
            address_id: The address PK from the URL path.
            user_id:    JWT-derived authenticated user ID.

        Returns:
            The Address instance, or None if not found / not owned.
        """
        return Address.query.filter_by(
            id=address_id,
            user_id=user_id,
        ).first()

    @staticmethod
    def create_address(user_id: int, data: dict) -> Address:
        """
        Create a new address for *user_id*.

        Default-address rules applied here:
        1. If this is the user's first address, it is made default
           regardless of the `is_default` value in *data*.
        2. If `is_default=True` in *data*, all existing addresses of
           the user are set to non-default first.

        Args:
            user_id: JWT-derived authenticated user ID.
            data:    Validated request body dict.

        Returns:
            The newly created Address instance.
        """
        # Count existing addresses for this user.
        existing_count = Address.query.filter_by(user_id=user_id).count()
        is_first = existing_count == 0

        # Determine if this address should be default.
        wants_default = bool(data.get("is_default", False))
        make_default = is_first or wants_default

        # Clear existing defaults if we're making this the new default.
        if make_default:
            AddressService._clear_defaults(user_id)

        address = Address(
            user_id=user_id,
            full_name=str(data["full_name"]).strip(),
            phone=str(data["phone"]).strip(),
            address_line=str(data["address_line"]).strip(),
            city=str(data["city"]).strip(),
            state=str(data["state"]).strip(),
            pincode=str(data["pincode"]).strip(),
            is_default=make_default,
        )
        db.session.add(address)
        db.session.commit()

        logger.info(
            "[AddressService] Address created: id=%s user_id=%s default=%s",
            address.id, user_id, make_default,
        )
        return address

    @staticmethod
    def update_address(address: Address, data: dict) -> Address:
        """
        Apply partial updates to an address row.

        Only fields present in *data* are updated.  The `user_id` field
        is never touched regardless of what *data* contains.

        Default-address rule:
        If `is_default=True` is set, all other addresses of the same
        user are set to non-default atomically.

        Args:
            address: The Address instance to update (already ownership-
                     checked by the route).
            data:    Partial dict of fields to update.

        Returns:
            The updated Address instance.
        """
        wants_default = data.get("is_default")

        if wants_default is True:
            # Clear existing defaults for this user, excluding this address.
            AddressService._clear_defaults(address.user_id, except_address_id=address.id)
            address.is_default = True
        elif wants_default is False:
            address.is_default = False

        # Update remaining fields if present.
        simple_fields = ("full_name", "phone", "address_line", "city", "state", "pincode")
        for field in simple_fields:
            if field in data:
                setattr(address, field, str(data[field]).strip())

        db.session.commit()
        logger.info("[AddressService] Address updated: id=%s", address.id)
        return address

    @staticmethod
    def delete_address(address: Address) -> None:
        """
        Delete an address.

        If the deleted address was the default, the oldest remaining
        address (lowest `id`) of the same user is automatically made
        the new default.  This ensures the user always has a default
        address as long as they have at least one saved address.

        Args:
            address: The Address instance to delete (already ownership-
                     checked by the route).
        """
        user_id       = address.user_id
        was_default   = address.is_default
        address_id    = address.id

        db.session.delete(address)
        db.session.flush()  # execute DELETE before querying for a replacement

        if was_default:
            # Find the next-oldest address for this user.
            replacement = (
                Address.query
                .filter(Address.user_id == user_id, Address.id != address_id)
                .order_by(Address.id.asc())
                .first()
            )
            if replacement:
                replacement.is_default = True
                logger.info(
                    "[AddressService] Default re-assigned to address id=%s for user_id=%s",
                    replacement.id, user_id,
                )

        db.session.commit()
        logger.info("[AddressService] Address deleted: id=%s user_id=%s", address_id, user_id)
