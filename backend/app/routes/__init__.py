"""
app/routes/__init__.py

Blueprint registration hub.

All blueprints are imported and registered here so that create_app()
only needs to call a single function:  register_blueprints(app).

Adding a new blueprint in the future is a one-liner in this file.
"""

from flask import Flask

from .auth      import auth_bp
from .db_health import db_health_bp
from .health    import health_bp
from .users     import users_bp
from .addresses import addresses_bp
from .admin_auth_routes import admin_auth_bp


def register_blueprints(app: Flask) -> None:
    """
    Attach every blueprint to *app*.

    Args:
        app: The Flask application instance returned by create_app().
    """
    # ── API v1 blueprints ─────────────────────────────────────────────────────────────
    app.register_blueprint(health_bp,    url_prefix="/api/v1")
    app.register_blueprint(db_health_bp, url_prefix="/api/v1")

    # ── STEP 5: Authentication ────────────────────────────────────────────────────
    app.register_blueprint(auth_bp,      url_prefix="/api/v1/auth")

    # ── Admin Authentication (login, /me, logout) ────────────────────────────────
    app.register_blueprint(admin_auth_bp, url_prefix="/api/v1/admin")

    # ── STEP 6: User Profile + Address API ──────────────────────────────────────
    app.register_blueprint(users_bp,     url_prefix="/api/v1/users")
    app.register_blueprint(addresses_bp, url_prefix="/api/v1/addresses")

    # ── Categories ─────────────────────────────────────────────────────────────
    from .category_routes import categories_bp
    from .admin_category_routes import admin_categories_bp
    app.register_blueprint(categories_bp,       url_prefix="/api/v1/categories")
    app.register_blueprint(admin_categories_bp, url_prefix="/api/v1/admin/categories")

    # ── Products ───────────────────────────────────────────────────────────────
    from .product_routes import products_bp
    from .admin_product_routes import admin_products_bp
    app.register_blueprint(products_bp,         url_prefix="/api/v1/products")
    app.register_blueprint(admin_products_bp,   url_prefix="/api/v1/admin/products")

    # ── Customer Misc & Orders ─────────────────────────────────────────────────
    from .customer_cart_routes import cart_bp, wishlist_bp
    from .customer_order_routes import orders_bp
    from .customer_misc_routes import (
        rates_bp, offers_bp, coupons_bp, banners_bp, 
        contact_bp, store_visits_bp, notifications_bp
    )
    
    app.register_blueprint(cart_bp,          url_prefix="/api/v1/cart")
    app.register_blueprint(wishlist_bp,      url_prefix="/api/v1/users/wishlist")
    app.register_blueprint(orders_bp,        url_prefix="/api/v1/orders")
    
    app.register_blueprint(rates_bp,         url_prefix="/api/v1/gold-price")
    app.register_blueprint(offers_bp,        url_prefix="/api/v1/offers")
    app.register_blueprint(coupons_bp,       url_prefix="/api/v1/coupons")
    app.register_blueprint(banners_bp,       url_prefix="/api/v1/banners")
    app.register_blueprint(contact_bp,       url_prefix="/api/v1/contact")
    app.register_blueprint(store_visits_bp,  url_prefix="/api/v1/store-visits")
    app.register_blueprint(notifications_bp, url_prefix="/api/v1/notifications")

    # ── Admin Only Routes ──────────────────────────────────────────────────────
    from .admin_rate_routes      import admin_rates_bp
    from .admin_inventory_routes import admin_inventory_bp
    from .admin_order_routes     import admin_orders_bp
    from .admin_customer_routes  import admin_customers_bp
    from .admin_offer_routes     import admin_offers_bp, admin_coupons_bp, admin_banners_bp
    from .admin_misc_routes      import (
        admin_payments_bp, admin_invoices_bp, admin_store_visits_bp,
        admin_chat_bp, admin_notifications_bp, admin_staff_bp,
        admin_settings_bp, admin_contact_bp, admin_reports_bp, admin_dashboard_bp
    )

    app.register_blueprint(admin_rates_bp,         url_prefix="/api/v1/admin/rates")
    app.register_blueprint(admin_inventory_bp,     url_prefix="/api/v1/admin/inventory")
    app.register_blueprint(admin_orders_bp,        url_prefix="/api/v1/admin/orders")
    app.register_blueprint(admin_customers_bp,     url_prefix="/api/v1/admin")  # contains /customers and /kyc
    app.register_blueprint(admin_offers_bp,        url_prefix="/api/v1/admin/offers")
    app.register_blueprint(admin_coupons_bp,       url_prefix="/api/v1/admin/coupons")
    app.register_blueprint(admin_banners_bp,       url_prefix="/api/v1/admin/banners")
    
    app.register_blueprint(admin_payments_bp,      url_prefix="/api/v1/admin/payments")
    app.register_blueprint(admin_invoices_bp,      url_prefix="/api/v1/admin/invoices")
    app.register_blueprint(admin_store_visits_bp,  url_prefix="/api/v1/admin/store-visits")
    app.register_blueprint(admin_chat_bp,          url_prefix="/api/v1/admin/chat")
    app.register_blueprint(admin_notifications_bp, url_prefix="/api/v1/admin/notifications")
    app.register_blueprint(admin_staff_bp,         url_prefix="/api/v1/admin/staff")
    app.register_blueprint(admin_settings_bp,      url_prefix="/api/v1/admin/settings")
    app.register_blueprint(admin_contact_bp,       url_prefix="/api/v1/admin/contact-messages")
    app.register_blueprint(admin_reports_bp,       url_prefix="/api/v1/admin/reports")
    app.register_blueprint(admin_dashboard_bp,     url_prefix="/api/v1/admin/dashboard")
