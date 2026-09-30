"""Add marketplace account roles, seller applications, and staff invitations.

Revision ID: 20260929_06
Revises: 20260929_05
Create Date: 2026-09-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260929_06"
down_revision = "20260929_05"
branch_labels = None
depends_on = None


def _create_table_if_missing(name, *columns, **kwargs):
    if not inspect(op.get_bind()).has_table(name):
        op.create_table(name, *columns, **kwargs)


def upgrade():
    bind = op.get_bind()
    inspector = inspect(bind)
    if inspector.has_table("users"):
        checks = {item["name"] for item in inspector.get_check_constraints("users")}
        if "ck_user_role_valid" in checks:
            if bind.dialect.name == "sqlite":
                with op.batch_alter_table("users", recreate="always") as batch:
                    batch.drop_constraint("ck_user_role_valid", type_="check")
                    batch.create_check_constraint(
                        "ck_user_role_valid",
                        "role IN ('customer', 'seller', 'rider', 'admin')",
                    )
            else:
                op.drop_constraint("ck_user_role_valid", "users", type_="check")
                op.create_check_constraint(
                    "ck_user_role_valid",
                    "users",
                    "role IN ('customer', 'seller', 'rider', 'admin')",
                )

    _create_table_if_missing(
        "seller_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("store_name", sa.String(120), nullable=False),
        sa.Column("contact_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("business_address", sa.String(500), nullable=True),
        sa.Column("approval_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("review_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "approval_status IN ('pending', 'approved', 'rejected', 'suspended')",
            name="ck_seller_profile_status_valid",
        ),
    )
    inspector = inspect(bind)
    if inspector.has_table("seller_profiles"):
        existing = {item["name"] for item in inspector.get_indexes("seller_profiles")}
        if "ix_seller_profiles_approval_status" not in existing:
            op.create_index("ix_seller_profiles_approval_status", "seller_profiles", ["approval_status"])
        if "ix_seller_profiles_status_created" not in existing:
            op.create_index("ix_seller_profiles_status_created", "seller_profiles", ["approval_status", "created_at"])

    _create_table_if_missing(
        "rider_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("full_name", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("availability_status", sa.String(20), nullable=False, server_default="offline"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "availability_status IN ('offline', 'available', 'busy', 'suspended')",
            name="ck_rider_profile_status_valid",
        ),
    )
    _create_table_if_missing(
        "account_invitations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("token_digest", sa.String(64), nullable=False, unique=True),
        sa.Column("invited_by_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locale", sa.String(12), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('rider', 'admin')", name="ck_account_invitation_role_valid"),
    )
    inspector = inspect(bind)
    if inspector.has_table("account_invitations"):
        existing = {item["name"] for item in inspector.get_indexes("account_invitations")}
        for name, columns in (
            ("ix_account_invitations_email", ["email"]),
            ("ix_account_invitations_expires_at", ["expires_at"]),
            ("ix_account_invitations_pending_email", ["email", "accepted_at", "expires_at"]),
        ):
            if name not in existing:
                op.create_index(name, "account_invitations", columns, unique=False)


def downgrade():
    # Staff and seller identities are operational data. Keep this migration
    # irreversible so a rollback cannot silently delete accounts or reviews.
    pass
