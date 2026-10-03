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


class AdminLoginChallenge(db.Model):
    __tablename__ = "admin_login_challenges"

    id = db.Column(db.String(64), primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code_hash = db.Column(db.String(64), nullable=False)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.CheckConstraint(
            "failed_attempts >= 0", name="ck_admin_login_challenges_failed_attempts_nonnegative"
        ),
        db.Index("ix_admin_login_challenges_user_sent", "user_id", "sent_at"),
    )


class RegistrationChallenge(db.Model):
    __tablename__ = "registration_challenges"

    id = db.Column(db.String(64), primary_key=True)
    email = db.Column(db.String(255), nullable=False, index=True)
    role = db.Column(db.String(20), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    profile_data = db.Column(db.JSON, nullable=False)
    locale = db.Column(db.String(12), nullable=True)
    code_hash = db.Column(db.String(64), nullable=False)
    sent_at = db.Column(db.DateTime(timezone=True), nullable=False)
    expires_at = db.Column(db.DateTime(timezone=True), nullable=False, index=True)
    failed_attempts = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    consumed_at = db.Column(db.DateTime(timezone=True), nullable=True)

    __table_args__ = (
        db.CheckConstraint("role IN ('customer', 'seller')", name="ck_registration_challenge_role_valid"),
        db.CheckConstraint(
            "failed_attempts >= 0", name="ck_registration_challenges_failed_attempts_nonnegative"
        ),
        db.Index("ix_registration_challenges_email_sent", "email", "sent_at"),
    )
