"""Add seller-owned catalog, product variants, translations, and moderation.

Revision ID: 20260929_07
Revises: 20260929_06
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260929_07"
down_revision = "20260929_06"
branch_labels = None
depends_on = None


def _add_column_if_missing(table, column):
    inspector = inspect(op.get_bind())
    if inspector.has_table(table):
        columns = {item["name"] for item in inspector.get_columns(table)}
        if column.name not in columns:
            op.add_column(table, column)


def _create_table_if_missing(name, *columns, **kwargs):
    if not inspect(op.get_bind()).has_table(name):
        op.create_table(name, *columns, **kwargs)


def _create_index_if_missing(table, name, columns, unique=False):
    if inspect(op.get_bind()).has_table(table):
        existing = {item["name"] for item in inspect(op.get_bind()).get_indexes(table)}
        if name not in existing:
            op.create_index(name, table, columns, unique=unique)


def upgrade():
    _add_column_if_missing(
        "products", sa.Column("seller_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    _add_column_if_missing(
        "products", sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0")
    )
    _add_column_if_missing(
        "products", sa.Column("original_locale", sa.String(12), nullable=False, server_default="en_US")
    )
    _add_column_if_missing(
        "products", sa.Column("moderation_status", sa.String(20), nullable=False, server_default="approved")
    )
    _add_column_if_missing("products", sa.Column("moderation_note", sa.String(500), nullable=True))
    _add_column_if_missing("products", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    _add_column_if_missing(
        "products", sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    )
    _create_index_if_missing("products", "ix_products_seller_id", ["seller_id"])
    _create_index_if_missing("products", "ix_products_moderation_status", ["moderation_status"])

    _create_table_if_missing(
        "product_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("locale", sa.String(12), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "locale", name="uq_product_translation_locale"),
        sa.CheckConstraint("locale IN ('en_US', 'bn_BD', 'hi_IN', 'ar')", name="ck_product_translation_locale"),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_product_translation_name_nonempty"),
    )
    _create_index_if_missing("product_translations", "ix_product_translations_product_id", ["product_id"])

    _create_table_if_missing(
        "product_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("product_id", sa.Integer(), sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sku", sa.String(80), nullable=False),
        sa.Column("option_name", sa.String(80), nullable=False),
        sa.Column("option_value", sa.String(120), nullable=False),
        sa.Column("price", sa.Numeric(10, 2), nullable=True),
        sa.Column("stock_quantity", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("product_id", "sku", name="uq_product_variant_sku"),
        sa.CheckConstraint("length(trim(sku)) > 0", name="ck_product_variant_sku_nonempty"),
        sa.CheckConstraint("stock_quantity >= 0", name="ck_product_variant_stock_nonnegative"),
        sa.CheckConstraint("price IS NULL OR price >= 0", name="ck_product_variant_price_nonnegative"),
    )
    _create_index_if_missing("product_variants", "ix_product_variants_product_id", ["product_id"])
    _create_index_if_missing("product_variants", "ix_product_variants_is_active", ["is_active"])


def downgrade():
    # Seller-created listings, translations, and stock are operational catalog data.
    # Keep this revision irreversible so rollback cannot silently erase them.
    pass
