"""Add one-time customer and seller registration challenges.

Revision ID: 20261007_14
Revises: 20261006_13
Create Date: 2026-10-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20261007_14"
down_revision = "20261006_13"
branch_labels = None
depends_on = None


def upgrade():
    if inspect(op.get_bind()).has_table("registration_challenges"):
        return
    op.create_table(
        "registration_challenges",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("profile_data", sa.JSON(), nullable=False),
        sa.Column("locale", sa.String(length=12), nullable=True),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "role IN ('customer', 'seller')", name="ck_registration_challenge_role_valid"
        ),
        sa.CheckConstraint(
            "failed_attempts >= 0", name="ck_registration_challenges_failed_attempts_nonnegative"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_registration_challenges_email", "registration_challenges", ["email"])
    op.create_index("ix_registration_challenges_expires_at", "registration_challenges", ["expires_at"])
    op.create_index(
        "ix_registration_challenges_email_sent", "registration_challenges", ["email", "sent_at"]
    )


def downgrade():
    if inspect(op.get_bind()).has_table("registration_challenges"):
        op.drop_index("ix_registration_challenges_email_sent", table_name="registration_challenges")
        op.drop_index("ix_registration_challenges_expires_at", table_name="registration_challenges")
        op.drop_index("ix_registration_challenges_email", table_name="registration_challenges")
        op.drop_table("registration_challenges")
