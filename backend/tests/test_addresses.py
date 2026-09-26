"""
tests/test_addresses.py

Test suite for the Address Management endpoints.

Endpoints tested
----------------
GET    /api/v1/addresses
POST   /api/v1/addresses
PUT    /api/v1/addresses/<id>
DELETE /api/v1/addresses/<id>

All tests run against the SQLite in-memory database (see conftest.py).
"""

import pytest

from app.extensions import db
from app.models.address import Address

BASE = "/api/v1/addresses"


# ── Helpers ───────────────────────────────────────────────────────────────────

def login(client, identifier="addr@example.com", identifier_type="email"):
    """Full OTP login — returns access_token."""
    r1 = client.post(
        "/api/v1/auth/request-otp",
        json={"identifier": identifier, "identifier_type": identifier_type},
    )
    assert r1.status_code == 200
    otp = r1.get_json()["otp"]

    r2 = client.post(
        "/api/v1/auth/verify-otp",
        json={"identifier": identifier, "identifier_type": identifier_type, "otp": otp},
    )
    assert r2.status_code == 200
    return r2.get_json()["access_token"]


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


VALID_ADDRESS = {
    "full_name":    "John Doe",
    "phone":        "9876543210",
    "address_line": "123 Main Road",
    "city":         "Kolkata",
    "state":        "West Bengal",
    "pincode":      "700001",
}


def create_address(client, token: str, overrides: dict = None) -> dict:
    """POST /addresses and return the response JSON."""
    payload = {**VALID_ADDRESS, **(overrides or {})}
    resp = client.post(BASE + "/", json=payload, headers=auth(token))
    assert resp.status_code == 201, resp.get_data(as_text=True)
    return resp.get_json()


# ══════════════════════════════════════════════════════════════════════════════
# GET /addresses/
# ══════════════════════════════════════════════════════════════════════════════

class TestListAddresses:
    """GET /api/v1/addresses/"""

    def test_requires_jwt(self, client):
        resp = client.get(BASE + "/")
        assert resp.status_code == 401

    def test_empty_list_for_new_user(self, client):
        """A brand-new user has no addresses."""
        token = login(client, "noaddr@example.com")
        resp  = client.get(BASE + "/", headers=auth(token))
        data  = resp.get_json()

        assert resp.status_code == 200
        assert data["status"]    == "success"
        assert data["addresses"] == []

    def test_returns_only_own_addresses(self, client):
        """User A should not see User B's addresses."""
        token_a = login(client, "usera@example.com")
        token_b = login(client, "userb@example.com")

        # User B creates an address.
        create_address(client, token_b)

        # User A's list should be empty.
        resp = client.get(BASE + "/", headers=auth(token_a))
        assert resp.get_json()["addresses"] == []


# ══════════════════════════════════════════════════════════════════════════════
# POST /addresses/
# ══════════════════════════════════════════════════════════════════════════════

class TestCreateAddress:
    """POST /api/v1/addresses/"""

    def test_requires_jwt(self, client):
        resp = client.post(BASE + "/", json=VALID_ADDRESS)
        assert resp.status_code == 401

    def test_create_address_success(self, client):
        """Valid payload → 201 with address data."""
        token = login(client, "create@example.com")
        resp  = client.post(BASE + "/", json=VALID_ADDRESS, headers=auth(token))
        data  = resp.get_json()

        assert resp.status_code == 201
        assert data["status"]                    == "success"
        assert data["address"]["city"]           == "Kolkata"
        assert data["address"]["pincode"]        == "700001"
        assert "id" in data["address"]

    def test_first_address_auto_default(self, client):
        """First address must be default regardless of is_default value."""
        token = login(client, "firstaddr@example.com")
        data  = create_address(client, token, {"is_default": False})

        assert data["address"]["is_default"] is True

    def test_second_address_not_default_by_default(self, client):
        """Second address without is_default=true should not be default."""
        token = login(client, "second@example.com")
        create_address(client, token)                       # first → auto default
        data2 = create_address(client, token, {"is_default": False})

        assert data2["address"]["is_default"] is False

    def test_second_address_as_default_clears_first(self, client, app):
        """Making second address default should unset the first."""
        token = login(client, "swap@example.com")
        first = create_address(client, token)
        _     = create_address(client, token, {"is_default": True})

        with app.app_context():
            first_addr = db.session.get(Address, first["address"]["id"])
            assert first_addr.is_default is False

    def test_missing_required_field(self, client):
        """Missing `city` → 400."""
        token    = login(client, "missing@example.com")
        payload  = {k: v for k, v in VALID_ADDRESS.items() if k != "city"}
        resp     = client.post(BASE + "/", json=payload, headers=auth(token))

        assert resp.status_code == 400

    def test_invalid_pincode(self, client):
        """5-digit pincode → 400."""
        token = login(client, "badpin@example.com")
        resp  = client.post(
            BASE + "/",
            json={**VALID_ADDRESS, "pincode": "70001"},
            headers=auth(token),
        )
        assert resp.status_code == 400

    def test_invalid_phone(self, client):
        """Alphabetic phone → 400."""
        token = login(client, "badphone@example.com")
        resp  = client.post(
            BASE + "/",
            json={**VALID_ADDRESS, "phone": "abc"},
            headers=auth(token),
        )
        assert resp.status_code == 400

    def test_user_id_not_accepted_from_body(self, client, app):
        """Even if user_id is sent in the body, it must be ignored."""
        token = login(client, "fakeid@example.com")
        resp  = client.post(
            BASE + "/",
            json={**VALID_ADDRESS, "user_id": 9999},
            headers=auth(token),
        )
        assert resp.status_code == 201
        addr_id = resp.get_json()["address"]["id"]

        with app.app_context():
            addr = db.session.get(Address, addr_id)
            # user_id must be the real authenticated user's ID — NOT 9999.
            assert addr.user_id != 9999


