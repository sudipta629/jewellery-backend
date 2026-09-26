import pytest
from app.extensions import db
from app.models.user import User
from app.models.category import Category
from app.models.product import Product

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

def test_create_product(client, app):
    token = login_admin(client, app, "admin@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        category_id = c.id
    
    data = {
        "sku": "GLD-RNG-001",
        "name": "Classic Gold Ring",
        "slug": "classic-gold-ring",
        "category_id": category_id,
        "metal_type": "gold",
        "purity": "22K",
        "gross_weight": 5.5,
        "net_weight": 5.0,
        "making_charge": 500,
        "stone_charge": 0,
        "gst_percentage": 3,
        "stock_quantity": 10,
        "is_active": True
    }
    res = client.post("/api/v1/admin/products/", json=data, headers=auth(token))
    assert res.status_code == 201
    
    with app.app_context():
        p = Product.query.filter_by(sku="GLD-RNG-001").first()
        assert p is not None
        assert p.metal_type == "gold"

def test_list_products_public(client, app):
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p1 = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True)
        p2 = Product(sku="P2", name="P2", slug="p2", category_id=c.id, metal_type="gold", is_active=False)
        db.session.add_all([p1, p2])
        db.session.commit()

    res = client.get("/api/v1/products/")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data) == 1
    assert data[0]["sku"] == "P1"

def test_get_single_product(client, app):
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    res = client.get(f"/api/v1/products/{p_id}")
    assert res.status_code == 200
    assert res.get_json()["data"]["sku"] == "P1"

def test_update_product(client, app):
    token = login_admin(client, app, "admin@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    res = client.put(f"/api/v1/admin/products/{p_id}", json={"name": "P1 Updated"}, headers=auth(token))
    assert res.status_code == 200
    assert res.get_json()["data"]["name"] == "P1 Updated"

def test_delete_product(client, app):
    token = login_admin(client, app, "admin@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    res = client.delete(f"/api/v1/admin/products/{p_id}", headers=auth(token))
    assert res.status_code == 200
    
    with app.app_context():
        prod = Product.query.get(p_id)
        assert prod.is_active is False
