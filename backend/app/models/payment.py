"""
app/models/payment.py

SQLAlchemy model for the `payments` table.

Each Order can have one or more Payment attempts.
The most recent successful payment record determines the order's payment status.

CRITICAL SECURITY NOTE:
* Payment success MUST be confirmed via server-side webhook verification.
* NEVER trust payment_status="SUCCESS" sent directly from the frontend.
* Gateway webhooks must be verified with signatures before updating DB.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class PaymentMethod(str, enum.Enum):
    UPI        = "UPI"
    CARD       = "CARD"
    NETBANKING = "NETBANKING"
    EMI        = "EMI"
    COD        = "COD"


class PaymentStatus(str, enum.Enum):
    PENDING  = "PENDING"
    SUCCESS  = "SUCCESS"
    FAILED   = "FAILED"
    REFUNDED = "REFUNDED"


class Payment(TimestampMixin, db.Model):
    """
    Represents a single payment attempt for an order.

    Table: payments
    """

    __tablename__ = "payments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    payment_method = db.Column(db.String(20), nullable=False)

    # The transaction ID from the payment gateway
    transaction_id = db.Column(db.String(200), nullable=True, unique=True, index=True)

    # Gateway name (e.g., "razorpay", "paytm", "stripe")
    gateway = db.Column(db.String(50), nullable=True, default="manual")

    amount = db.Column(db.Numeric(12, 2), nullable=False)

    status = db.Column(
        db.String(20),
        nullable=False,
        default=PaymentStatus.PENDING,
        index=True,
    )

    # Timestamp of successful payment (set by webhook handler)
    paid_at = db.Column(db.DateTime(timezone=True), nullable=True)

    # Raw gateway response (for debugging, do not expose to frontend)
    gateway_response = db.Column(db.Text, nullable=True)

    # Relationships
    order = db.relationship("Order", backref=db.backref("payments", lazy="dynamic"))
    user  = db.relationship("User",  backref=db.backref("payments",  lazy="dynamic"))

    def __repr__(self) -> str:
        return (
            f"<Payment id={self.id} order_id={self.order_id} "
            f"method={self.payment_method} status={self.status}>"
        )
