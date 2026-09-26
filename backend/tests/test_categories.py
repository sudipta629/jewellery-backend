import pytest
from app.extensions import db
from app.models.user import User
from app.models.category import Category

def login(client, identifier="customer@example.com"):
    r1 = client.post("/api/v1/auth/request-otp", json={"identifier": identifier, "identifier_type": "email"})
    otp = r1.get_json()["otp"]
    r2 = client.post("/api/v1/auth/verify-otp", json={"identifier": identifier, "identifier_type": "email", "otp": otp})
    return r2.get_json()["access_token"]

def login_admin(client, app, identifier="admin@example.com"):
    r1 = client.post("/api/v1/auth/request-otp", json={"identifier": identifier, "identifier_type": "email"})
    otp = r1.get_json()["otp"]
    client.post("/api/v1/auth/verify-otp", json={"identifier": identifier, "identifier_type": "email", "otp": otp})
    with app.app_context():
        user = User.query.filter_by(email=identifier).first()
        user.role = "admin"
        db.session.commit()
    r1 = client.post("/api/v1/auth/request-otp", json={"identifier": identifier, "identifier_type": "email"})
    otp = r1.get_json()["otp"]
    r2 = client.post("/api/v1/auth/verify-otp", json={"identifier": identifier, "identifier_type": "email", "otp": otp})
    return r2.get_json()["access_token"]

def auth(token):
    return {"Authorization": f"Bearer {token}"}

def test_create_category(client, app):
    token = login_admin(client, app, "admin@example.com")
    
    data = {
        "name": "Gold Rings",
        "slug": "gold-rings",
        "description": "Beautiful gold rings",
        "is_active": True
    }
    res = client.post("/api/v1/admin/categories/", json=data, headers=auth(token))
    assert res.status_code == 201
    assert res.get_json()["data"]["name"] == "Gold Rings"
    
    # Verify DB persistence
    with app.app_context():
        cat = Category.query.filter_by(slug="gold-rings").first()
        assert cat is not None
        assert cat.name == "Gold Rings"

def test_create_category_unauthorized(client):
    token = login(client, "customer@example.com")
    # Not making admin
    data = {"name": "Test", "slug": "test"}
    res = client.post("/api/v1/admin/categories/", json=data, headers=auth(token))
    assert res.status_code == 403

def test_list_categories_public(client, app):
    with app.app_context():
        c1 = Category(name="Active Cat", slug="active", is_active=True)
        c2 = Category(name="Inactive Cat", slug="inactive", is_active=False)
        db.session.add_all([c1, c2])
        db.session.commit()

    res = client.get("/api/v1/categories/")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data) == 1
    assert data[0]["name"] == "Active Cat"

def test_list_categories_admin(client, app):
    token = login_admin(client, app, "admin@example.com")
    with app.app_context():
        c1 = Category(name="Active Cat", slug="active", is_active=True)
        c2 = Category(name="Inactive Cat", slug="inactive", is_active=False)
        db.session.add_all([c1, c2])
        db.session.commit()

    res = client.get("/api/v1/admin/categories/", headers=auth(token))
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data) == 2

def test_update_category(client, app):
    token = login_admin(client, app, "admin@example.com")
    with app.app_context():
        c = Category(name="Old Name", slug="old-slug")
        db.session.add(c)
        db.session.commit()
        c_id = c.id
        
    res = client.put(f"/api/v1/admin/categories/{c_id}", json={"name": "New Name"}, headers=auth(token))
    assert res.status_code == 200
    assert res.get_json()["data"]["name"] == "New Name"
    
    with app.app_context():
        cat = Category.query.get(c_id)
        assert cat.name == "New Name"

def test_delete_category(client, app):
    token = login_admin(client, app, "admin@example.com")
    with app.app_context():
        c = Category(name="To Delete", slug="to-delete", is_active=True)
        db.session.add(c)
        db.session.commit()
        c_id = c.id
        
    res = client.delete(f"/api/v1/admin/categories/{c_id}", headers=auth(token))
    assert res.status_code == 200
    
    with app.app_context():
        cat = Category.query.get(c_id)
        assert cat.is_active is False # Soft deleted
