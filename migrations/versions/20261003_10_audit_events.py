"""Add the audit event trail.

Revision ID: 20261003_10
Revises: 20261002_09
Create Date: 2026-10-03
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261003_10"
down_revision = "20261002_09"
branch_labels = None
depends_on = None


INDEXES = (
    ("ix_audit_events_created_at", ["created_at"]),
    ("ix_audit_events_action", ["action"]),
    ("ix_audit_events_action_created", ["action", "created_at"]),
)


def upgrade():
    if not inspect(op.get_bind()).has_table("audit_events"):
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("action", sa.String(length=60), nullable=False),
            sa.Column("actor_id", sa.Integer(), nullable=True),
            sa.Column("actor_email", sa.String(length=255), nullable=True),
            sa.Column("actor_role", sa.String(length=20), nullable=True),
            sa.Column("target_type", sa.String(length=40), nullable=True),
            sa.Column("target_id", sa.String(length=40), nullable=True),
            sa.Column("detail", sa.String(length=255), nullable=True),
            sa.Column("ip_hash", sa.String(length=64), nullable=True),
            sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )

    inspector = inspect(op.get_bind())
    existing = {index["name"] for index in inspector.get_indexes("audit_events")}
    for name, columns in INDEXES:
        if name not in existing:
            op.create_index(name, "audit_events", columns)


def downgrade():
    if inspect(op.get_bind()).has_table("audit_events"):
        for name, _columns in INDEXES:
            op.drop_index(name, table_name="audit_events")
        op.drop_table("audit_events")
