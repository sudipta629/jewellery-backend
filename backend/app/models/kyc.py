"""
app/models/kyc.py

SQLAlchemy model for the `kyc_documents` table.

Stores KYC (Know Your Customer) document verification records
for jewellery store customers.

Statuses
--------
    PENDING  — submitted by customer, awaiting admin review
    APPROVED — verified by admin
    REJECTED — rejected by admin, with reason

Security Note
-------------
Do NOT store actual document images/files in PostgreSQL.
Store only a reference URL pointing to a secure cloud storage
location (e.g. S3 with pre-signed URLs or Firebase Storage).
"""

import enum

from app.extensions import db
from app.models.base import TimestampMixin


class KYCStatus(str, enum.Enum):
    PENDING  = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class KYCDocumentType(str, enum.Enum):
    AADHAAR         = "AADHAAR"
    PAN             = "PAN"
    PASSPORT        = "PASSPORT"
    DRIVING_LICENSE = "DRIVING_LICENSE"
    VOTER_ID        = "VOTER_ID"


class KYC(TimestampMixin, db.Model):
    """
    Represents a KYC document submission for a customer.

    Table: kyc_documents
    """

    __tablename__ = "kyc_documents"

    # ── Primary key ───────────────────────────────────────────────────────────
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # ── Customer ──────────────────────────────────────────────────────────────
    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Document info ─────────────────────────────────────────────────────────
    document_type = db.Column(
        db.String(30),
        nullable=False,
    )

    # The document identifier number (Aadhaar number, PAN, etc.)
    # Store only the last 4 digits for security, or the full reference
    # depending on regulatory requirements.
    document_number = db.Column(
        db.String(100),
        nullable=True,
    )

    # URL pointing to the secure cloud-stored document image.
    document_url = db.Column(
        db.String(500),
        nullable=True,
    )

    # ── Status ────────────────────────────────────────────────────────────────
    status = db.Column(
        db.String(20),
        nullable=False,
        default=KYCStatus.PENDING,
        index=True,
    )

    submitted_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    reviewed_at = db.Column(
        db.DateTime(timezone=True),
        nullable=True,
    )

    reviewed_by = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    rejection_reason = db.Column(db.Text, nullable=True)

    # ── Relationship ──────────────────────────────────────────────────────────
    user     = db.relationship("User", foreign_keys=[user_id],
                               backref=db.backref("kyc_documents", lazy="dynamic"))
    reviewer = db.relationship("User", foreign_keys=[reviewed_by])

    def __repr__(self) -> str:
        return (
            f"<KYC id={self.id} user_id={self.user_id} "
            f"type={self.document_type} status={self.status}>"
        )
