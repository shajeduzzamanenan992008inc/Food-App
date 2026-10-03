from datetime import datetime, timezone

from ..extensions import db


NOTIFICATION_TYPES = ("order", "delivery", "account", "system")


class Notification(db.Model):
    """A single in-app notification delivered to one account."""

    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    type = db.Column(db.String(30), nullable=False, default="system", server_default="system")
    message = db.Column(db.String(500), nullable=False)
    # Optional in-app destination (a relative path such as /orders/FB-...).
    link = db.Column(db.String(500), nullable=True)
    is_read = db.Column(db.Boolean, nullable=False, default=False, index=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    __table_args__ = (
        db.CheckConstraint(
            "type IN ('order', 'delivery', 'account', 'system')",
            name="ck_notification_type_valid",
        ),
        db.CheckConstraint("length(trim(message)) > 0", name="ck_notification_message_nonempty"),
        db.Index("ix_notifications_user_read", "user_id", "is_read"),
    )

    user = db.relationship("User", back_populates="notifications")