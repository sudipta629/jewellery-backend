"""
app/routes/auth.py

Passwordless OTP authentication blueprint.

Endpoints
---------
POST  /api/v1/auth/request-otp   Generate and (in dev) return an OTP
POST  /api/v1/auth/verify-otp    Verify the OTP and issue JWT tokens
POST  /api/v1/auth/refresh        Exchange a refresh token for a new access token
GET   /api/v1/auth/me             Return the currently authenticated user's profile
POST  /api/v1/auth/logout         Revoke the current access (and optionally refresh) token

Security notes
--------------
* OTP is NEVER stored in plain text (handled by OTPService).
* In production (FLASK_ENV != "development") the OTP is never included
  in the API response, nor printed to logs.
* User enumeration is avoided in the production request-otp response —
  the same generic message is returned whether the identifier exists or not.
* JWT secret is read from config, never hard-coded here.
* Expired and locked OTPs are rejected before any hash comparison.

Rate limiting
-------------
Per-IP rate limits are enforced by Flask-Limiter on the two most
sensitive endpoints:
  - /request-otp : 5 requests per minute
  - /verify-otp  : 10 requests per minute
Limits are disabled automatically in the test environment
(RATELIMIT_ENABLED=False in TestingConfig).

Logout / token revocation
-------------------------
Server-side token blacklisting is implemented via the `token_blacklist`
database table.  On logout the access token's jti is stored there.
If the client also provides the refresh token in the request body,
that is revoked too.  The `token_in_blocklist_loader` in app/__init__.py
checks every protected request against this table.
"""

import os
import logging
from datetime import datetime, timezone

from flask import Blueprint, current_app, jsonify, request
from flask_jwt_extended import (
    create_access_token,
    get_jwt,
    get_jwt_identity,
    jwt_required,
    decode_token,
)

from app.extensions import db, limiter
from app.models.user import User
from app.services.auth_service import AuthService, OTPService, TokenBlacklistService
from app.services.email_service import EmailService
from app.utils.validators import (
    is_valid_email,
    is_valid_identifier_type,
    is_valid_phone,
)

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_development() -> bool:
    """Return True only when running in development mode."""
    return os.environ.get("FLASK_ENV", "development").lower() == "development"


def _validate_identifier_request(data: dict) -> tuple[str | None, str | None, dict | None]:
    """
    Validate a request body containing `identifier` and `identifier_type`.

    Returns:
        (identifier, identifier_type, error_response)
        error_response is None on success, or a (jsonify(...), status_code)
        tuple on validation failure.
    """
    if not data:
        return None, None, (
            jsonify({"status": "error", "message": "Request body must be JSON."}),
            400,
        )

    identifier = data.get("identifier", "").strip()
    identifier_type = data.get("identifier_type", "").strip()

    if not identifier:
        return None, None, (
            jsonify({"status": "error", "message": "identifier is required."}),
            400,
        )

    if not is_valid_identifier_type(identifier_type):
        return None, None, (
            jsonify({
                "status": "error",
                "message": "identifier_type must be 'email' or 'phone'.",
            }),
            400,
        )

    if identifier_type == "email" and not is_valid_email(identifier):
        return None, None, (
            jsonify({"status": "error", "message": "Invalid email address format."}),
            400,
        )

    if identifier_type == "phone" and not is_valid_phone(identifier):
        return None, None, (
            jsonify({
                "status": "error",
                "message": (
                    "Invalid phone number format. "
                    "Use digits only, optionally prefixed with '+' (7–15 digits total)."
                ),
            }),
            400,
        )

    return identifier, identifier_type, None


# ── POST /request-otp ─────────────────────────────────────────────────────────

