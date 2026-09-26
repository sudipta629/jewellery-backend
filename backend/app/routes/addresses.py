"""
app/routes/addresses.py

Address management blueprint.

Endpoints
---------
GET    /api/v1/addresses              List the authenticated user's addresses.
POST   /api/v1/addresses              Create a new address.
PUT    /api/v1/addresses/<address_id> Update an address (own only).
DELETE /api/v1/addresses/<address_id> Delete an address (own only).

Security model
--------------
* All endpoints require a valid JWT access token.
* The authenticated user's ID is taken exclusively from the JWT identity.
  The client CANNOT supply a user_id in the request body or URL.
* For update and delete, the address is fetched with BOTH its id AND the
  JWT user_id.  This means an attempt to touch another user's address
  returns 404 (same as "not found") — preventing user enumeration.

Default address behaviour
-------------------------
* First address created is automatically made default.
* Setting is_default=True on create or update clears all other defaults
  for the same user atomically.
* Deleting the default address automatically promotes the oldest
  remaining address to default.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services.address_service import AddressService

logger = logging.getLogger(__name__)

addresses_bp = Blueprint("addresses", __name__)


# ── GET / ─────────────────────────────────────────────────────────────────────

@addresses_bp.get("/")
@jwt_required()
def list_addresses():
    """
    Return all addresses belonging to the authenticated user.

    Response (200):
        {
            "status":    "success",
            "addresses": [ { ... }, ... ]
        }

    Error responses:
        401 — Missing or invalid JWT
    """
    user_id   = int(get_jwt_identity())
    addresses = AddressService.get_addresses(user_id)

    return jsonify({
        "status":    "success",
        "addresses": [AddressService.serialize_address(a) for a in addresses],
    }), 200


# ── POST / ────────────────────────────────────────────────────────────────────

@addresses_bp.post("/")
@jwt_required()
def create_address():
    """
    Create a new address for the authenticated user.

    Required fields: full_name, phone, address_line, city, state, pincode.
    Optional fields: is_default (boolean, default false).

    The backend always sets user_id from the JWT — never from the request.

    First-address rule: if this is the user's first address, it is
    automatically made the default regardless of the is_default value.

    Request body:
        {
            "full_name":    "John Doe",
            "phone":        "9876543210",
            "address_line": "123 Main Road",
            "city":         "Kolkata",
            "state":        "West Bengal",
            "pincode":      "700001",
            "is_default":   false
        }

    Response (201):
        {
            "status":  "success",
            "message": "Address created successfully.",
            "address": { ... }
        }

    Error responses:
        400 — Missing or invalid fields
        401 — Missing or invalid JWT
    """
    user_id = int(get_jwt_identity())
    data    = request.get_json(silent=True)

    if not data:
        return jsonify({
            "status":  "error",
            "message": "Request body must be JSON.",
        }), 400

    errors = AddressService.validate_address_data(data, require_all=True)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    address = AddressService.create_address(user_id, data)

    return jsonify({
        "status":  "success",
        "message": "Address created successfully.",
        "address": AddressService.serialize_address(address),
    }), 201


# ── PUT /<address_id> ─────────────────────────────────────────────────────────

@addresses_bp.put("/<int:address_id>")
@jwt_required()
def update_address(address_id: int):
    """
    Update an address that belongs to the authenticated user.

    All fields are optional — only those present in the body are updated.

    Ownership rule: if address_id belongs to a different user, 404 is
    returned (same as "not found") to prevent enumeration.

    Request body (all fields optional):
        {
            "full_name":    "Jane Doe",
            "phone":        "9876543210",
            "address_line": "456 New Road",
            "city":         "Mumbai",
            "state":        "Maharashtra",
            "pincode":      "400001",
            "is_default":   true
        }

    Response (200):
        {
            "status":  "success",
            "message": "Address updated successfully.",
            "address": { ... }
        }

    Error responses:
        400 — Validation error
        401 — Missing or invalid JWT
        404 — Address not found or not owned by the authenticated user
    """
    user_id = int(get_jwt_identity())
    address = AddressService.get_address_owned_by(address_id, user_id)

    if address is None:
        return jsonify({
            "status":  "error",
            "message": "Address not found.",
        }), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "status":  "error",
            "message": "Request body must be JSON.",
        }), 400

    errors = AddressService.validate_address_data(data, require_all=False)
    if errors:
        return jsonify({
            "status":  "error",
            "message": errors[0] if len(errors) == 1 else "Validation failed.",
            "errors":  errors,
        }), 400

    updated = AddressService.update_address(address, data)

    return jsonify({
        "status":  "success",
        "message": "Address updated successfully.",
        "address": AddressService.serialize_address(updated),
    }), 200


# ── DELETE /<address_id> ──────────────────────────────────────────────────────

@addresses_bp.delete("/<int:address_id>")
@jwt_required()
def delete_address(address_id: int):
    """
    Delete an address that belongs to the authenticated user.

    Ownership rule: returns 404 if the address does not belong to the
    authenticated user (prevents enumeration).

    Default-address rule: if the deleted address was the default, the
    oldest remaining address automatically becomes the new default.

    Response (200):
        {
            "status":  "success",
            "message": "Address deleted successfully."
        }

    Error responses:
        401 — Missing or invalid JWT
        404 — Address not found or not owned by the authenticated user
    """
    user_id = int(get_jwt_identity())
    address = AddressService.get_address_owned_by(address_id, user_id)

    if address is None:
        return jsonify({
            "status":  "error",
            "message": "Address not found.",
        }), 404

    AddressService.delete_address(address)

    return jsonify({
        "status":  "success",
        "message": "Address deleted successfully.",
    }), 200
