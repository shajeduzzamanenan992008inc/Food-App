from ..extensions import db


class FdcCategory(db.Model):
    """FoodData Central dietary category vocabulary."""

    __tablename__ = "fdc_categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    __table_args__ = (db.Index("ix_fdc_categories_name", "name"),)


class FdcFood(db.Model):
    """A reference food from USDA FDC; it is not a sellable menu product."""

    __tablename__ = "fdc_foods"

    fdc_id = db.Column(db.Integer, primary_key=True)
    data_type = db.Column(db.String(40), nullable=False, index=True)
    description = db.Column(db.String(500), nullable=False, index=True)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("fdc_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    food_code = db.Column(db.String(24), nullable=True)
    start_date = db.Column(db.String(10), nullable=True)
    end_date = db.Column(db.String(10), nullable=True)
    publication_date = db.Column(db.String(10), nullable=True)
    source_release = db.Column(db.String(24), nullable=False)
    category = db.relationship("FdcCategory", foreign_keys=[category_id], lazy="joined")


class FdcNutrient(db.Model):
    __tablename__ = "fdc_nutrients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(180), nullable=False)
    unit_name = db.Column(db.String(32), nullable=False)
    nutrient_nbr = db.Column(db.String(16), nullable=True)
    rank = db.Column(db.Integer, nullable=True)


class FdcFoodNutrient(db.Model):
    __tablename__ = "fdc_food_nutrients"

    id = db.Column(db.Integer, primary_key=True)
    fdc_id = db.Column(
        db.Integer,
        db.ForeignKey("fdc_foods.fdc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nutrient_id = db.Column(
        db.Integer,
        db.ForeignKey("fdc_nutrients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    amount = db.Column(db.Numeric(16, 6), nullable=True)
    data_points = db.Column(db.Integer, nullable=True)
    derivation_id = db.Column(db.Integer, nullable=True)
    min_value = db.Column(db.Numeric(16, 6), nullable=True)
    max_value = db.Column(db.Numeric(16, 6), nullable=True)
    median_value = db.Column(db.Numeric(16, 6), nullable=True)
    min_year_acquired = db.Column(db.Integer, nullable=True)
    __table_args__ = (db.Index("ix_fdc_food_nutrients_food_nutrient", "fdc_id", "nutrient_id"),)


class FdcFoodPortion(db.Model):
    __tablename__ = "fdc_food_portions"

    id = db.Column(db.Integer, primary_key=True)
    fdc_id = db.Column(
        db.Integer,
        db.ForeignKey("fdc_foods.fdc_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    sequence_number = db.Column(db.Integer, nullable=True)
    amount = db.Column(db.Numeric(14, 6), nullable=True)
    measure_unit_id = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(240), nullable=True)
    modifier = db.Column(db.String(120), nullable=True)
    gram_weight = db.Column(db.Numeric(14, 6), nullable=True)
    data_points = db.Column(db.Integer, nullable=True)


class FoodOnCategory(db.Model):
    """FoodOn's real food-product vocabulary, kept separate from menu categories."""

    __tablename__ = "foodon_categories"

    term_id = db.Column(db.String(48), primary_key=True)
    name = db.Column(db.String(240), nullable=False)
    parent_term_ids = db.Column(db.Text, nullable=False, default="[]")
    __table_args__ = (db.Index("ix_foodon_categories_name", "name"),)
