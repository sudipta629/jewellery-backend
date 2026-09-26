"""
app/models/notification.py
app/models/store_settings.py
app/models/contact.py

Miscellaneous models: Notification, StoreSettings, ContactMessage.
Combined into a single file to keep the models directory manageable.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


# ══════════════════════════════════════════════════════════════════════════════
# Notification
# ══════════════════════════════════════════════════════════════════════════════

class NotificationType(str, enum.Enum):
    ORDER_PLACED    = "ORDER_PLACED"
    ORDER_CONFIRMED = "ORDER_CONFIRMED"
    ORDER_SHIPPED   = "ORDER_SHIPPED"
    ORDER_DELIVERED = "ORDER_DELIVERED"
    ORDER_CANCELLED = "ORDER_CANCELLED"
    KYC_APPROVED    = "KYC_APPROVED"
    KYC_REJECTED    = "KYC_REJECTED"
    OFFER           = "OFFER"
    GENERAL         = "GENERAL"


class Notification(TimestampMixin, db.Model):
    """
    In-app notification for a user.

    Table: notifications
    """

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    title   = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text,        nullable=False)

    notification_type = db.Column(
        db.String(30),
        nullable=False,
        default=NotificationType.GENERAL,
        index=True,
    )

    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)

    # Optional: deep link data
    reference_type = db.Column(db.String(50),  nullable=True)   # "order", "kyc", etc.
    reference_id   = db.Column(db.Integer,      nullable=True)   # the related ID

    user = db.relationship("User", backref=db.backref("notifications", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<Notification id={self.id} user_id={self.user_id} read={self.is_read}>"


# ══════════════════════════════════════════════════════════════════════════════
# StoreSettings
# ══════════════════════════════════════════════════════════════════════════════

class StoreSettings(TimestampMixin, db.Model):
    """
    Singleton table for store-wide configuration.

    Table: store_settings

    Only one row should ever exist (id=1).
    Use StoreSettingsService.get() to retrieve or create the singleton.
    """

    __tablename__ = "store_settings"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    store_name    = db.Column(db.String(200), nullable=True)
    tagline       = db.Column(db.String(300), nullable=True)
    address       = db.Column(db.Text,        nullable=True)
    phone         = db.Column(db.String(20),  nullable=True)
    email         = db.Column(db.String(254), nullable=True)
    gst_number    = db.Column(db.String(20),  nullable=True)

    # Business hours (free-text for flexibility)
    business_hours = db.Column(db.Text, nullable=True)

    logo_url       = db.Column(db.String(500), nullable=True)
    favicon_url    = db.Column(db.String(500), nullable=True)

    currency_code  = db.Column(db.String(10),  nullable=True, default="INR")
    currency_symbol= db.Column(db.String(5),   nullable=True, default="₹")

    # Social links
    facebook_url   = db.Column(db.String(300), nullable=True)
    instagram_url  = db.Column(db.String(300), nullable=True)
    twitter_url    = db.Column(db.String(300), nullable=True)
    youtube_url    = db.Column(db.String(300), nullable=True)
    whatsapp_number= db.Column(db.String(20),  nullable=True)

    # Tax settings
    default_gst_percentage = db.Column(db.Numeric(5, 2), nullable=True, default=3)

    def __repr__(self) -> str:
        return f"<StoreSettings id={self.id} store={self.store_name!r}>"


# ══════════════════════════════════════════════════════════════════════════════
# ContactMessage
# ══════════════════════════════════════════════════════════════════════════════

class ContactStatus(str, enum.Enum):
    NEW     = "NEW"
    READ    = "READ"
    REPLIED = "REPLIED"
    CLOSED  = "CLOSED"


class ContactMessage(TimestampMixin, db.Model):
    """
    Customer enquiry / contact form submission.

    Table: contact_messages
    """

    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Optional: link to a registered user
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    name    = db.Column(db.String(120), nullable=False)
    email   = db.Column(db.String(254), nullable=True)
    phone   = db.Column(db.String(20),  nullable=True)
    subject = db.Column(db.String(200), nullable=True)
    message = db.Column(db.Text,        nullable=False)

    status  = db.Column(
        db.String(20),
        nullable=False,
        default=ContactStatus.NEW,
        index=True,
    )

    admin_reply = db.Column(db.Text, nullable=True)

    user = db.relationship("User", backref=db.backref("contact_messages", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<ContactMessage id={self.id} from={self.name!r} status={self.status}>"
