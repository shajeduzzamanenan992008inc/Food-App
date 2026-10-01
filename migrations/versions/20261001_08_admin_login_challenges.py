"""Add one-time admin login challenges.

Revision ID: 20261001_08
Revises: 20260929_07
Create Date: 2026-10-01
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261001_08"
down_revision = "20260929_07"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if not inspector.has_table("admin_login_challenges"):
        op.create_table(
            "admin_login_challenges",
            sa.Column("id", sa.String(length=64), nullable=False),
            sa.Column("user_id", sa.Integer(), nullable=False),
            sa.Column("code_hash", sa.String(length=64), nullable=False),
            sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
            sa.CheckConstraint(
                "failed_attempts >= 0",
                name="ck_admin_login_challenges_failed_attempts_nonnegative",
            ),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    inspector = inspect(op.get_bind())
    indexes = {item["name"] for item in inspector.get_indexes("admin_login_challenges")}
    if "ix_admin_login_challenges_user_id" not in indexes:
        op.create_index("ix_admin_login_challenges_user_id", "admin_login_challenges", ["user_id"])
    if "ix_admin_login_challenges_expires_at" not in indexes:
        op.create_index("ix_admin_login_challenges_expires_at", "admin_login_challenges", ["expires_at"])
    if "ix_admin_login_challenges_user_sent" not in indexes:
        op.create_index(
            "ix_admin_login_challenges_user_sent", "admin_login_challenges", ["user_id", "sent_at"]
        )


def downgrade():
    if inspect(op.get_bind()).has_table("admin_login_challenges"):
        op.drop_table("admin_login_challenges")
