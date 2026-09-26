import pytest
from app.extensions import db
from app.models.user import User
from app.models.category import Category
from app.models.product import Product
from app.models.address import Address
from app.models.order import Order, OrderStatus

def login(client, identifier="customer@example.com"):
    r1 = client.post("/api/v1/auth/request-otp", json={"identifier": identifier, "identifier_type": "email"})
    otp = r1.get_json()["otp"]
    r2 = client.post("/api/v1/auth/verify-otp", json={"identifier": identifier, "identifier_type": "email", "otp": otp})
    return r2.get_json()["access_token"]

def auth(token):
    return {"Authorization": f"Bearer {token}"}

def setup_data(app):
    with app.app_context():
        c = Category(name="Rings", slug="rings")
        db.session.add(c)
        db.session.commit()
        
        p = Product(sku="P1", name="P1", slug="p1", category_id=c.id, metal_type="gold", net_weight=5.0, making_charge=500, stock_quantity=10)
        db.session.add(p)
        db.session.commit()
        
        # User is created on login, so we find them to add an address
        user = User.query.filter_by(email="customer@example.com").first()
        addr = Address(user_id=user.id, full_name="John", phone="123", address_line="abc", city="Kolkata", state="WB", pincode="700001", is_default=True)
        db.session.add(addr)
        db.session.commit()
        
        return p.id, addr.id

def test_create_order(client, app):
    token = login(client, "customer@example.com")
    p_id, addr_id = setup_data(app)
    
    data = {
        "items": [{"productId": p_id, "quantity": 1}],
        "shippingAddressId": addr_id,
        "billingAddressId": addr_id,
        "paymentMethod": "UPI"
    }
    
    res = client.post("/api/v1/orders/", json=data, headers=auth(token))
    assert res.status_code == 201
    
    # Verify stock reduction
    with app.app_context():
        prod = db.session.get(Product, p_id)
        assert prod.stock_quantity == 10  # stock reduces on CONFIRMED, not PLACED
        
def test_create_order_insufficient_stock(client, app):
    token = login(client, "customer@example.com")
    p_id, addr_id = setup_data(app)
    
    data = {
        "items": [{"productId": p_id, "quantity": 20}], # more than 10
        "shippingAddressId": addr_id,
        "billingAddressId": addr_id,
        "paymentMethod": "UPI"
    }
    
    res = client.post("/api/v1/orders/", json=data, headers=auth(token))
    assert res.status_code == 400
    
def test_list_orders(client, app):
    token = login(client, "customer@example.com")
    p_id, addr_id = setup_data(app)
    
    client.post("/api/v1/orders/", json={"items": [{"productId": p_id, "quantity": 1}], "shippingAddressId": addr_id}, headers=auth(token))
    
    res = client.get("/api/v1/orders/", headers=auth(token))
    assert res.status_code == 200
    assert len(res.get_json()["data"]) == 1
    
def test_get_single_order(client, app):
    token = login(client, "customer@example.com")
    p_id, addr_id = setup_data(app)
    
    res_create = client.post("/api/v1/orders/", json={"items": [{"productId": p_id, "quantity": 1}], "shippingAddressId": addr_id}, headers=auth(token))
    order_id = res_create.get_json()["data"]["id"]
    
    res = client.get(f"/api/v1/orders/{order_id}", headers=auth(token))
    assert res.status_code == 200
    assert res.get_json()["data"]["id"] == order_id
    
def test_cancel_order(client, app):
    token = login(client, "customer@example.com")
    p_id, addr_id = setup_data(app)
    
    res_create = client.post("/api/v1/orders/", json={"items": [{"productId": p_id, "quantity": 1}], "shippingAddressId": addr_id}, headers=auth(token))
    order_id = res_create.get_json()["data"]["id"]
    
    res = client.put(f"/api/v1/orders/{order_id}/cancel", headers=auth(token))
    assert res.status_code == 200
    
    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.order_status == OrderStatus.CANCELLED.value
