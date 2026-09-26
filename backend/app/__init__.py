"""
app/__init__.py

Application factory for the Jewellery E-Commerce API.
This function creates and configures the Flask application instance.
"""

from flask import Flask, jsonify
from .config import get_config
from .extensions import cors, db, jwt, limiter, migrate


def create_app(config_name: str = None) -> Flask:
    """
    Application factory function.

    Creates a Flask application instance, loads configuration,
    initialises extensions, and registers blueprints.

    Args:
        config_name: Optional name of the configuration class to use.
                     Defaults to the value of FLASK_ENV environment variable,
                     falling back to 'development'.

    Returns:
        A fully configured Flask application instance.
    """
    app = Flask(__name__, instance_relative_config=False)

    # ── Load configuration ────────────────────────────────────────────────────
    app.config.from_object(get_config(config_name))

    # ── Initialise extensions ─────────────────────────────────────────────────
    # CORS: allow the React frontend to call this API
    cors.init_app(
        app,
        resources={r"/*": {"origins": app.config.get("FRONTEND_URL", "*")}},
    )

    # SQLAlchemy: connects to PostgreSQL using SQLALCHEMY_DATABASE_URI from config
    db.init_app(app)

    # Flask-Migrate: enables `flask db init/migrate/upgrade` CLI commands
    # Second argument is the db instance so Migrate knows which database to manage
    migrate.init_app(app, db)

    # Flask-JWT-Extended: handles access tokens and refresh tokens
    jwt.init_app(app)

    # Flask-Limiter: per-IP rate limiting on sensitive auth endpoints.
    # RATELIMIT_ENABLED is False in TestingConfig so pytest is never blocked.
    limiter.init_app(app)

    # ── JWT error handlers ────────────────────────────────────────────────────
    # These replace Flask-JWT-Extended's default HTML error pages with
    # consistent JSON responses that match our API's error format.

    @jwt.expired_token_loader
    def expired_token_callback(jwt_header, jwt_payload):
        """Return a clean 401 when an access or refresh token has expired."""
        return jsonify({
            "status": "error",
            "message": "Token has expired. Please log in again.",
        }), 401

    @jwt.invalid_token_loader
    def invalid_token_callback(error_string):
        """Return a clean 401 when the token is malformed or has a bad signature."""
        return jsonify({
            "status": "error",
            "message": "Invalid token. Please log in again.",
        }), 401

    @jwt.unauthorized_loader
    def missing_token_callback(error_string):
        """Return a clean 401 when no token is present on a protected endpoint."""
        return jsonify({
            "status": "error",
            "message": "Authentication required. Please provide a valid access token.",
        }), 401

    @jwt.revoked_token_loader
    def revoked_token_callback(jwt_header, jwt_payload):
        """Return a clean 401 when a token has been revoked (blacklisted on logout)."""
        return jsonify({
            "status": "error",
            "message": "Token has been revoked. Please log in again.",
        }), 401

    # ── JWT token blocklist (logout / token revocation) ───────────────────────
    # Called by Flask-JWT-Extended on every request to a @jwt_required() endpoint.
    # If the token's jti is found in the blacklist, the request is rejected.
    @jwt.token_in_blocklist_loader
    def check_if_token_revoked(jwt_header, jwt_payload):
        """Return True if the token has been blacklisted (user logged out)."""
        from app.services.auth_service import TokenBlacklistService
        jti = jwt_payload.get("jti")
        if not jti:
            return False
        return TokenBlacklistService.is_token_revoked(jti)

    # ── Import models (MUST come after db.init_app) ───────────────────────────
    # Importing app.models here ensures that every SQLAlchemy model class is
    # registered in db.metadata BEFORE Flask-Migrate generates a migration.
    # This is the standard pattern for avoiding circular imports:
    #
    #   extensions.py  defines  db  (no app knowledge)
    #   models/*.py    imports  db  from extensions (no app knowledge)
    #   __init__.py    imports  models  AFTER db.init_app(app)
    #
    # Because models only import from extensions.py (not from app/__init__.py),
    # there is no circular dependency.
    with app.app_context():
        from . import models  # noqa: F401

    # ── Register blueprints ───────────────────────────────────────────────────
    from .routes import register_blueprints
    register_blueprints(app)

    return app
