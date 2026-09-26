import pytest
from app.extensions import db
from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.models.cart import Wishlist

def login(client, identifier="customer@example.com"):
    r1 = client.post("/api/v1/auth/request-otp", json={"identifier": identifier, "identifier_type": "email"})
    otp = r1.get_json()["otp"]
    r2 = client.post("/api/v1/auth/verify-otp", json={"identifier": identifier, "identifier_type": "email", "otp": otp})
    return r2.get_json()["access_token"]

def auth(token):
    return {"Authorization": f"Bearer {token}"}

def test_add_to_wishlist(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
    
    res = client.post("/api/v1/users/wishlist/", json={"productId": p_id}, headers=auth(token))
    assert res.status_code == 201
    
    # Duplicate prevention
    res2 = client.post("/api/v1/users/wishlist/", json={"productId": p_id}, headers=auth(token))
    assert res2.status_code == 409

def test_get_wishlist(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    client.post("/api/v1/users/wishlist/", json={"productId": p_id}, headers=auth(token))
    
    res = client.get("/api/v1/users/wishlist/", headers=auth(token))
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data) == 1
    assert data[0]["product_id"] == p_id

def test_remove_from_wishlist(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    client.post("/api/v1/users/wishlist/", json={"productId": p_id}, headers=auth(token))
    
    res_del = client.delete(f"/api/v1/users/wishlist/{p_id}", headers=auth(token))
    assert res_del.status_code == 200
    
    res_get = client.get("/api/v1/users/wishlist/", headers=auth(token))
    assert len(res_get.get_json()["data"]) == 0
