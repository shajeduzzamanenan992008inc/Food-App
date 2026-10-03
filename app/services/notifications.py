"""In-app notifications.

Creating a notification is best-effort: it must never break the request that
triggered it (an order, a delivery update, or an approval), so failures are
logged and swallowed just like the audit trail.
"""

import logging

from sqlalchemy import func, select, update

from ..extensions import db
from ..models import NOTIFICATION_TYPES, Notification


logger = logging.getLogger(__name__)


def notify(user_id, message, type="system", link=None):
    """Create one notification for a user id and return it (or None)."""
    if not user_id:
        return None
    try:
        notification = Notification(
            user_id=user_id,
            type=type if type in NOTIFICATION_TYPES else "system",
            message=str(message)[:500],
            link=str(link)[:500] if link else None,
        )
        db.session.add(notification)
        db.session.commit()
        return notification
    except Exception:  # noqa: BLE001 - notifications must never break a request
        db.session.rollback()
        logger.exception("Notification for user %s could not be recorded.", user_id)
        return None


def notifications_for(user, limit=50):
    if user is None:
        return []
    return db.session.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
        .limit(limit)
    ).all()


def unread_count(user):
    if user is None:
        return 0
    return db.session.scalar(
        select(func.count(Notification.id)).where(
            Notification.user_id == user.id, Notification.is_read.is_(False)
        )
    ) or 0


def mark_read(user, notification_id):
    """Mark one of the user's notifications as read. Return True when changed."""
    if user is None:
        return False
    notification = db.session.scalar(
        select(Notification).where(
            Notification.id == notification_id, Notification.user_id == user.id
        )
    )
    if notification is None:
        return False
    if not notification.is_read:
        notification.is_read = True
        db.session.commit()
    return True


def mark_all_read(user):
    """Mark every unread notification as read and return how many changed."""
    if user is None:
        return 0
    result = db.session.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read.is_(False))
        .values(is_read=True)
    )
    db.session.commit()
    return result.rowcount or 0