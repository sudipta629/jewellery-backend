

"""
app/routes/db_health.py

Database health-check blueprint.

Provides a single endpoint that tests whether the Flask application can
successfully open a connection to PostgreSQL and execute a query:

  GET /api/v1/db-health

The endpoint runs a lightweight  SELECT 1  query via SQLAlchemy.

Success (200):
    { "status": "success", "message": "Database connection is working" }

Failure (503):
    { "status": "error", "message": "Database connection failed" }

The error response deliberately omits database credentials and internal
connection details so that no sensitive information is leaked to callers.
"""

from flask import Blueprint, jsonify
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db

db_health_bp = Blueprint("db_health", __name__)


@db_health_bp.get("/db-health")
def db_health_check():
    """
    Database health-check endpoint.

    Runs  SELECT 1  inside the current application context.
    Returns 200 if the query succeeds, 503 if it fails.

    HTTP 503 (Service Unavailable) is the semantically correct code when
    a downstream dependency (the database) is unreachable.
    """
    try:
        # text() wraps a raw SQL string so SQLAlchemy treats it safely
        db.session.execute(text("SELECT 1"))
        return jsonify(
            {
                "status": "success",
                "message": "Database connection is working",
            }
        ), 200

    except SQLAlchemyError as error:
        # Log the real error internally (visible in the terminal / log file)
        # but return a safe, generic message to the caller.
        print(f"[DB-HEALTH] Database error: {error.__class__.__name__}")
        return jsonify(
            {
                "status": "error",
                "message": "Database connection failed. "
                           "Check your DATABASE_URL in .env and ensure "
                           "PostgreSQL is running.",
            }
        ), 503
