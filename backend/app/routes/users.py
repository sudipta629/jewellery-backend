"""
app/routes/users.py

User profile blueprint.

Endpoints
---------
GET  /api/v1/users/me   Return the authenticated user's own profile.
PUT  /api/v1/users/me   Update the authenticated user's own profile.

Security model
--------------
* Both endpoints require a valid JWT access token.
* The user ID is ALWAYS taken from the JWT identity claim — never from
  the request body, query parameters, or URL path.
* This means a user can only ever read or modify their OWN profile.

Update restrictions
-------------------
* Only `name` can be updated in this endpoint.
* `email` and `phone` are authentication identifiers that require a
  dedicated OTP re-verification flow before they can be changed.
  That flow is planned for a later step.  For now, attempting to change
  email/phone returns a 200 with a warning in the response (not an error,
  since the update itself still succeeds for the `name` field).
* `id`, `role`, `is_verified`, `created_at`, `updated_at` are read-only.
  Sending them in the body is silently ignored and a warning is returned.
"""

import logging

from flask import Blueprint, jsonify, request
from flask_jwt_extended import get_jwt_identity, jwt_required

from app.services.user_service import UserService

logger = logging.getLogger(__name__)

users_bp = Blueprint("users", __name__)


# ── GET /me ───────────────────────────────────────────────────────────────────

@users_bp.get("/me")
@jwt_required()
def get_profile():
    """
    Return the authenticated user's own profile.

    The user's ID is extracted from the JWT — the client cannot choose
    whose profile to view.

    Response (200):
        {
            "status": "success",
            "user": {
                "id": 1,
                "name": "John Doe",
                "email": "john@example.com",
                "phone": "9876543210",
                "role": "customer",
                "is_verified": true,
                "created_at": "...",
                "updated_at": "..."
            }
        }

    Error responses:
        401 — Missing or invalid JWT
        404 — User no longer exists in the database
    """
    user_id = int(get_jwt_identity())
    user    = UserService.get_user_by_id(user_id)

    if user is None:
        return jsonify({
            "status":  "error",
            "message": "User not found.",
        }), 404

    return jsonify({
        "status": "success",
        "user":   UserService.serialize_user(user),
    }), 200


# ── PUT /me ───────────────────────────────────────────────────────────────────

@users_bp.put("/me")
@jwt_required()
def update_profile():
    """
    Update the authenticated user's own profile.

    Only `name` can be changed through this endpoint.

    Request body (JSON):
        {
            "name": "New Name"
        }

    Success response (200):
        {
            "status":  "success",
            "message": "Profile updated successfully.",
            "user":    { ... },
            "warnings": []          ← populated if restricted fields were sent
        }

    Error responses:
        400 — Validation error (e.g. empty name, name too long)
        401 — Missing or invalid JWT
        404 — User no longer exists in the database
    """
    user_id = int(get_jwt_identity())
    user    = UserService.get_user_by_id(user_id)

    if user is None:
        return jsonify({
            "status":  "error",
            "message": "User not found.",
        }), 404

    data = request.get_json(silent=True)
    if not data:
        return jsonify({
            "status":  "error",
            "message": "Request body must be JSON.",
        }), 400

    try:
        updated_user, warnings = UserService.update_profile(user, data)
    except ValueError as exc:
        return jsonify({
            "status":  "error",
            "message": str(exc),
        }), 400

    response_body = {
        "status":   "success",
        "message":  "Profile updated successfully.",
        "user":     UserService.serialize_user(updated_user),
    }
    if warnings:
        response_body["warnings"] = warnings

    return jsonify(response_body), 200
