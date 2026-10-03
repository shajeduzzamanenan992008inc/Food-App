"""Add in-app notifications.

Revision ID: 20261005_12
Revises: 20261004_11
Create Date: 2026-10-05
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261005_12"
down_revision = "20261004_11"
branch_labels = None
depends_on = None


def upgrade():
    if inspect(op.get_bind()).has_table("notifications"):
        return
    op.create_table(
        "notifications",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=30), server_default="system", nullable=False),
        sa.Column("message", sa.String(length=500), nullable=False),
        sa.Column("link", sa.String(length=500), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "type IN ('order', 'delivery', 'account', 'system')",
            name="ck_notification_type_valid",
        ),
        sa.CheckConstraint("length(trim(message)) > 0", name="ck_notification_message_nonempty"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])
    op.create_index("ix_notifications_is_read", "notifications", ["is_read"])
    op.create_index("ix_notifications_user_read", "notifications", ["user_id", "is_read"])


def downgrade():
    if inspect(op.get_bind()).has_table("notifications"):
        op.drop_index("ix_notifications_user_read", table_name="notifications")
        op.drop_index("ix_notifications_is_read", table_name="notifications")
        op.drop_index("ix_notifications_user_id", table_name="notifications")
        op.drop_table("notifications")