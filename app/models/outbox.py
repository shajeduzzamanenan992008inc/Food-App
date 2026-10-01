from datetime import datetime, timezone

from ..extensions import db


class OutboundEmail(db.Model):
    """Durable outbox row so failed transaction emails can be retried safely.

    Rendered content is stored so a retry never has to re-render a template or
    hold request state. Diagnostic fields never store provider credentials.
    """

    __tablename__ = "outbound_emails"

    id = db.Column(db.Integer, primary_key=True)
    recipients = db.Column(db.Text, nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body_html = db.Column(db.Text, nullable=False)
    attachments = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(20), nullable=False, default="pending", index=True)
    attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    last_error = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    __table_args__ = (
        db.CheckConstraint(
            "status IN ('pending', 'sent', 'failed')", name="ck_outbound_email_status_valid"
        ),
        db.CheckConstraint("attempts >= 0", name="ck_outbound_email_attempts_nonnegative"),
        db.Index("ix_outbound_emails_status_created", "status", "created_at"),
    )
