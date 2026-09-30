"""Add session revocation, integrity checks, and common query indexes.

Revision ID: 20260928_02
Revises: 20260928_01
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260928_02"
down_revision = "20260928_01"
branch_labels = None
depends_on = None


CHECKS = {
    "users": (
        ("ck_user_role_valid", "role IN ('customer', 'admin')"),
        ("ck_user_auth_version_nonnegative", "auth_version >= 0"),
        ("ck_user_password_reset_attempts_nonnegative", "password_reset_attempts >= 0"),
    ),
    "orders": (
        ("ck_order_total_nonnegative", "total >= 0"),
        ("ck_order_payment_method_valid", "payment_method = 'cod'"),
        (
            "ck_order_status_valid",
            "status IN ('pending', 'confirmed', 'preparing', 'delivered', 'cancelled', 'declined')",
        ),
    ),
    "order_items": (
        ("ck_order_item_price_nonnegative", "price >= 0"),
        ("ck_order_item_quantity_range", "quantity BETWEEN 1 AND 20"),
        ("ck_order_item_subtotal_nonnegative", "subtotal >= 0"),
    ),
}


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)

    user_columns = {column["name"] for column in inspector.get_columns("users")}
    user_additions = (
        ("auth_version", sa.Column("auth_version", sa.Integer(), nullable=False, server_default="0")),
        ("password_reset_hash", sa.Column("password_reset_hash", sa.String(length=64), nullable=True)),
        (
            "password_reset_expires_at",
            sa.Column("password_reset_expires_at", sa.DateTime(timezone=True), nullable=True),
        ),
        (
            "password_reset_sent_at",
            sa.Column("password_reset_sent_at", sa.DateTime(timezone=True), nullable=True),
        ),
        (
            "password_reset_attempts",
            sa.Column("password_reset_attempts", sa.Integer(), nullable=False, server_default="0"),
        ),
    )
    for column_name, column in user_additions:
        if column_name not in user_columns:
            op.add_column("users", column)

    if bind.dialect.name != "sqlite":
        order_columns = {column["name"]: column for column in inspector.get_columns("orders")}
        order_number = order_columns["order_number"]
        if getattr(order_number["type"], "length", None) and order_number["type"].length < 40:
            op.alter_column(
                "orders",
                "order_number",
                existing_type=sa.String(length=order_number["type"].length),
                type_=sa.String(length=40),
                existing_nullable=False,
            )

        for table_name, constraints in CHECKS.items():
            existing = {item["name"] for item in inspect(bind).get_check_constraints(table_name)}
            for name, expression in constraints:
                if name not in existing:
                    op.create_check_constraint(name, table_name, expression)

    index_definitions = (
        ("orders", "ix_orders_user_created", ["user_id", "created_at"]),
        ("orders", "ix_orders_status_created", ["status", "created_at"]),
        ("products", "ix_products_available_featured_name", ["is_available", "is_featured", "name"]),
    )
    for table_name, index_name, columns in index_definitions:
        existing = {item["name"] for item in inspect(bind).get_indexes(table_name)}
        if index_name not in existing:
            op.create_index(index_name, table_name, columns, unique=False)


def downgrade():
    bind = op.get_bind()
    for table_name, index_name in (
        ("orders", "ix_orders_user_created"),
        ("orders", "ix_orders_status_created"),
        ("products", "ix_products_available_featured_name"),
    ):
        existing = {item["name"] for item in inspect(bind).get_indexes(table_name)}
        if index_name in existing:
            op.drop_index(index_name, table_name=table_name)
