"""
app/utils/decorators.py

Reusable route decorators for authentication and role-based access control.

Role Hierarchy
--------------
    super_admin      — Full access to everything, including staff management.
    admin            — Full access to store operations.
    sales_staff      — Order management, customer management, KYC.
    inventory_staff  — Product/inventory management, rates.
    customer         — Customer-facing APIs only.

Admin roles (any staff member):
    super_admin, admin, sales_staff, inventory_staff

Decorators
----------
    require_auth          — JWT required (any role).
    require_admin         — JWT + any admin role.
    require_super_admin   — JWT + super_admin only.
    require_role(*roles)  — JWT + specific role(s).
"""

import logging
from functools import wraps

from flask import jsonify
from flask_jwt_extended import get_jwt, verify_jwt_in_request

logger = logging.getLogger(__name__)

# ── Role constants ─────────────────────────────────────────────────────────────
ROLE_SUPER_ADMIN     = "super_admin"
ROLE_ADMIN           = "admin"
ROLE_SALES_STAFF     = "sales_staff"
ROLE_INVENTORY_STAFF = "inventory_staff"
ROLE_CUSTOMER        = "customer"

# Set of all roles that can access /api/v1/admin/* endpoints
ADMIN_ROLES = {ROLE_SUPER_ADMIN, ROLE_ADMIN, ROLE_SALES_STAFF, ROLE_INVENTORY_STAFF}


def _forbidden(role: str, endpoint: str, required_roles: set | list) -> tuple:
    """Return a consistent 403 response."""
    logger.warning(
        "[RBAC] Access denied: role=%r endpoint=%r required=%r",
        role, endpoint, required_roles,
    )
    return jsonify({
        "status":  "error",
        "message": "You do not have permission to access this resource.",
    }), 403


# ── require_auth ──────────────────────────────────────────────────────────────

def require_auth(f):
    """
    Route decorator that requires a valid JWT (any role).

    Use this on endpoints that any authenticated user (customer or admin)
    can access.

    Behaviour
    ---------
    1. Calls verify_jwt_in_request() — handles missing/expired/revoked tokens
       exactly like @jwt_required().
    2. Calls the original route function if the token is valid.

    Usage
    -----
    @bp.get("/some-endpoint")
    @require_auth
    def some_endpoint():
        ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        return f(*args, **kwargs)
    return decorated


# ── require_admin ─────────────────────────────────────────────────────────────

def require_admin(f):
    """
    Route decorator that requires a valid JWT **and** any admin role.

    Allowed roles: super_admin, admin, sales_staff, inventory_staff.
    Customers (role == 'customer') are rejected with 403.

    Behaviour
    ---------
    1. Calls verify_jwt_in_request() — handles missing/expired/revoked tokens.
    2. Reads the `role` claim from the decoded token.
    3. Returns 403 Forbidden if the role is not in ADMIN_ROLES.
    4. Calls the original route function if the check passes.

    Usage
    -----
    @admin_bp.post("/categories")
    @require_admin
    def create_category():
        ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        role   = claims.get("role", "")

        if role not in ADMIN_ROLES:
            return _forbidden(role, f.__name__, ADMIN_ROLES)

        return f(*args, **kwargs)
    return decorated


# ── require_super_admin ───────────────────────────────────────────────────────

def require_super_admin(f):
    """
    Route decorator that requires a valid JWT **and** role == 'super_admin'.

    Use this for the most sensitive operations:
    - Staff management (create/delete admin accounts)
    - Store settings changes
    - Permanent hard-deletes

    Usage
    -----
    @admin_bp.delete("/staff/<id>")
    @require_super_admin
    def delete_staff(id):
        ...
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        verify_jwt_in_request()
        claims = get_jwt()
        role   = claims.get("role", "")

        if role != ROLE_SUPER_ADMIN:
            return _forbidden(role, f.__name__, {ROLE_SUPER_ADMIN})

        return f(*args, **kwargs)
    return decorated


# ── require_role ──────────────────────────────────────────────────────────────

def require_role(*allowed_roles: str):
    """
    Route decorator factory that requires a valid JWT **and** one of the
    specified roles.

    Args:
        *allowed_roles: One or more role strings from the ROLE_* constants.

    Usage
    -----
    @admin_bp.put("/inventory/<id>/adjust")
    @require_role(ROLE_ADMIN, ROLE_SUPER_ADMIN, ROLE_INVENTORY_STAFF)
    def adjust_inventory(id):
        ...
    """
    allowed = set(allowed_roles)

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            verify_jwt_in_request()
            claims = get_jwt()
            role   = claims.get("role", "")

            if role not in allowed:
                return _forbidden(role, f.__name__, allowed)

            return f(*args, **kwargs)
        return decorated
    return decorator
