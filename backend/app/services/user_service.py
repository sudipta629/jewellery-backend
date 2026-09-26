"""
app/services/user_service.py

Business logic for user profile management.

Architecture
------------
This service layer sits between the route handlers and the database.
Routes call these methods — no raw SQLAlchemy queries live in route files.

Design decisions
----------------
* Email and phone are authentication identifiers used for OTP delivery.
  Changing them without re-verification would allow a user to lock
  themselves out or impersonate another identifier.  For this step,
  only `name` is updatable.  A dedicated "change email/phone + verify"
  flow belongs to a later step.

* The `serialize_user` method produces a safe dict that explicitly lists
  every field to include.  New columns added to the User model will NOT
  appear in responses until they are deliberately added here.  This
  prevents accidental leakage of sensitive future columns.
"""

import logging

from app.extensions import db
from app.models.user import User
from app.utils.validators import is_valid_name

logger = logging.getLogger(__name__)


class UserService:
    """
    Handles user profile read and update operations.

    All methods are static — no instance state is needed.
    The authenticated user's ID always comes from the JWT, never from
    the request body or query parameters.
    """

    @staticmethod
    def get_user_by_id(user_id: int) -> User | None:
        """
        Fetch a User row by primary key.

        Args:
            user_id: Integer primary key from the JWT identity claim.

        Returns:
            The User instance, or None if the ID does not exist.
        """
        return db.session.get(User, user_id)

    @staticmethod
    def update_profile(user: User, data: dict) -> tuple[User, list[str]]:
        """
        Apply allowed profile updates to *user* and persist them.

        Allowed fields
        --------------
        name : str
            Must be a non-empty string of at most 120 characters.

        Restricted fields (silently ignored even if sent)
        -------------------------------------------------
        email, phone  — require a future OTP re-verification flow.
        id, role, is_verified, created_at, updated_at  — immutable.

        Args:
            user: The authenticated User model instance to update.
            data: Dict of fields from the request body.

        Returns:
            A (updated_user, warnings) tuple.
            `warnings` is a list of human-readable strings explaining
            why certain fields were skipped (e.g. email/phone).
        """
        warnings: list[str] = []
        changed = False

        # ── name ─────────────────────────────────────────────────────────────
        if "name" in data:
            name = str(data["name"]).strip() if data["name"] else ""
            if not is_valid_name(name):
                raise ValueError(
                    "name must be a non-empty string of at most 120 characters."
                )
            if name != user.name:
                user.name = name
                changed = True

        # ── restricted: email ─────────────────────────────────────────────────
        if "email" in data:
            warnings.append(
                "email cannot be changed here. "
                "Use the dedicated email-change flow (coming in a future step)."
            )

        # ── restricted: phone ─────────────────────────────────────────────────
        if "phone" in data:
            warnings.append(
                "phone cannot be changed here. "
                "Use the dedicated phone-change flow (coming in a future step)."
            )

        # ── immutable fields ──────────────────────────────────────────────────
        for field in ("id", "role", "is_verified", "created_at", "updated_at"):
            if field in data:
                warnings.append(
                    f"'{field}' is a read-only field and cannot be modified."
                )

        if changed:
            db.session.commit()
            logger.info("[UserService] Profile updated for user_id=%s", user.id)

        return user, warnings

    @staticmethod
    def serialize_user(user: User) -> dict:
        """
        Convert a User model instance into a safe, JSON-serialisable dict.

        Explicitly lists every included field so that new sensitive columns
        added to the model are NOT accidentally exposed.

        Excluded fields: otp_hash, any future password, JWT secrets.

        Args:
            user: A User model instance.

        Returns:
            A plain dict safe for use in a JSON response body.
        """
        return {
            "id":         user.id,
            "name":       user.name,
            "email":      user.email,
            "phone":      user.phone,
            "role":       user.role,
            "is_verified": user.is_verified,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
