# app/models/__init__.py
#
# Model discovery hub.
#
# Flask-Migrate (Alembic) can only generate migration scripts for models
# whose classes have been imported into Python's memory.  This file is the
# single place where every model is imported so that:
#
#   1. app/__init__.py imports this package once  ->  all models are loaded.
#   2. `flask db migrate` sees every table definition.
#   3. You never have to touch app/__init__.py again just to add a new model;
#      add the import here and Alembic detects it automatically.
#
# ── Model imports ─────────────────────────────────────────────────────────────
# STEP 4 — Users + Addresses
from .user    import User     # noqa: F401
from .address import Address  # noqa: F401

# STEP 5 — Auth
from .otp_verification import OTPVerification  # noqa: F401
from .token_blacklist  import TokenBlacklist   # noqa: F401

# STEP 7 — Catalogue
from .category      import Category     # noqa: F401
from .product       import Product      # noqa: F401
from .product_image import ProductImage # noqa: F401

# PHASE 5 — Metal rates + pricing
from .metal_rate import MetalRate  # noqa: F401

# PHASE 6 — Inventory
from .inventory import InventoryTransaction  # noqa: F401

# PHASE 7 — Orders
from .order import Order, OrderItem, OrderStatusHistory  # noqa: F401

# PHASE 8 — KYC
from .kyc import KYC  # noqa: F401

# PHASE 9 — Offers, Coupons, Banners
from .offer import Offer, Coupon, CouponUsage, Banner  # noqa: F401

# PHASE 10 — Payments
from .payment import Payment  # noqa: F401

# PHASE 11 — Invoices + Purity Certificates
from .invoice import Invoice, PurityCertificate  # noqa: F401

# PHASE 12 — Cart + Wishlist
from .cart import Cart, CartItem, Wishlist  # noqa: F401

# PHASE 13 — Store Visits
from .store_visit import StoreVisit  # noqa: F401

# PHASE 14 — Chat
from .chat import Conversation, ConversationParticipant, Message  # noqa: F401

# PHASE 15/18 — Notifications, Settings, Contact
from .misc import Notification, StoreSettings, ContactMessage  # noqa: F401
