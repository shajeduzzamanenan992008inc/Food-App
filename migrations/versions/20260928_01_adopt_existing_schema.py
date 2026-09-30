"""Create missing FreshBite tables and adopt prototype databases.

Revision ID: 20260928_01
Revises:
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

from app.extensions import db


revision = "20260928_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Older FreshBite deployments ran create_all() at startup. create_all with
    # checkfirst adopts those tables while still creating the full schema on a
    # new database; it never drops or rewrites existing order/customer data.
    db.metadata.create_all(bind=op.get_bind(), checkfirst=True)
    inspector = inspect(op.get_bind())
    for table_name in ("customers", "admins"):
        columns = {column["name"] for column in inspector.get_columns(table_name)}
        if "profile_image" not in columns:
            op.add_column(table_name, sa.Column("profile_image", sa.String(length=255), nullable=True))


def downgrade():
    # This adoption revision is intentionally irreversible to preserve data.
    pass
