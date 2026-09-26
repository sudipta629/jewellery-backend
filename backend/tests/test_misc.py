import pytest
from app.extensions import db
from app.models.metal_rate import MetalRate
from app.models.offer import Offer, Coupon, Banner
from app.models.misc import ContactMessage, Notification
from app.models.store_visit import StoreVisit
from app.models.user import User
from datetime import datetime, timezone, timedelta

def login(client, identifier="customer@example.com"):
    r1 = client.post("/api/v1/auth/request-otp", json={"identifier": identifier, "identifier_type": "email"})
    otp = r1.get_json()["otp"]
    r2 = client.post("/api/v1/auth/verify-otp", json={"identifier": identifier, "identifier_type": "email", "otp": otp})
    return r2.get_json()["access_token"]

def auth(token):
    return {"Authorization": f"Bearer {token}"}

def test_get_metal_rates(client, app):
    with app.app_context():
        from datetime import date
        r = MetalRate(metal_type="gold", purity="22K", rate_per_gram=6000, effective_date=date.today(), is_active=True)
        db.session.add(r)
        db.session.commit()
        
    res = client.get("/api/v1/gold-price/")
    assert res.status_code == 200
    data = res.get_json()["data"]
    assert len(data) == 1
    assert data[0]["metal_type"] == "gold"
    assert data[0]["price"] == 60000.0  # rate_per_gram * 10

def test_get_active_offers(client, app):
    with app.app_context():
        o = Offer(title="Diwali", discount_type="PERCENTAGE", discount_value=10, is_active=True)
        db.session.add(o)
        db.session.commit()
        
    res = client.get("/api/v1/offers/")
    assert res.status_code == 200
    assert len(res.get_json()["data"]) == 1

def test_validate_coupon(client, app):
    token = login(client)
    with app.app_context():
        c = Coupon(code="SUMMER10", discount_type="PERCENTAGE", discount_value=10, is_active=True)
        db.session.add(c)
        db.session.commit()
        
    res = client.post("/api/v1/coupons/validate", json={"code": "SUMMER10", "cart_total": 5000}, headers=auth(token))
    assert res.status_code == 200
    assert res.get_json()["data"]["code"] == "SUMMER10"

def test_get_banners(client, app):
    with app.app_context():
        b = Banner(title="Summer Sale", image_url="http://example.com/img.jpg", is_active=True)
        db.session.add(b)
        db.session.commit()
        
    res = client.get("/api/v1/banners/")
    assert res.status_code == 200
    assert len(res.get_json()["data"]) == 1

def test_submit_contact(client):
    res = client.post("/api/v1/contact/", json={"name": "John Doe", "message": "Hello"})
    assert res.status_code == 201

def test_store_visits(client, app):
    token = login(client)
    
    # Book visit
    res = client.post("/api/v1/store-visits/", json={
        "visit_date": "2026-10-10",
        "contact_name": "John",
        "contact_phone": "12345"
    }, headers=auth(token))
    assert res.status_code == 201
    
    # Get visits
    res = client.get("/api/v1/store-visits/", headers=auth(token))
    assert res.status_code == 200
    assert len(res.get_json()["data"]) == 1

def test_notifications(client, app):
    token = login(client)
    with app.app_context():
        user = User.query.filter_by(email="customer@example.com").first()
        n = Notification(user_id=user.id, title="Welcome", message="Hello")
        db.session.add(n)
        db.session.commit()
        n_id = n.id
        
    res = client.get("/api/v1/notifications/", headers=auth(token))
    assert res.status_code == 200
    assert len(res.get_json()["data"]) == 1
    
    res = client.put(f"/api/v1/notifications/{n_id}/read", headers=auth(token))
    assert res.status_code == 200
