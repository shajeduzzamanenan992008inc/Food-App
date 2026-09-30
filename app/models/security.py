from datetime import datetime, timezone

from ..extensions import db


class AuthThrottle(db.Model):
    __tablename__ = "auth_throttles"

    key_hash = db.Column(db.String(64), primary_key=True)
    failures = db.Column(db.Integer, nullable=False, default=0)
    window_started_at = db.Column(db.DateTime(timezone=True), nullable=False)
    blocked_until = db.Column(db.DateTime(timezone=True), nullable=True)
    last_attempt_at = db.Column(
        db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    __table_args__ = (
        db.CheckConstraint("failures >= 0", name="ck_auth_throttle_failures_nonnegative"),
        db.Index("ix_auth_throttles_last_attempt", "last_attempt_at"),
    )
