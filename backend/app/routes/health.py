"""
app/routes/health.py

Health-check blueprint.

Provides a single endpoint that a monitoring tool, load balancer, or
frontend developer can use to confirm the API is reachable:

  GET /api/v1/health
"""

from flask import Blueprint, jsonify

health_bp = Blueprint("health", __name__)


@health_bp.get("/health")
def health_check():
    """
    Health-check endpoint.

    Returns a simple JSON payload confirming the API is running.
    HTTP 200 means the server is up and reachable.

    Response:
        {
            "status": "success",
            "message": "Jewellery API is running"
        }
    """
    return jsonify(
        {
            "status": "success",
            "message": "Jewellery API is running",
        }
    ), 200
