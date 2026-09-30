"""Add USDA food reference data and FoodOn taxonomy tables.

Revision ID: 20260928_03
Revises: 20260928_02
Create Date: 2026-09-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "20260928_03"
down_revision = "20260928_02"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    if not inspect(bind).has_table("fdc_categories"):
        op.create_table(
            "fdc_categories",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_fdc_categories_name", "fdc_categories", ["name"])

    if not inspect(bind).has_table("fdc_foods"):
        op.create_table(
            "fdc_foods",
        sa.Column("fdc_id", sa.Integer(), nullable=False),
        sa.Column("data_type", sa.String(length=40), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=False),
        sa.Column("wweia_category_id", sa.Integer(), nullable=True),
        sa.Column("food_code", sa.String(length=24), nullable=True),
        sa.Column("start_date", sa.String(length=10), nullable=True),
        sa.Column("end_date", sa.String(length=10), nullable=True),
        sa.Column("publication_date", sa.String(length=10), nullable=True),
        sa.Column("source_release", sa.String(length=24), nullable=False),
        sa.ForeignKeyConstraint(["wweia_category_id"], ["fdc_categories.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("fdc_id"),
        )
    _ensure_index("ix_fdc_foods_data_type", "fdc_foods", ["data_type"])
    _ensure_index("ix_fdc_foods_description", "fdc_foods", ["description"])
    food_columns = {column["name"] for column in inspect(bind).get_columns("fdc_foods")}
    if "category_id" in food_columns:
        _ensure_index("ix_fdc_foods_category_id", "fdc_foods", ["category_id"])
    else:
        _ensure_index("ix_fdc_foods_wweia_category_id", "fdc_foods", ["wweia_category_id"])

    if not inspect(bind).has_table("fdc_nutrients"):
        op.create_table(
            "fdc_nutrients",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=180), nullable=False),
            sa.Column("unit_name", sa.String(length=32), nullable=False),
            sa.Column("nutrient_nbr", sa.String(length=16), nullable=True),
            sa.Column("rank", sa.Integer(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )

    if not inspect(bind).has_table("fdc_food_nutrients"):
        op.create_table(
            "fdc_food_nutrients",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fdc_id", sa.Integer(), nullable=False),
        sa.Column("nutrient_id", sa.Integer(), nullable=False),
        sa.Column("amount", sa.Numeric(16, 6), nullable=True),
        sa.Column("data_points", sa.Integer(), nullable=True),
        sa.Column("derivation_id", sa.Integer(), nullable=True),
        sa.Column("min_value", sa.Numeric(16, 6), nullable=True),
        sa.Column("max_value", sa.Numeric(16, 6), nullable=True),
        sa.Column("median_value", sa.Numeric(16, 6), nullable=True),
        sa.Column("min_year_acquired", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["fdc_id"], ["fdc_foods.fdc_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["nutrient_id"], ["fdc_nutrients.id"], ondelete="RESTRICT"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_fdc_food_nutrients_fdc_id", "fdc_food_nutrients", ["fdc_id"])
    _ensure_index("ix_fdc_food_nutrients_nutrient_id", "fdc_food_nutrients", ["nutrient_id"])
    _ensure_index(
        "ix_fdc_food_nutrients_food_nutrient", "fdc_food_nutrients", ["fdc_id", "nutrient_id"]
    )

    if not inspect(bind).has_table("fdc_food_portions"):
        op.create_table(
            "fdc_food_portions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("fdc_id", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=True),
        sa.Column("amount", sa.Numeric(14, 6), nullable=True),
        sa.Column("measure_unit_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.String(length=240), nullable=True),
        sa.Column("modifier", sa.String(length=120), nullable=True),
        sa.Column("gram_weight", sa.Numeric(14, 6), nullable=True),
        sa.Column("data_points", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["fdc_id"], ["fdc_foods.fdc_id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
    _ensure_index("ix_fdc_food_portions_fdc_id", "fdc_food_portions", ["fdc_id"])

    if not inspect(bind).has_table("foodon_categories"):
        op.create_table(
            "foodon_categories",
            sa.Column("term_id", sa.String(length=48), nullable=False),
            sa.Column("name", sa.String(length=240), nullable=False),
            sa.Column("parent_term_ids", sa.Text(), nullable=False),
            sa.PrimaryKeyConstraint("term_id"),
        )
    _ensure_index("ix_foodon_categories_name", "foodon_categories", ["name"])


def _ensure_index(name, table, columns):
    inspector = inspect(op.get_bind())
    existing = {index["name"] for index in inspector.get_indexes(table)}
    if name not in existing:
        op.create_index(name, table, columns, unique=False)


def downgrade():
    op.drop_index("ix_foodon_categories_name", table_name="foodon_categories")
    op.drop_table("foodon_categories")
    op.drop_index("ix_fdc_food_portions_fdc_id", table_name="fdc_food_portions")
    op.drop_table("fdc_food_portions")
    op.drop_index("ix_fdc_food_nutrients_food_nutrient", table_name="fdc_food_nutrients")
    op.drop_index("ix_fdc_food_nutrients_nutrient_id", table_name="fdc_food_nutrients")
    op.drop_index("ix_fdc_food_nutrients_fdc_id", table_name="fdc_food_nutrients")
    op.drop_table("fdc_food_nutrients")
    op.drop_table("fdc_nutrients")
    food_indexes = {item["name"] for item in inspect(op.get_bind()).get_indexes("fdc_foods")}
    for index_name in ("ix_fdc_foods_category_id", "ix_fdc_foods_wweia_category_id"):
        if index_name in food_indexes:
            op.drop_index(index_name, table_name="fdc_foods")
    op.drop_index("ix_fdc_foods_description", table_name="fdc_foods")
    op.drop_index("ix_fdc_foods_data_type", table_name="fdc_foods")
    op.drop_table("fdc_foods")
    op.drop_index("ix_fdc_categories_name", table_name="fdc_categories")
    op.drop_table("fdc_categories")
