from datetime import datetime, timezone

from ..extensions import db


class AuditEvent(db.Model):
    """Append-only record of security-relevant actions for launch review.

    Actor email is snapshotted so the trail survives account changes. The client
    address is stored only as a keyed hash, never as a raw value.
    """

    __tablename__ = "audit_events"

    id = db.Column(db.Integer, primary_key=True)
    created_at = db.Column(
        db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False, index=True
    )
    action = db.Column(db.String(60), nullable=False, index=True)
    actor_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_email = db.Column(db.String(255), nullable=True)
    actor_role = db.Column(db.String(20), nullable=True)
    target_type = db.Column(db.String(40), nullable=True)
    target_id = db.Column(db.String(40), nullable=True)
    detail = db.Column(db.String(255), nullable=True)
    ip_hash = db.Column(db.String(64), nullable=True)

    __table_args__ = (db.Index("ix_audit_events_action_created", "action", "created_at"),)
