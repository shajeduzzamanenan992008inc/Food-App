"""Use one category reference for USDA Foundation and FNDDS foods.

Revision ID: 20260929_04
Revises: 20260928_03
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260929_04"
down_revision = "20260928_03"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if not inspector.has_table("fdc_foods"):
        return

    columns = {column["name"] for column in inspector.get_columns("fdc_foods")}
    indexes = {index["name"] for index in inspector.get_indexes("fdc_foods")}
    if "wweia_category_id" in columns and "category_id" not in columns:
        if "ix_fdc_foods_wweia_category_id" in indexes:
            op.drop_index("ix_fdc_foods_wweia_category_id", table_name="fdc_foods")
        op.alter_column(
            "fdc_foods",
            "wweia_category_id",
            new_column_name="category_id",
            existing_type=sa.Integer(),
            existing_nullable=True,
        )
        op.create_index("ix_fdc_foods_category_id", "fdc_foods", ["category_id"])


def downgrade():
    inspector = inspect(op.get_bind())
    if not inspector.has_table("fdc_foods"):
        return

    columns = {column["name"] for column in inspector.get_columns("fdc_foods")}
    indexes = {index["name"] for index in inspector.get_indexes("fdc_foods")}
    if "category_id" in columns and "wweia_category_id" not in columns:
        if "ix_fdc_foods_category_id" in indexes:
            op.drop_index("ix_fdc_foods_category_id", table_name="fdc_foods")
        op.alter_column(
            "fdc_foods",
            "category_id",
            new_column_name="wweia_category_id",
            existing_type=sa.Integer(),
            existing_nullable=True,
        )
        op.create_index("ix_fdc_foods_wweia_category_id", "fdc_foods", ["wweia_category_id"])
