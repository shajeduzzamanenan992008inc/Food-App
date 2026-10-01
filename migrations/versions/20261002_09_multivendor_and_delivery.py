"""Add seller sub-orders, delivery workflow, and the email outbox.

Revision ID: 20261002_09
Revises: 20261001_08
Create Date: 2026-10-02
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261002_09"
down_revision = "20261001_08"
branch_labels = None
depends_on = None


ORDER_COLUMNS = (
    ("checkout_group", sa.String(length=40), True, None),
    ("seller_id", sa.Integer(), True, None),
    ("rider_id", sa.Integer(), True, None),
    ("delivery_fee", sa.Numeric(10, 2), False, sa.text("0")),
    ("delivery_status", sa.String(length=20), False, sa.text("'unassigned'")),
    ("assigned_at", sa.DateTime(timezone=True), True, None),
    ("picked_up_at", sa.DateTime(timezone=True), True, None),
    ("out_for_delivery_at", sa.DateTime(timezone=True), True, None),
    ("delivered_at", sa.DateTime(timezone=True), True, None),
    ("delivery_proof", sa.String(length=500), True, None),
    ("delivery_note", sa.String(length=500), True, None),
)

ORDER_INDEXES = (
    ("ix_orders_checkout_group", ["checkout_group"]),
    ("ix_orders_seller_id", ["seller_id"]),
    ("ix_orders_rider_id", ["rider_id"]),
    ("ix_orders_delivery_status", ["delivery_status"]),
    ("ix_orders_seller_created", ["seller_id", "created_at"]),
    ("ix_orders_rider_status", ["rider_id", "delivery_status"]),
)


def upgrade():
    inspector = inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("orders")}
    for name, column_type, nullable, default in ORDER_COLUMNS:
        if name in existing_columns:
            continue
        op.add_column(
            "orders",
            sa.Column(name, column_type, nullable=nullable, server_default=default),
        )

    inspector = inspect(op.get_bind())
    existing_indexes = {index["name"] for index in inspector.get_indexes("orders")}
    for name, columns in ORDER_INDEXES:
        if name not in existing_indexes:
            op.create_index(name, "orders", columns)

    if not inspect(op.get_bind()).has_table("outbound_emails"):
        op.create_table(
            "outbound_emails",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("recipients", sa.Text(), nullable=False),
            sa.Column("subject", sa.String(length=255), nullable=False),
            sa.Column("body_html", sa.Text(), nullable=False),
            sa.Column("attachments", sa.Text(), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
            sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
            sa.Column("last_error", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.CheckConstraint(
                "status IN ('pending', 'sent', 'failed')", name="ck_outbound_email_status_valid"
            ),
            sa.CheckConstraint("attempts >= 0", name="ck_outbound_email_attempts_nonnegative"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_outbound_emails_status", "outbound_emails", ["status"])
        op.create_index(
            "ix_outbound_emails_status_created", "outbound_emails", ["status", "created_at"]
        )


def downgrade():
    if inspect(op.get_bind()).has_table("outbound_emails"):
        op.drop_index("ix_outbound_emails_status_created", table_name="outbound_emails")
        op.drop_index("ix_outbound_emails_status", table_name="outbound_emails")
        op.drop_table("outbound_emails")

    inspector = inspect(op.get_bind())
    existing_indexes = {index["name"] for index in inspector.get_indexes("orders")}
    for name, _columns in ORDER_INDEXES:
        if name in existing_indexes:
            op.drop_index(name, table_name="orders")

    inspector = inspect(op.get_bind())
    existing_columns = {column["name"] for column in inspector.get_columns("orders")}
    for name, _column_type, _nullable, _default in ORDER_COLUMNS:
        if name in existing_columns:
            op.drop_column("orders", name)
