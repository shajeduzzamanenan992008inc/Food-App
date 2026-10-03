"""Add product reviews.

Revision ID: 20261004_11
Revises: 20261003_10
Create Date: 2026-10-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261004_11"
down_revision = "20261003_10"
branch_labels = None
depends_on = None


def upgrade():
    if inspect(op.get_bind()).has_table("reviews"):
        return
    op.create_table(
        "reviews",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("rating", sa.SmallInteger(), nullable=False),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("author_name", sa.String(length=120), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("moderation_note", sa.String(length=500), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("moderated_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_review_rating_range"),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected')", name="ck_review_status_valid"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["moderated_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id", "user_id", "order_id", name="uq_review_product_user_order"
        ),
    )
    op.create_index("ix_reviews_product_id", "reviews", ["product_id"])
    op.create_index("ix_reviews_user_id", "reviews", ["user_id"])
    op.create_index("ix_reviews_order_id", "reviews", ["order_id"])
    op.create_index("ix_reviews_status", "reviews", ["status"])
    op.create_index("ix_reviews_product_status", "reviews", ["product_id", "status"])


def downgrade():
    if inspect(op.get_bind()).has_table("reviews"):
        op.drop_index("ix_reviews_product_status", table_name="reviews")
        op.drop_index("ix_reviews_status", table_name="reviews")
        op.drop_index("ix_reviews_order_id", table_name="reviews")
        op.drop_index("ix_reviews_user_id", table_name="reviews")
        op.drop_index("ix_reviews_product_id", table_name="reviews")
        op.drop_table("reviews")
