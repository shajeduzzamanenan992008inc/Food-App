"""Consistent JSON envelopes for the versioned REST API.

Every endpoint returns one of these shapes so clients can rely on a predictable
contract:

Success:   {"success": true, "data": {}, "message": "Success"}
Collection: {"success": true, "data": [], "pagination": {...}}
Error:     {"success": false, "error": {"code": "...", "message": "..."}}
"""

from flask import jsonify, request


API_PATH_PREFIX = "/api/"


def is_api_request():
    """Return True when the current request targets the JSON API."""
    return request.path.startswith(API_PATH_PREFIX)


def success_response(data=None, message="Success", status=200):
    return jsonify(success=True, data=data, message=message), status


def created_response(data=None, message="Created"):
    return success_response(data, message, 201)


def error_response(code, message, status=400, details=None):
    error = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return jsonify(success=False, error=error), status


def paginated_response(items, page, limit, total, message="Success"):
    return (
        jsonify(
            success=True,
            data=items,
            message=message,
            pagination={"page": page, "limit": limit, "total": total},
        ),
        200,
    )
