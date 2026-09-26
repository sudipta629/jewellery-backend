"""
run.py

Application entry point.

This is the file you run directly to start the development server:

    python run.py

What it does:
  1. Loads environment variables from the .env file (via python-dotenv).
  2. Calls create_app() to build a configured Flask application instance.
  3. Starts Flask's built-in development server on the configured host/port.

Do NOT use this server in production.
In production, use a proper WSGI server such as Gunicorn or uWSGI.
"""

import os
from dotenv import load_dotenv

# Load .env before importing the app so that os.environ is populated
# when config.py reads the environment variables.
load_dotenv()

from app import create_app  # noqa: E402  (import after load_dotenv is intentional)

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("FLASK_RUN_HOST", "127.0.0.1")
    port = int(os.environ.get("FLASK_RUN_PORT", 5000))
    debug = os.environ.get("FLASK_ENV", "development") == "development"

    print(f"\n* Jewellery API is starting...")
    print(f"  Environment : {os.environ.get('FLASK_ENV', 'development')}")
    print(f"  Running on  : http://{host}:{port}")
    print(f"  Health check: http://{host}:{port}/api/v1/health\n")

    app.run(host=host, port=port, debug=debug)
