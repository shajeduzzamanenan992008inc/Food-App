"""Add account language preferences and update the default platform brand.

Revision ID: 20260929_05
Revises: 20260929_04
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260929_05"
down_revision = "20260929_04"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if inspector.has_table("users"):
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "preferred_locale" not in columns:
            op.add_column("users", sa.Column("preferred_locale", sa.String(length=12), nullable=True))

    inspector = inspect(op.get_bind())
    if inspector.has_table("app_settings"):
        op.execute(
            "UPDATE app_settings SET app_name = 'NexHaat' "
            "WHERE lower(trim(app_name)) = 'freshbite'"
        )


def downgrade():
    inspector = inspect(op.get_bind())
    if inspector.has_table("users"):
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "preferred_locale" in columns:
            op.drop_column("users", "preferred_locale")
