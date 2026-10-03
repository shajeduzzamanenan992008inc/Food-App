"""In-app notification pages for every signed-in role."""

from flask import Blueprint, abort, redirect, render_template, url_for

from ..security import current_session_user
from ..services.notifications import mark_all_read, mark_read, notifications_for, unread_count


notifications_bp = Blueprint("notifications", __name__)


@notifications_bp.get("/notifications")
def index():
    user = current_session_user()
    if user is None:
        return redirect(url_for("auth.login", next=url_for("notifications.index")))
    return render_template(
        "notifications/index.html",
        user=user,
        notifications=notifications_for(user),
        unread_count=unread_count(user),
    )


@notifications_bp.post("/notifications/<int:notification_id>/read")
def read_one(notification_id):
    user = current_session_user()
    if user is None:
        abort(403)
    if not mark_read(user, notification_id):
        abort(404)
    return redirect(url_for("notifications.index"))


@notifications_bp.post("/notifications/read-all")
def read_all():
    user = current_session_user()
    if user is None:
        abort(403)
    mark_all_read(user)
    return redirect(url_for("notifications.index"))