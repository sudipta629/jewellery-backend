"""
app/models/store_visit.py

SQLAlchemy model for `store_visits` table.

Customers can book a visit to the physical store.
Admin staff confirm, complete, or cancel the visit.
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class VisitStatus(str, enum.Enum):
    PENDING   = "PENDING"
    CONFIRMED = "CONFIRMED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class StoreVisit(TimestampMixin, db.Model):
    """
    Represents a store visit booking by a customer.

    Table: store_visits
    """

    __tablename__ = "store_visits"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,    # nullable to allow walk-in bookings
        index=True,
    )

    # Contact information (may differ from user profile)
    contact_name  = db.Column(db.String(120), nullable=False)
    contact_phone = db.Column(db.String(20),  nullable=False)
    contact_email = db.Column(db.String(254), nullable=True)

    visit_date = db.Column(db.Date,   nullable=False)
    visit_time = db.Column(db.String(20), nullable=True)  # e.g. "10:30 AM"

    purpose = db.Column(db.String(200), nullable=True)  # e.g. "Engagement ring selection"

    status = db.Column(
        db.String(20),
        nullable=False,
        default=VisitStatus.PENDING,
        index=True,
    )

    notes = db.Column(db.Text, nullable=True)

    # Staff notes (admin-only field)
    admin_notes = db.Column(db.Text, nullable=True)

    user = db.relationship("User", backref=db.backref("store_visits", lazy="dynamic"))

    def __repr__(self) -> str:
        return (
            f"<StoreVisit id={self.id} contact={self.contact_name!r} "
            f"date={self.visit_date} status={self.status}>"
        )
