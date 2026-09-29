"""
app/routes/admin_auth_routes.py

Admin authentication endpoints.

Endpoints
---------
POST  /api/v1/admin/login   Authenticate with username + password.
GET   /api/v1/admin/me      Return the authenticated admin's profile.
POST  /api/v1/admin/logout  Revoke the admin's tokens.

Security notes
--------------
* Admin JWTs carry `sub_type = "admin"`.  The `require_admin_token`
  decorator verifies this claim, so a normal user JWT is NEVER accepted
  on these endpoints.
* Credentials are validated through AdminService which uses Werkzeug
  constant-time comparison.
* Login errors are generic — the same message is returned whether the
  username does not exist or the password is wrong, preventing username
  enumeration.
* Rate limiting is enforced on POST /login (5 per minute per IP).
"""

import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from flask_jwt_extended import (
    decode_token,
    get_jwt,
    get_jwt_identity,
)

from app.extensions import db, limiter
from app.models.admin import Admin
from app.models.token_blacklist import TokenBlacklist
from app.services.admin_service import AdminService, ADMIN_SUB_TYPE
from app.services.auth_service import TokenBlacklistService
from app.utils.admin_decorators import require_admin_token

logger = logging.getLogger(__name__)

admin_auth_bp = Blueprint("admin_auth", __name__)

# Generic error used for any failed login attempt.
_LOGIN_ERROR = "Invalid credentials."


# ── POST /login ───────────────────────────────────────────────────────────────

@admin_auth_bp.post("/login")
@limiter.limit("5 per minute")
def admin_login():
    """
    Authenticate an admin with username + password.

    Request body:
        { "username": "...", "password": "..." }

    Success (200):
        { "status": "success", "access_token": "...", "refresh_token": "...", "admin": {...} }

    Errors:
        400 — Missing fields.
        401 — Invalid credentials (generic message, does not reveal existence).
        403 — Account disabled.
    """
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"status": "error", "message": "Request body must be JSON."}), 400

    username = str(data.get("username", "")).strip()
    password = str(data.get("password", "")).strip()

    if not username or not password:
        return jsonify({"status": "error", "message": "username and password are required."}), 400

    admin = AdminService.authenticate(username, password)

    if admin is None:
        logger.warning("[AdminAuth] Failed login attempt for username=%r", username)
        return jsonify({"status": "error", "message": _LOGIN_ERROR}), 401

    if not admin.is_active:
        logger.warning("[AdminAuth] Login attempt on disabled account id=%s", admin.id)
        return jsonify({"status": "error", "message": "Admin account is disabled."}), 403

    token_data = AdminService.build_token_response(admin)
    logger.info("[AdminAuth] Admin id=%s logged in successfully.", admin.id)

    return jsonify({"status": "success", **token_data}), 200


# ── GET /me ───────────────────────────────────────────────────────────────────

@admin_auth_bp.get("/me")
@require_admin_token
def admin_me():
    """
    Return the currently authenticated admin's profile.

    Requires a valid admin access token in the Authorization header.

    Response (200):
        { "status": "success", "admin": { "id": ..., "username": ..., ... } }
    """
    identity = get_jwt_identity()   # "admin:<id>"
    try:
        admin_id = int(identity.split(":")[1])
    except (IndexError, ValueError):
        return jsonify({"status": "error", "message": "Invalid token identity."}), 401

    admin = db.session.get(Admin, admin_id)
    if admin is None:
        return jsonify({"status": "error", "message": "Admin not found."}), 404

    if not admin.is_active:
        return jsonify({"status": "error", "message": "Admin account is disabled."}), 403

    return jsonify({"status": "success", "admin": admin.to_safe_dict()}), 200


# ── POST /logout ──────────────────────────────────────────────────────────────

@admin_auth_bp.post("/logout")
@require_admin_token
def admin_logout():
    """
    Revoke the current admin access token (and optionally the refresh token).

    Optional request body:
        { "refresh_token": "<refresh_token_string>" }

    Response (200):
        { "status": "success", "message": "Logged out successfully." }
    """
    jwt_payload   = get_jwt()
    jti           = jwt_payload["jti"]
    exp_timestamp = jwt_payload.get("exp")
    expires_at    = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    # Revoke access token — admin_id is stored as None since the token
    # identity is "admin:<id>" rather than an integer user_id.
    TokenBlacklistService.revoke_token(
        jti=jti,
        token_type="access",
        expires_at=expires_at,
        user_id=None,
    )

    # Optionally revoke the refresh token too.
    body = request.get_json(silent=True) or {}
    refresh_token_str = body.get("refresh_token", "")
    if refresh_token_str:
        try:
            refresh_payload = decode_token(refresh_token_str)
            if refresh_payload.get("type") == "refresh":
                r_jti    = refresh_payload["jti"]
                r_exp    = refresh_payload.get("exp")
                r_expiry = datetime.fromtimestamp(r_exp, tz=timezone.utc)
                TokenBlacklistService.revoke_token(
                    jti=r_jti,
                    token_type="refresh",
                    expires_at=r_expiry,
                    user_id=None,
                )
        except Exception:
            logger.warning("[AdminAuth] Could not decode refresh token on logout — ignored.")

    return jsonify({"status": "success", "message": "Logged out successfully."}), 200
