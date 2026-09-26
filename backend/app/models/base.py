"""
app/models/base.py

Reusable base utilities for SQLAlchemy models.

Contents
--------
TimestampMixin
    A mixin class that adds `created_at` and `updated_at` columns to any
    model that inherits from it.  All timestamps are stored in UTC.

Usage (in a future model file)
------------------------------
    from app.extensions import db
    from app.models.base import TimestampMixin

    class Product(TimestampMixin, db.Model):
        __tablename__ = "products"

        id    = db.Column(db.Integer, primary_key=True)
        name  = db.Column(db.String(200), nullable=False)
        # created_at and updated_at are inherited automatically

Design notes
------------
* `db.Model` comes from Flask-SQLAlchemy and is already a declarative base,
  so no separate Base class is needed.
* TimestampMixin is listed BEFORE db.Model in the class definition so that
  Python's MRO resolves the mixin columns correctly.
* `lambda: datetime.now(timezone.utc)` is used instead of
  `datetime.utcnow` because utcnow() is deprecated in Python 3.12+.
* `onupdate` is called by SQLAlchemy automatically on every UPDATE statement.
"""

from datetime import datetime, timezone

from sqlalchemy import DateTime
from sqlalchemy.orm import mapped_column, MappedColumn


class TimestampMixin:
    """
    Mixin that automatically adds two audit timestamp columns to any model.

    Columns
    -------
    created_at : DateTime (UTC, timezone-aware)
        Set once when a row is first inserted. Never changes after that.

    updated_at : DateTime (UTC, timezone-aware)
        Set on insert AND updated automatically on every subsequent UPDATE.
    """

    created_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        # lambda ensures a fresh datetime is computed for each new row,
        # not a single value captured when the class is defined.
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    updated_at: MappedColumn[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        # onupdate fires on every SQL UPDATE for that row.
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
