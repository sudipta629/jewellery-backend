"""
app/utils/admin_decorators.py

Decorator for protecting admin-only endpoints with admin JWTs.

The key difference from the existing `require_admin` decorator
(which allows any ROLE-based token) is that `require_admin_token`
ALSO validates the `sub_type` claim to be "admin".  This ensures
that:

  - A normal customer JWT (sub_type absent or "user") is REJECTED even
    if its role claim happens to be "admin".
  - Only tokens issued by AdminService.build_token_response() are accepted.

Usage
-----
    from app.utils.admin_decorators import require_admin_token

    @bp.get("/some-admin-endpoint")
    @require_admin_token
    def some_handler():
        ...
"""

import logging
from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request

from app.services.admin_service import ADMIN_SUB_TYPE

logger = logging.getLogger(__name__)


def require_admin_token(f):
    """
    Decorator that requires:
      1. A valid, non-expired, non-revoked JWT in the Authorization header.
      2. The JWT must have `sub_type == "admin"` in its additional claims.

    Rejects with 401 for invalid/missing tokens (handled by JWT callbacks).
    Rejects with 403 when the token exists but is a non-admin token.
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()          # handles missing / expired / revoked
        claims  = get_jwt()
        sub_type = claims.get("sub_type", "")

        if sub_type != ADMIN_SUB_TYPE:
            logger.warning(
                "[require_admin_token] Access denied: sub_type=%r on %s",
                sub_type,
                f.__name__,
            )
            return jsonify({
                "status":  "error",
                "message": "Admin authentication required.",
            }), 403

        return f(*args, **kwargs)
    return decorated
