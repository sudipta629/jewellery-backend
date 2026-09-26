import pytest
from app.extensions import db
from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.models.cart import Cart, CartItem

def login(client, identifier="customer@example.com"):
    r1 = client.post("/api/v1/auth/request-otp", json={"identifier": identifier, "identifier_type": "email"})
    otp = r1.get_json()["otp"]
    r2 = client.post("/api/v1/auth/verify-otp", json={"identifier": identifier, "identifier_type": "email", "otp": otp})
    return r2.get_json()["access_token"]

def auth(token):
    return {"Authorization": f"Bearer {token}"}

def test_add_to_cart(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
    
    res = client.post("/api/v1/cart/", json={"productId": p_id, "quantity": 2}, headers=auth(token))
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data["items"]) == 1
    assert data["items"][0]["product_id"] == p_id
    assert data["items"][0]["quantity"] == 2

def test_add_to_cart_insufficient_stock(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=1)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
    
    res = client.post("/api/v1/cart/", json={"productId": p_id, "quantity": 2}, headers=auth(token))
    assert res.status_code == 400

def test_get_cart(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    client.post("/api/v1/cart/", json={"productId": p_id, "quantity": 2}, headers=auth(token))
    
    res = client.get("/api/v1/cart/", headers=auth(token))
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data["items"]) == 1
    
def test_update_cart_quantity(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    res_add = client.post("/api/v1/cart/", json={"productId": p_id, "quantity": 1}, headers=auth(token))
    item_id = res_add.get_json()["data"]["items"][0]["id"]
    
    res_update = client.put(f"/api/v1/cart/{item_id}", json={"quantity": 3}, headers=auth(token))
    assert res_update.status_code == 200
    assert res_update.get_json()["data"]["items"][0]["quantity"] == 3
    
def test_remove_cart_item(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        p_id = p.id
        
    res_add = client.post("/api/v1/cart/", json={"productId": p_id, "quantity": 1}, headers=auth(token))
    item_id = res_add.get_json()["data"]["items"][0]["id"]
    
    res_del = client.delete(f"/api/v1/cart/{item_id}", headers=auth(token))
    assert res_del.status_code == 200
    assert len(res_del.get_json()["data"]["items"]) == 0
    
def test_clear_cart(client, app):
    token = login(client, "customer@example.com")
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        p1 = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        p2 = Product(sku="P2", name="P2", slug="p2", category_id=c.id, metal_type="gold", is_active=True, stock_quantity=10)
        db.session.add_all([p1, p2])
        db.session.commit()
        p1_id = p1.id
        p2_id = p2.id
        
    client.post("/api/v1/cart/", json={"productId": p1_id, "quantity": 1}, headers=auth(token))
    client.post("/api/v1/cart/", json={"productId": p2_id, "quantity": 2}, headers=auth(token))
    
    res_clear = client.delete("/api/v1/cart/", headers=auth(token))
    assert res_clear.status_code == 200
    assert len(res_clear.get_json()["data"]["items"]) == 0
