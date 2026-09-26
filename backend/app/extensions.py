"""
app/extensions.py

Central registry for Flask extensions.

Each extension is created here WITHOUT being bound to a specific app
instance.  Binding happens later inside create_app() via the
extension's .init_app(app) method.  This pattern prevents circular
imports and makes it easy to reuse the same extension objects across
blueprints and tests.

Extensions active in STEP 1:
  - Flask-CORS  ->  cross-origin request handling for the React frontend

Extensions added in STEP 2:
  - Flask-SQLAlchemy  ->  database ORM / connection management
  - Flask-Migrate     ->  Alembic-based schema migrations

Extensions added in STEP 5:
  - Flask-JWT-Extended ->  JWT access tokens + refresh tokens
  - Flask-Limiter      ->  per-IP rate limiting for auth endpoints
"""

from flask_cors import CORS
from flask_jwt_extended import JWTManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

# ── Active extensions ─────────────────────────────────────────────────────────────
cors    = CORS()
db      = SQLAlchemy()
migrate = Migrate()
jwt     = JWTManager()

# Rate limiter — key is the client's IP address.
# Storage URI is read from RATELIMIT_STORAGE_URI in config (default: memory://).
# In tests, limits are disabled via RATELIMIT_ENABLED=False in TestingConfig.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[],          # no global default — limits are set per-endpoint
    storage_uri="memory://",    # overridden by RATELIMIT_STORAGE_URI in config
)
