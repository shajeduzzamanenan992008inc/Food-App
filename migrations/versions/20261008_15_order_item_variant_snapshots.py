"""Store selected variant details on order items.

Revision ID: 20261008_15
Revises: 20261007_14
Create Date: 2026-10-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261008_15"
down_revision = "20261007_14"
branch_labels = None
depends_on = None


def upgrade():
    inspector = inspect(op.get_bind())
    if not inspector.has_table("order_items"):
        return
    columns = {item["name"] for item in inspector.get_columns("order_items")}
    foreign_keys = {
        item.get("name") for item in inspector.get_foreign_keys("order_items")
    }
    with op.batch_alter_table("order_items") as batch:
        if "variant_id" not in columns:
            batch.add_column(sa.Column("variant_id", sa.Integer(), nullable=True))
        if "variant_label" not in columns:
            batch.add_column(sa.Column("variant_label", sa.String(length=220), nullable=True))
        if "sku_snapshot" not in columns:
            batch.add_column(sa.Column("sku_snapshot", sa.String(length=80), nullable=True))
        if "fk_order_items_variant_id" not in foreign_keys:
            batch.create_foreign_key(
                "fk_order_items_variant_id",
                "product_variants",
                ["variant_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade():
    if not inspect(op.get_bind()).has_table("order_items"):
        return
    columns = {item["name"] for item in inspect(op.get_bind()).get_columns("order_items")}
    foreign_keys = {
        item.get("name") for item in inspect(op.get_bind()).get_foreign_keys("order_items")
    }
    with op.batch_alter_table("order_items") as batch:
        if "fk_order_items_variant_id" in foreign_keys:
            batch.drop_constraint("fk_order_items_variant_id", type_="foreignkey")
        for column in ("sku_snapshot", "variant_label", "variant_id"):
            if column in columns:
                batch.drop_column(column)
