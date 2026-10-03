"""Notification API routes."""

from flask import Blueprint

from ...security import current_session_user
from ...services.notifications import (
    mark_all_read,
    mark_read,
    notifications_for,
    unread_count,
)
from ..errors import ApiError
from ..responses import success_response
from ..serializers import notification_to_dict


notifications_api = Blueprint("api_notifications", __name__)


def _current_user():
    user = current_session_user()
    if user is None:
        raise ApiError("Sign in to read your notifications.", "UNAUTHENTICATED", 401)
    return user


@notifications_api.get("/notifications")
def list_notifications():
    user = _current_user()
    return success_response(
        {
            "unread": unread_count(user),
            "notifications": [notification_to_dict(item) for item in notifications_for(user)],
        }
    )


@notifications_api.post("/notifications/read-all")
def read_all_notifications():
    user = _current_user()
    return success_response({"updated": mark_all_read(user)})


@notifications_api.post("/notifications/<int:notification_id>/read")
def read_notification(notification_id):
    user = _current_user()
    if not mark_read(user, notification_id):
        raise ApiError("Notification not found.", "NOT_FOUND", 404)
    return success_response({"id": notification_id, "is_read": True})