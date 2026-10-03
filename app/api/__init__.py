"""Versioned JSON REST API (Bravo-compatible), mounted under ``/api/v1``.

The API is intentionally thin: it reuses the shared services and repositories
used by the server-rendered pages so it stays frontend-independent and can be
consumed by the website, Bravo, or a future mobile client.

All blueprint setup happens at import time. ``create_app`` may run many times
(for tests and workers), so a registered blueprint must not be modified later.
"""

from flask import Blueprint

from .errors import register_error_handlers
from .routes.auth import auth_api
from .routes.admin import admin_api
from .routes.catalog import catalog_api
from .routes.commerce import commerce_api
from .routes.health import health_api
from .routes.notifications import notifications_api
from .routes.wishlist import wishlist_api


api_bp = Blueprint("api", __name__, url_prefix="/api/v1")

# Error handlers and sub-blueprints are set up once, before first registration.
register_error_handlers(api_bp)
api_bp.register_blueprint(health_api)
api_bp.register_blueprint(auth_api)
api_bp.register_blueprint(admin_api)
api_bp.register_blueprint(catalog_api)
api_bp.register_blueprint(commerce_api)
api_bp.register_blueprint(notifications_api)
api_bp.register_blueprint(wishlist_api)


def register_api(app):
    """Attach the prepared versioned API blueprint to a Flask app."""
    app.register_blueprint(api_bp)