# ══════════════════════════════════════════════════════════════════════════════
# PUT /addresses/<id>
# ══════════════════════════════════════════════════════════════════════════════

class TestUpdateAddress:
    """PUT /api/v1/addresses/<id>"""

    def test_requires_jwt(self, client):
        resp = client.put(f"{BASE}/1", json={"city": "Mumbai"})
        assert resp.status_code == 401

    def test_update_city(self, client):
        """Updating city → 200 with new city value."""
        token = login(client, "updcity@example.com")
        addr  = create_address(client, token)["address"]

        resp = client.put(
            f"{BASE}/{addr['id']}",
            json={"city": "Mumbai"},
            headers=auth(token),
        )
        data = resp.get_json()

        assert resp.status_code == 200
        assert data["address"]["city"] == "Mumbai"

    def test_cannot_update_another_users_address(self, client):
        """User B cannot update User A's address → 404."""
        token_a = login(client, "ownerA@example.com")
        token_b = login(client, "ownerB@example.com")

        addr_a = create_address(client, token_a)["address"]

        resp = client.put(
            f"{BASE}/{addr_a['id']}",
            json={"city": "Hacked"},
            headers=auth(token_b),
        )
        assert resp.status_code == 404

    def test_update_nonexistent_address(self, client):
        """Address ID that doesn't exist → 404."""
        token = login(client, "noaddr2@example.com")
        resp  = client.put(f"{BASE}/99999", json={"city": "X"}, headers=auth(token))
        assert resp.status_code == 404

    def test_set_default_clears_other_defaults(self, client, app):
        """Setting second address as default must unset the first."""
        token = login(client, "setdef@example.com")
        first = create_address(client, token)["address"]
        sec   = create_address(client, token)["address"]

        client.put(
            f"{BASE}/{sec['id']}",
            json={"is_default": True},
            headers=auth(token),
        )

        with app.app_context():
            first_db = db.session.get(Address, first["id"])
            sec_db   = db.session.get(Address, sec["id"])
            assert first_db.is_default is False
            assert sec_db.is_default   is True

    def test_update_invalid_pincode(self, client):
        """Invalid pincode in update → 400."""
        token = login(client, "badpinupd@example.com")
        addr  = create_address(client, token)["address"]

        resp = client.put(
            f"{BASE}/{addr['id']}",
            json={"pincode": "ABCDEF"},
            headers=auth(token),
        )
        assert resp.status_code == 400


# ══════════════════════════════════════════════════════════════════════════════
# DELETE /addresses/<id>
# ══════════════════════════════════════════════════════════════════════════════

class TestDeleteAddress:
    """DELETE /api/v1/addresses/<id>"""

    def test_requires_jwt(self, client):
        resp = client.delete(f"{BASE}/1")
        assert resp.status_code == 401

    def test_delete_own_address(self, client, app):
        """Deleting own address → 200, row removed from DB."""
        token = login(client, "delown@example.com")
        addr  = create_address(client, token)["address"]

        resp = client.delete(f"{BASE}/{addr['id']}", headers=auth(token))
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "success"

        with app.app_context():
            assert db.session.get(Address, addr["id"]) is None

    def test_cannot_delete_another_users_address(self, client):
        """User B cannot delete User A's address → 404."""
        token_a = login(client, "del_ownerA@example.com")
        token_b = login(client, "del_ownerB@example.com")

        addr_a = create_address(client, token_a)["address"]

        resp = client.delete(f"{BASE}/{addr_a['id']}", headers=auth(token_b))
        assert resp.status_code == 404

    def test_delete_nonexistent_address(self, client):
        """Non-existent address ID → 404."""
        token = login(client, "delnoex@example.com")
        resp  = client.delete(f"{BASE}/99999", headers=auth(token))
        assert resp.status_code == 404

    def test_delete_default_promotes_next_oldest(self, client, app):
        """
        Deleting the default address should automatically make the
        oldest remaining address the new default.
        """
        token = login(client, "delpromote@example.com")

        first  = create_address(client, token)["address"]  # auto-default
        second = create_address(client, token)["address"]  # not default

        # Delete the default (first).
        client.delete(f"{BASE}/{first['id']}", headers=auth(token))

        with app.app_context():
            second_db = db.session.get(Address, second["id"])
            assert second_db.is_default is True

    def test_delete_only_address_leaves_no_default(self, client, app):
        """Deleting the sole address leaves the user with 0 addresses."""
        token = login(client, "delonly@example.com")
        addr  = create_address(client, token)["address"]

        client.delete(f"{BASE}/{addr['id']}", headers=auth(token))

        with app.app_context():
            count = Address.query.filter_by(
                user_id=db.session.execute(
                    db.select(Address.user_id).where(Address.id == addr["id"])
                ).scalar() or 0  # address deleted, fall back
            ).count()
            # Just verify via the list endpoint.

        resp = client.get(BASE + "/", headers=auth(token))
        assert resp.get_json()["addresses"] == []
