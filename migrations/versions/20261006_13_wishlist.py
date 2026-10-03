"""Add the customer wishlist.

Revision ID: 20261006_13
Revises: 20261005_12
Create Date: 2026-10-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261006_13"
down_revision = "20261005_12"
branch_labels = None
depends_on = None


def upgrade():
    if inspect(op.get_bind()).has_table("wishlist_items"):
        return
    op.create_table(
        "wishlist_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "product_id", name="uq_wishlist_user_product"),
    )
    op.create_index("ix_wishlist_items_user_id", "wishlist_items", ["user_id"])
    op.create_index("ix_wishlist_items_product_id", "wishlist_items", ["product_id"])
    op.create_index("ix_wishlist_user_created", "wishlist_items", ["user_id", "created_at"])


def downgrade():
    if inspect(op.get_bind()).has_table("wishlist_items"):
        op.drop_index("ix_wishlist_user_created", table_name="wishlist_items")
        op.drop_index("ix_wishlist_items_product_id", table_name="wishlist_items")
        op.drop_index("ix_wishlist_items_user_id", table_name="wishlist_items")
        op.drop_table("wishlist_items")