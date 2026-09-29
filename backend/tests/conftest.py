"""
tests/conftest.py

Pytest fixtures shared across the entire test suite.

Design decisions
----------------
* TestingConfig uses SQLite in-memory so that the real PostgreSQL database
  is NEVER touched during testing.  Each test session gets a fresh, empty
  schema.
* FLASK_ENV is forced to "development" in tests so that the OTP is returned
  in the request-otp response (no real SMS/email needed).
* The `db_session` fixture wraps each test in a transaction that is rolled
  back after the test completes — keeping tests fully isolated.
"""

import os
import pytest

# Force development mode so OTP is exposed in API responses during tests.
os.environ["FLASK_ENV"] = "development"
os.environ["GMAIL_ADDRESS"] = "test@gmail.com"
os.environ["GMAIL_APP_PASSWORD"] = "dummy"

from unittest.mock import patch

# Globally patch SMTP to prevent any real network calls during tests.
patcher = patch("smtplib.SMTP")
patcher.start()

from app import create_app
from app.extensions import db as _db


@pytest.fixture(scope="session")
def app():
    """
    Create a Flask application configured for testing.

    scope="session" means a single app instance is created for the entire
    test session, which is faster than creating a new app for each test.
    """
    flask_app = create_app("testing")

    with flask_app.app_context():
        # Create all tables in the SQLite in-memory database.
        _db.create_all()
        yield flask_app
        # Tear down: drop all tables after the session ends.
        _db.drop_all()


@pytest.fixture(scope="function")
def client(app):
    """
    Flask test client — one per test function.

    The test client allows us to make HTTP requests to the API without
    starting a real server.
    """
    return app.test_client()


@pytest.fixture(scope="function", autouse=True)
def clean_db(app):
    """
    Roll back all database changes after each test.

    autouse=True means this fixture runs automatically for every test
    without needing to be explicitly requested.

    This ensures tests are completely isolated — no data from one test
    leaks into another.
    """
    with app.app_context():
        yield
        # Clean all tables between tests (SQLite doesn't support TRUNCATE).
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()
