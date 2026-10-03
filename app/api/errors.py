"""API error handling that returns JSON envelopes and never leaks internals."""

import logging

from flask_wtf.csrf import CSRFError
from werkzeug.exceptions import HTTPException

from .responses import error_response


logger = logging.getLogger(__name__)


# Stable, client-facing codes for the HTTP statuses the API can emit.
STATUS_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHENTICATED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
}


class ApiError(Exception):
    """Raise inside API views for a controlled JSON error response."""

    def __init__(self, message, code="BAD_REQUEST", status=400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details


def register_error_handlers(api_bp):
    """Register JSON error handlers scoped to the API blueprint."""

    @api_bp.errorhandler(ApiError)
    def handle_api_error(error):
        return error_response(error.code, error.message, error.status, error.details)

    @api_bp.errorhandler(CSRFError)
    def handle_csrf_error(error):
        return error_response(
            "CSRF_ERROR", "The CSRF token is missing or invalid.", 403
        )

    @api_bp.errorhandler(HTTPException)
    def handle_http_error(error):
        code = STATUS_CODES.get(error.code, "HTTP_ERROR")
        message = error.description or "Request failed."
        return error_response(code, message, error.code)