@auth_bp.post("/request-otp")
@limiter.limit("5 per minute")
def request_otp():
    """
    Generate an OTP for the given identifier.

    Request body:
        {
            "identifier": "user@example.com",
            "identifier_type": "email"
        }

    Development response (FLASK_ENV=development):
        {
            "status": "success",
            "message": "OTP generated successfully",
            "development_only": true,
            "otp": "123456"
        }

    Production response (FLASK_ENV=production):
        {
            "status": "success",
            "message": "If the identifier is valid, an OTP has been sent."
        }

    HTTP status codes:
        200 — OTP generated (or production generic response)
        400 — Invalid request body
    """
    data = request.get_json(silent=True)
    identifier, identifier_type, err = _validate_identifier_request(data)
    if err:
        return err

    # Create the OTP record (invalidates any previous pending OTPs).
    otp_record = OTPService.create_otp_record(identifier, identifier_type)
    plaintext_otp = getattr(otp_record, "_plaintext_otp", None)

    # ── Send Email OTP ────────────────────────────────────────────────────────
    if identifier_type == "email" and plaintext_otp:
        # In production, this should ideally be dispatched to a background queue
        # (like Celery/Redis) to avoid blocking the HTTP response on SMTP latency.
        # But for this implementation, we handle it synchronously.
        EmailService.send_otp_email(identifier, plaintext_otp)

    # ── Development-only: expose OTP in the response ──────────────────────────
    # This block is ONLY executed when FLASK_ENV=development.
    # In production this branch is never entered, so the OTP is never
    # included in the response body.
    if _is_development():
        return jsonify({
            "status": "success",
            "message": "OTP generated successfully.",
            "development_only": True,
            "otp": plaintext_otp,
        }), 200

    # ── Production: generic response — no OTP, no enumeration ────────────────
    return jsonify({
        "status": "success",
        "message": "If the identifier is valid, an OTP has been sent.",
    }), 200


# ── POST /verify-otp ──────────────────────────────────────────────────────────

@auth_bp.post("/verify-otp")
@limiter.limit("10 per minute")
def verify_otp():
    """
    Verify the submitted OTP and issue JWT tokens on success.

    If the user does not exist yet, a new customer account is created
    automatically (first-time login flow).

    Request body:
        {
            "identifier": "user@example.com",
            "identifier_type": "email",
            "otp": "123456"
        }

    Success response (200):
        {
            "status": "success",
            "message": "Authentication successful.",
            "access_token": "...",
            "refresh_token": "...",
            "user": {
                "id": 1,
                "name": "New Customer",
                "email": "user@example.com",
                "phone": null,
                "role": "customer",
                "is_verified": true
            }
        }

    Error responses:
        400 — Invalid request body / missing fields
        401 — OTP is invalid, expired, or all attempts exhausted
        429 — (reserved for future rate limiting)
    """
    data = request.get_json(silent=True)
    identifier, identifier_type, err = _validate_identifier_request(data)
    if err:
        return err

    # Validate OTP field presence and format.
    submitted_otp = str(data.get("otp", "")).strip()
    if not submitted_otp:
        return jsonify({"status": "error", "message": "otp is required."}), 400
    if not submitted_otp.isdigit() or len(submitted_otp) != 6:
        return jsonify({
            "status": "error",
            "message": "otp must be a 6-digit number.",
        }), 400

    # ── Find a valid OTP record ───────────────────────────────────────────────
    otp_record = OTPService.find_valid_otp(identifier, identifier_type)

    if otp_record is None:
        # Could be: no OTP was ever requested, OTP expired, or all attempts used.
        # We return a single generic message to avoid enumeration.
        return jsonify({
            "status": "error",
            "message": (
                "No valid OTP found. The OTP may have expired or been "
                "used too many times. Please request a new OTP."
            ),
        }), 401

    # ── Verify the OTP against the stored hash ────────────────────────────────
    success, message = OTPService.verify_and_consume(otp_record, submitted_otp)

    if not success:
        # Distinguish between attempt-limit reached (429-ish) and plain wrong OTP.
        if otp_record.is_locked:
            return jsonify({
                "status": "error",
                "message": "Maximum verification attempts reached. Please request a new OTP.",
            }), 429
        return jsonify({"status": "error", "message": message}), 401

    # ── OTP is valid — find or create the user ────────────────────────────────
    user, was_created = AuthService.get_or_create_user(identifier, identifier_type)

    # ── Build token response ──────────────────────────────────────────────────
    token_data = AuthService.build_token_response(user)

    response_body = {
        "status": "success",
        "message": "Authentication successful.",
        **token_data,
    }
    if was_created:
        response_body["new_user"] = True  # hint to the frontend to show profile setup

    return jsonify(response_body), 200


