"""
app/utils/validators.py

Reusable input-validation helpers.

These functions are kept small and stateless so they are easy to test
independently and to reuse across multiple route modules.

Validation rules
----------------
Email
    A simplified RFC-5322 pattern: local@domain.tld
    Rejects obvious non-emails without requiring a heavyweight library.

Phone
    Accepts an optional leading '+' followed by 7–15 digits.
    This covers international E.164 numbers as well as local numbers.
    More granular validation (country-specific) can be added later.

Identifier type
    Must be exactly "email" or "phone" (case-sensitive).

Name
    Non-empty string, max 120 characters (matches User.name column length).

Pincode
    Indian postal code: exactly 6 digits (no letters, no spaces).
    Stored as a string so leading zeros are preserved.
"""

import re

# ── Email ─────────────────────────────────────────────────────────────────────
# Pattern allows:   user+tag@sub.domain.co.uk
# Rejects:          spaces, consecutive dots, missing @, missing TLD
_EMAIL_RE = re.compile(
    r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$"
)

# ── Phone ─────────────────────────────────────────────────────────────────────
# Optional leading '+', then 7–15 digits (ITU-T E.164 range)
_PHONE_RE = re.compile(r"^\+?[0-9]{7,15}$")

# ── Allowed identifier types ──────────────────────────────────────────────────
_VALID_TYPES = {"email", "phone"}


def is_valid_email(value: str) -> bool:
    """
    Return True if *value* looks like a valid email address.

    Args:
        value: The string to validate.

    Returns:
        True if the string matches the email pattern, False otherwise.

    Examples:
        >>> is_valid_email("user@example.com")
        True
        >>> is_valid_email("not-an-email")
        False
    """
    if not isinstance(value, str):
        return False
    return bool(_EMAIL_RE.match(value.strip()))


def is_valid_phone(value: str) -> bool:
    """
    Return True if *value* looks like a valid phone number.

    Accepts optional leading '+' and 7–15 digits.

    Args:
        value: The string to validate.

    Returns:
        True if the string matches the phone pattern, False otherwise.

    Examples:
        >>> is_valid_phone("+919876543210")
        True
        >>> is_valid_phone("9876543210")
        True
        >>> is_valid_phone("abc")
        False
    """
    if not isinstance(value, str):
        return False
    return bool(_PHONE_RE.match(value.strip()))


def is_valid_identifier_type(value: str) -> bool:
    """
    Return True if *value* is an allowed identifier type.

    Args:
        value: Must be "email" or "phone".

    Returns:
        True if the value is in the allowed set, False otherwise.

    Examples:
        >>> is_valid_identifier_type("email")
        True
        >>> is_valid_identifier_type("sms")
        False
    """
    return value in _VALID_TYPES


def is_valid_name(value: str, max_len: int = 120) -> bool:
    """
    Return True if *value* is a usable display name.

    Rules:
    - Must be a non-empty string after stripping whitespace.
    - Must not exceed *max_len* characters (default 120, matching the
      User.name column length).

    Args:
        value:   The candidate name string.
        max_len: Maximum allowed character count (inclusive).

    Returns:
        True if the name passes all checks, False otherwise.

    Examples:
        >>> is_valid_name("John Doe")
        True
        >>> is_valid_name("")
        False
        >>> is_valid_name("A" * 121)
        False
    """
    if not isinstance(value, str):
        return False
    stripped = value.strip()
    return 1 <= len(stripped) <= max_len


# ── Pincode ────────────────────────────────────────────────────────────────────────────────
# Indian postal codes are always exactly 6 decimal digits.
# We store them as strings so a code like "011001" is preserved correctly.
_PINCODE_RE = re.compile(r"^[0-9]{6}$")


def is_valid_pincode(value: str) -> bool:
    """
    Return True if *value* is a valid Indian postal (PIN) code.

    Rules:
    - Must be exactly 6 digits (0–9).
    - No letters, spaces, or hyphens.
    - Stored/validated as a string so leading zeros (e.g. "011001") are
      preserved correctly.

    Args:
        value: The candidate pincode string.

    Returns:
        True if the string is exactly 6 digits, False otherwise.

    Examples:
        >>> is_valid_pincode("700001")
        True
        >>> is_valid_pincode("11001")   # only 5 digits
        False
        >>> is_valid_pincode("70000A")
        False
    """
    if not isinstance(value, str):
        return False
    return bool(_PINCODE_RE.match(value.strip()))
