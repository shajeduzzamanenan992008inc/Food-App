"""API health endpoint."""

from flask import Blueprint

from ..responses import success_response


health_api = Blueprint("api_health", __name__)


@health_api.get("/health")
def health():
    return success_response({"status": "ok"})