# ── POST /refresh ─────────────────────────────────────────────────────────────

@auth_bp.post("/refresh")
@jwt_required(refresh=True)
def refresh():
    """
    Issue a new access token using a valid refresh token.

    The refresh token must be sent in the Authorization header:
        Authorization: Bearer <refresh_token>

    Response (200):
        {
            "status": "success",
            "access_token": "..."
        }

    Error responses:
        401 — Missing, invalid, or expired refresh token
    """
    identity = get_jwt_identity()
    claims = get_jwt()
    role = claims.get("role", "customer")

    new_access_token = create_access_token(
        identity=identity,
        additional_claims={"role": role},
    )
    return jsonify({
        "status": "success",
        "access_token": new_access_token,
    }), 200


# ── GET /me ───────────────────────────────────────────────────────────────────

@auth_bp.get("/me")
@jwt_required()
def me():
    """
    Return the currently authenticated user's profile.

    Requires a valid access token in the Authorization header:
        Authorization: Bearer <access_token>

    Response (200):
        {
            "status": "success",
            "user": {
                "id": 1,
                "name": "...",
                "email": "...",
                "phone": "...",
                "role": "customer",
                "is_verified": true
            }
        }

    Error responses:
        401 — Missing or invalid access token
        404 — User ID from token does not exist in the database
    """
    user_id = get_jwt_identity()

    user = db.session.get(User, int(user_id))
    if user is None:
        return jsonify({
            "status": "error",
            "message": "User not found.",
        }), 404

    return jsonify({
        "status": "success",
        "user": {
            "id": user.id,
            "name": user.name,
            "email": user.email,
            "phone": user.phone,
            "role": user.role,
            "is_verified": user.is_verified,
        },
    }), 200


# ── POST /logout ──────────────────────────────────────────────────────────────────

@auth_bp.post("/logout")
@jwt_required()
def logout():
    """
    Revoke the current access token (and optionally the refresh token).

    The access token's `jti` is always stored in the token blacklist.
    If the client also sends its refresh token in the request body,
    that is revoked too — preventing the user from obtaining a new
    access token after logout.

    Requires a valid access token in the Authorization header:
        Authorization: Bearer <access_token>

    Optional request body:
        {
            "refresh_token": "<refresh_token_string>"
        }

    Response (200):
        {
            "status": "success",
            "message": "Logged out successfully."
        }

    Error responses:
        401 — Missing or invalid access token
    """
    jwt_payload = get_jwt()
    jti          = jwt_payload["jti"]
    user_id_str  = get_jwt_identity()
    user_id      = int(user_id_str) if user_id_str else None

    # Convert the exp timestamp (Unix epoch int) to a datetime for storage.
    exp_timestamp = jwt_payload.get("exp")
    expires_at    = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)

    # ── Revoke access token ──────────────────────────────────────────────────
    TokenBlacklistService.revoke_token(
        jti=jti,
        token_type="access",
        expires_at=expires_at,
        user_id=user_id,
    )

    # ── Optionally revoke the refresh token too ──────────────────────────────
    # This prevents the client from silently refreshing after logout.
    data = request.get_json(silent=True) or {}
    refresh_token_str = data.get("refresh_token", "")

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
                    user_id=user_id,
                )
        except Exception:
            # If the refresh token is malformed or already expired, ignore it.
            # The access token is already revoked, so logout still succeeds.
            logger.warning(
                "[logout] Could not decode refresh token for user_id=%s — ignored.",
                user_id,
            )

    return jsonify({
        "status": "success",
        "message": "Logged out successfully.",
    }), 200
