"""
app/models/invoice.py

SQLAlchemy models for invoices and purity certificates.

Invoice          — Full order invoice document.
PurityCertificate — Hallmark / purity certificate for a product.

Design Note
-----------
PDF generation is SEPARATED from this model.
The model stores the structured data; a service (InvoiceService) 
handles PDF generation using a library like WeasyPrint or ReportLab.
"""

from app.extensions import db
from app.models.base import TimestampMixin


class Invoice(TimestampMixin, db.Model):
    """
    Represents a customer invoice for an order.

    Table: invoices
    """

    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    # Human-readable invoice number (e.g. "INV-20260924-0001")
    invoice_number = db.Column(db.String(30), nullable=False, unique=True, index=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        unique=True,   # one invoice per order
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Snapshot of totals (copied from Order at generation time)
    subtotal        = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    making_charges  = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    stone_charges   = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    gst_amount      = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    discount_amount = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total_amount    = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    # Generated PDF URL (stored in cloud storage)
    pdf_url = db.Column(db.String(500), nullable=True)

    # Relationships
    order = db.relationship("Order", backref=db.backref("invoice", uselist=False))
    user  = db.relationship("User",  backref=db.backref("invoices", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<Invoice id={self.id} number={self.invoice_number!r} order_id={self.order_id}>"


class PurityCertificate(TimestampMixin, db.Model):
    """
    Represents a hallmark / purity certificate for a jewellery item.

    Table: purity_certificates

    One certificate per OrderItem (one product in one order).
    """

    __tablename__ = "purity_certificates"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)

    certificate_number = db.Column(db.String(50), nullable=False, unique=True, index=True)

    order_id = db.Column(
        db.Integer,
        db.ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    order_item_id = db.Column(
        db.Integer,
        db.ForeignKey("order_items.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    product_id = db.Column(
        db.Integer,
        db.ForeignKey("products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Snapshot fields
    product_name = db.Column(db.String(200), nullable=False)
    product_sku  = db.Column(db.String(100), nullable=False)
    metal_type   = db.Column(db.String(50),  nullable=True)
    purity       = db.Column(db.String(20),  nullable=True)
    net_weight   = db.Column(db.Numeric(10, 2), nullable=True)
    gross_weight = db.Column(db.Numeric(10, 2), nullable=True)

    issue_date = db.Column(db.Date, nullable=True)

    # Generated PDF URL
    pdf_url = db.Column(db.String(500), nullable=True)

    # Relationships
    order      = db.relationship("Order",     backref=db.backref("certificates", lazy="dynamic"))
    order_item = db.relationship("OrderItem", backref=db.backref("certificate", uselist=False))
    product    = db.relationship("Product",   backref=db.backref("certificates", lazy="dynamic"))
    user       = db.relationship("User",      backref=db.backref("certificates", lazy="dynamic"))

    def __repr__(self) -> str:
        return f"<PurityCertificate id={self.id} number={self.certificate_number!r}>"
