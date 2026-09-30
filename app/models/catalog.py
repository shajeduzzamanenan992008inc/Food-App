import re
from datetime import datetime, timezone
from decimal import Decimal
from urllib.parse import urlparse

from sqlalchemy.orm import validates

from ..extensions import db


class CatalogTimestampMixin:
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = db.Column(
        db.DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class Category(CatalogTimestampMixin, db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    slug = db.Column(db.String(120), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=True)
    image = db.Column(db.String(500), nullable=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    __table_args__ = (db.CheckConstraint("length(trim(name)) > 0", name="ck_category_name_nonempty"),)

    products = db.relationship("Product", back_populates="category", lazy="select", cascade="save-update")

    @property
    def display_image(self):
        return self.image or {
            "burgers": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=900&q=80",
            "pizza": "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?auto=format&fit=crop&w=900&q=80",
            "drinks": "https://images.unsplash.com/photo-1544145945-f90425340c7e?auto=format&fit=crop&w=900&q=80",
            "chicken": "https://images.unsplash.com/photo-1598103442097-8b74394b95c6?auto=format&fit=crop&w=900&q=80",
        }.get(self.slug)

    @validates("slug")
    def validate_slug(self, key, value):
        normalized = re.sub(r"[^a-z0-9-]+", "-", (value or "").strip().lower()).strip("-")
        if not normalized:
            raise ValueError("Category slug must contain letters or numbers.")
        return normalized

    @validates("image")
    def validate_image(self, key, value):
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            raise ValueError("Image must be an HTTP(S) URL or a relative path.")
        if value.startswith("//") or value.startswith("data:"):
            raise ValueError("Unsafe image reference.")
        return value


class Product(CatalogTimestampMixin, db.Model):
    __tablename__ = "products"

    id = db.Column(db.Integer, primary_key=True)
    seller_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    name = db.Column(db.String(160), nullable=False, index=True)
    slug = db.Column(db.String(180), unique=True, nullable=False, index=True)
    description = db.Column(db.Text, nullable=False)
    image = db.Column(db.String(500), nullable=True)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    discount_price = db.Column(db.Numeric(10, 2), nullable=True)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    original_locale = db.Column(db.String(12), nullable=False, default="en_US", server_default="en_US")
    moderation_status = db.Column(db.String(20), nullable=False, default="approved", server_default="approved", index=True)
    moderation_note = db.Column(db.String(500), nullable=True)
    reviewed_at = db.Column(db.DateTime(timezone=True), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    is_available = db.Column(db.Boolean, nullable=False, default=True, index=True)
    is_featured = db.Column(db.Boolean, nullable=False, default=False, index=True)
    __table_args__ = (
        db.CheckConstraint("length(trim(name)) > 0", name="ck_product_name_nonempty"),
        db.CheckConstraint("price >= 0", name="ck_product_price_nonnegative"),
        db.CheckConstraint(
            "discount_price IS NULL OR (discount_price >= 0 AND discount_price < price)",
            name="ck_product_discount_valid",
        ),
        db.CheckConstraint("stock_quantity >= 0", name="ck_product_stock_nonnegative"),
        db.CheckConstraint(
            "moderation_status IN ('pending', 'approved', 'rejected', 'suspended')",
            name="ck_product_moderation_status_valid",
        ),
        db.Index("ix_products_available_featured_name", "is_available", "is_featured", "name"),
    )

    category = db.relationship("Category", back_populates="products")
    seller = db.relationship("User", foreign_keys=[seller_id])
    reviewer = db.relationship("User", foreign_keys=[reviewed_by_id])
    translations = db.relationship(
        "ProductTranslation", back_populates="product", cascade="all, delete-orphan", lazy="selectin"
    )
    variants = db.relationship(
        "ProductVariant", back_populates="product", cascade="all, delete-orphan", lazy="selectin",
        order_by="ProductVariant.id",
    )

    _locale_labels = {
        "en_US": "English (US)", "bn_BD": "বাংলা", "hi_IN": "हिन्दी", "ar": "العربية",
    }

    def _localized_text(self, field, locale):
        translation = next((item for item in self.translations if item.locale == locale), None)
        translated = getattr(translation, field, None) if translation else None
        if translated:
            return translated
        original = getattr(self, field)
        if locale and locale != self.original_locale:
            language = self._locale_labels.get(self.original_locale, self.original_locale)
            return f"{original} ({language})"
        return original

    def localized_name(self, locale):
        return self._localized_text("name", locale)

    def localized_description(self, locale):
        return self._localized_text("description", locale)

    @property
    def available_stock(self):
        active_variants = [variant for variant in self.variants if variant.is_active]
        return sum(variant.stock_quantity for variant in active_variants) if active_variants else self.stock_quantity

    @property
    def display_image(self):
        return self.image or {
            "burgers": "https://images.unsplash.com/photo-1568901346375-23c9450c58cd?auto=format&fit=crop&w=900&q=80",
            "pizza": "https://images.unsplash.com/photo-1574071318508-1cdbab80d002?auto=format&fit=crop&w=900&q=80",
            "drinks": "https://images.unsplash.com/photo-1544145945-f90425340c7e?auto=format&fit=crop&w=900&q=80",
            "chicken": "https://images.unsplash.com/photo-1598103442097-8b74394b95c6?auto=format&fit=crop&w=900&q=80",
        }.get(self.category.slug)

    @validates("slug")
    def validate_slug(self, key, value):
        normalized = re.sub(r"[^a-z0-9-]+", "-", (value or "").strip().lower()).strip("-")
        if not normalized:
            raise ValueError("Product slug must contain letters or numbers.")
        return normalized

    @validates("price", "discount_price")
    def validate_price(self, key, value):
        amount = Decimal(str(value)) if value is not None else None
        if amount is not None:
            if not amount.is_finite() or amount < 0 or amount > Decimal("99999999.99"):
                raise ValueError("Product prices must be finite and within the supported range.")
            if amount != amount.quantize(Decimal("0.01")):
                raise ValueError("Product prices can have at most two decimal places.")
        if key == "discount_price" and amount is not None and self.price is not None and amount >= self.price:
            raise ValueError("Discount price must be lower than the regular price.")
        return amount

    @validates("stock_quantity")
    def validate_stock_quantity(self, key, value):
        try:
            quantity = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Stock must be a whole number.") from error
        if isinstance(value, bool) or quantity < 0 or quantity > 2_147_483_647:
            raise ValueError("Stock quantity is outside the supported range.")
        return quantity

    @validates("original_locale")
    def validate_original_locale(self, key, value):
        if value not in self._locale_labels:
            raise ValueError("Choose a supported source language.")
        return value

    @validates("moderation_status")
    def validate_moderation_status(self, key, value):
        if value not in {"pending", "approved", "rejected", "suspended"}:
            raise ValueError("Invalid product moderation status.")
        return value

    @validates("image")
    def validate_image(self, key, value):
        if value is None:
            return None
        parsed = urlparse(value)
        if parsed.scheme and parsed.scheme not in {"http", "https"}:
            raise ValueError("Image must be an HTTP(S) URL or a relative path.")
        if value.startswith("//") or value.startswith("data:"):
            raise ValueError("Unsafe image reference.")
        return value

    @property
    def display_price(self):
        return self.discount_price if self.discount_price is not None else self.price


class ProductTranslation(CatalogTimestampMixin, db.Model):
    __tablename__ = "product_translations"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    locale = db.Column(db.String(12), nullable=False)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, nullable=False, default="")
    __table_args__ = (
        db.UniqueConstraint("product_id", "locale", name="uq_product_translation_locale"),
        db.CheckConstraint("locale IN ('en_US', 'bn_BD', 'hi_IN', 'ar')", name="ck_product_translation_locale"),
        db.CheckConstraint("length(trim(name)) > 0", name="ck_product_translation_name_nonempty"),
    )

    product = db.relationship("Product", back_populates="translations")


class ProductVariant(CatalogTimestampMixin, db.Model):
    __tablename__ = "product_variants"

    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    sku = db.Column(db.String(80), nullable=False)
    option_name = db.Column(db.String(80), nullable=False)
    option_value = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=True)
    stock_quantity = db.Column(db.Integer, nullable=False, default=0, server_default="0")
    is_active = db.Column(db.Boolean, nullable=False, default=True, index=True)
    __table_args__ = (
        db.UniqueConstraint("product_id", "sku", name="uq_product_variant_sku"),
        db.CheckConstraint("length(trim(sku)) > 0", name="ck_product_variant_sku_nonempty"),
        db.CheckConstraint("stock_quantity >= 0", name="ck_product_variant_stock_nonnegative"),
        db.CheckConstraint("price IS NULL OR price >= 0", name="ck_product_variant_price_nonnegative"),
    )

    product = db.relationship("Product", back_populates="variants")

    @validates("stock_quantity")
    def validate_stock_quantity(self, key, value):
        try:
            quantity = int(value)
        except (TypeError, ValueError) as error:
            raise ValueError("Stock must be a whole number.") from error
        if isinstance(value, bool) or quantity < 0 or quantity > 2_147_483_647:
            raise ValueError("Stock quantity is outside the supported range.")
        return quantity

    @validates("price")
    def validate_variant_price(self, key, value):
        amount = Decimal(str(value)) if value is not None else None
        if amount is not None and (not amount.is_finite() or amount < 0 or amount > Decimal("99999999.99")):
            raise ValueError("Variant price is outside the supported range.")
        if amount is not None and amount != amount.quantize(Decimal("0.01")):
            raise ValueError("Variant prices can have at most two decimal places.")
        return amount
