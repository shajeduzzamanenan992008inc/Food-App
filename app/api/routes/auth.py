"""Authentication API routes.

Stage A exposes the CSRF token used by session-authenticated API clients; the
remaining auth endpoints are added in a later stage.
"""

from flask import Blueprint
from flask_wtf.csrf import generate_csrf

from ..responses import success_response


auth_api = Blueprint("api_auth", __name__, url_prefix="/auth")


@auth_api.get("/csrf")
def csrf_token():
    """Return a CSRF token for state-changing API requests.

    API clients authenticate with the session cookie and echo this token back in
    the ``X-CSRFToken`` header on POST/PATCH/DELETE requests.
    """
    return success_response({"csrf_token": generate_csrf()})
