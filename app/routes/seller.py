from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, g, redirect, render_template, request, url_for
from flask_babel import gettext
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..i18n import SUPPORTED_LOCALES
from ..models import Category, Product, ProductTranslation, ProductVariant, User
from ..security import (
    approved_seller_required,
    current_approved_seller,
    current_session_user,
    role_required,
)


seller_bp = Blueprint("seller", __name__)
MAX_STOCK = 2_147_483_647


def _approved_seller():
    return getattr(g, "current_seller", None) or current_approved_seller()


def _seller_product_or_404(product_id, seller_id):
    product = db.session.scalar(
        select(Product)
        .options(selectinload(Product.translations), selectinload(Product.variants))
        .where(Product.id == product_id, Product.seller_id == seller_id)
    )
    if product is None:
        abort(404)
    return product


def _catalog_form(product=None, status=200):
    translations = {item.locale: item for item in product.translations} if product else {}
    return render_template(
        "seller/product_form.html",
        product=product,
        categories=db.session.scalars(
            select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        ).all(),
        locales=SUPPORTED_LOCALES,
        translations=translations,
        selected_category_id=request.form.get(
            "category_id", product.category_id if product else None, type=int
        ),
    ), status


def _parse_product_form(seller, product=None):
    name = request.form.get("name", "").strip()
    slug = request.form.get("slug", "").strip()
    description = request.form.get("description", "").strip()
    image = request.form.get("image", "").strip() or None
    source_locale = request.form.get("original_locale", "en_US")
    category_id = request.form.get("category_id", type=int)
    raw_stock = request.form.get("stock_quantity", "0").strip()

    if source_locale not in SUPPORTED_LOCALES:
        raise ValueError("Choose a supported source language.")
    if not 2 <= len(name) <= 160 or not description or len(description) > 10000:
        raise ValueError("Enter a product name and a description within the allowed length.")
    category = db.session.get(Category, category_id) if category_id else None
    if not category or not category.is_active:
        raise ValueError("Choose an active category.")
    if image and len(image) > 500:
        raise ValueError("The image address is too long.")
    stock = int(raw_stock)
    if not 0 <= stock <= MAX_STOCK:
        raise ValueError("Stock must be a non-negative whole number.")
    price = Decimal(request.form.get("price", ""))
    discount_text = request.form.get("discount_price", "").strip()
    discount = Decimal(discount_text) if discount_text else None

    candidate = Product(
        seller_id=seller.id,
        category_id=category.id,
        name=name,
        slug=slug,
        description=description,
        image=image,
        price=price,
        discount_price=discount,
        stock_quantity=stock,
        original_locale=source_locale,
        moderation_status="pending",
        is_available=False,
        is_featured=False,
    )
    if len(candidate.slug) > 180 or db.session.scalar(
        select(Product.id).where(Product.slug == candidate.slug, Product.id != (product.id if product else -1))
    ):
        raise ValueError("That product URL is invalid or already in use.")

    translations = {}
    for locale in SUPPORTED_LOCALES:
        if locale == source_locale:
            continue
        translated_name = request.form.get(f"translation_name_{locale}", "").strip()
        translated_description = request.form.get(f"translation_description_{locale}", "").strip()
        if translated_description and not translated_name:
            raise ValueError("Add a translated product name before its description.")
        if translated_name:
            if len(translated_name) > 160 or len(translated_description) > 10000:
                raise ValueError("A translated product field is longer than allowed.")
            translations[locale] = (translated_name, translated_description)

    if product is None:
        target = candidate
    else:
        target = product
        target.category_id = candidate.category_id
        target.name = candidate.name
        target.slug = candidate.slug
        target.description = candidate.description
        target.image = candidate.image
        target.price = candidate.price
        target.discount_price = candidate.discount_price
        target.stock_quantity = candidate.stock_quantity
        target.original_locale = candidate.original_locale
        target.moderation_status = "pending"
        target.moderation_note = None
        target.reviewed_at = None
        target.reviewed_by_id = None
        target.is_available = False

    existing_translations = {translation.locale: translation for translation in target.translations}
    for locale in SUPPORTED_LOCALES:
        if locale == source_locale:
            existing = existing_translations.pop(locale, None)
            if existing:
                target.translations.remove(existing)
            continue
        values = translations.get(locale)
        existing = existing_translations.pop(locale, None)
        if values:
            if existing:
                existing.name, existing.description = values
            else:
                target.translations.append(ProductTranslation(locale=locale, name=values[0], description=values[1]))
        elif existing:
            target.translations.remove(existing)

    for stale in existing_translations.values():
        target.translations.remove(stale)
    return target


@seller_bp.get("/seller/dashboard")
@role_required("seller")
def dashboard():
    user = current_session_user("seller")
    if not user.seller_profile:
        abort(403)
    return render_template("seller/dashboard.html", user=user, profile=user.seller_profile)


@seller_bp.get("/seller/catalog")
@approved_seller_required
def catalog():
    seller = _approved_seller()
    products = db.session.scalars(
        select(Product)
        .options(selectinload(Product.translations), selectinload(Product.variants), selectinload(Product.category))
        .where(Product.seller_id == seller.id)
        .order_by(Product.updated_at.desc(), Product.id.desc())
        .limit(100)
    ).all()
    return render_template("seller/catalog.html", products=products, seller=seller)


@seller_bp.route("/seller/products/new", methods=["GET", "POST"])
@approved_seller_required
def product_new():
    seller = _approved_seller()
    if request.method == "POST":
        try:
            product = _parse_product_form(seller)
            db.session.add(product)
            db.session.commit()
        except (KeyError, TypeError, ValueError, InvalidOperation, ArithmeticError, IntegrityError):
            db.session.rollback()
            flash(gettext("Please check the product details and try again."), "error")
            return _catalog_form(status=400)
        flash(gettext("Product submitted for Admin review."), "success")
        return redirect(url_for("seller.catalog"))
    return _catalog_form()


@seller_bp.route("/seller/products/<int:product_id>/edit", methods=["GET", "POST"])
@approved_seller_required
def product_edit(product_id):
    seller = _approved_seller()
    product = _seller_product_or_404(product_id, seller.id)
    if request.method == "POST":
        try:
            _parse_product_form(seller, product)
            db.session.commit()
        except (KeyError, TypeError, ValueError, InvalidOperation, ArithmeticError, IntegrityError):
            db.session.rollback()
            flash(gettext("Please check the product details and try again."), "error")
            return _catalog_form(product, 400)
        flash(gettext("Updated product details were sent for Admin review."), "success")
        return redirect(url_for("seller.catalog"))
    return _catalog_form(product)


@seller_bp.post("/seller/products/<int:product_id>/archive")
@approved_seller_required
def product_archive(product_id):
    seller = _approved_seller()
    product = _seller_product_or_404(product_id, seller.id)
    product.is_available = False
    product.moderation_status = "suspended"
    db.session.commit()
    flash(gettext("The product is no longer visible in the marketplace."), "success")
    return redirect(url_for("seller.catalog"))


@seller_bp.route("/seller/products/<int:product_id>/variants", methods=["GET", "POST"])
@approved_seller_required
def product_variants(product_id):
    seller = _approved_seller()
    product = _seller_product_or_404(product_id, seller.id)
    if request.method == "POST":
        sku = request.form.get("sku", "").strip().upper()
        option_name = request.form.get("option_name", "").strip()
        option_value = request.form.get("option_value", "").strip()
        try:
            stock = int(request.form.get("stock_quantity", ""))
            price_text = request.form.get("price", "").strip()
            price = Decimal(price_text) if price_text else None
            if not sku or len(sku) > 80 or not 1 <= len(option_name) <= 80 or not 1 <= len(option_value) <= 120:
                raise ValueError("Fill in the SKU and variant option.")
            if not 0 <= stock <= MAX_STOCK:
                raise ValueError("Stock must be a non-negative whole number.")
            if db.session.scalar(select(ProductVariant.id).where(ProductVariant.product_id == product.id, ProductVariant.sku == sku)):
                raise ValueError("That SKU already exists for this product.")
            variant = ProductVariant(
                product_id=product.id, sku=sku, option_name=option_name,
                option_value=option_value, price=price, stock_quantity=stock,
            )
            db.session.add(variant)
            db.session.commit()
        except (TypeError, ValueError, InvalidOperation, ArithmeticError, IntegrityError):
            db.session.rollback()
            flash(gettext("Please check the variant details and try again."), "error")
            return redirect(url_for("seller.product_variants", product_id=product.id))
        flash(gettext("Product variant added."), "success")
        return redirect(url_for("seller.product_variants", product_id=product.id))
    return render_template("seller/variants.html", product=product)


@seller_bp.post("/seller/products/<int:product_id>/variants/<int:variant_id>/toggle")
@approved_seller_required
def product_variant_delete(product_id, variant_id):
    seller = _approved_seller()
    product = _seller_product_or_404(product_id, seller.id)
    variant = db.session.get(ProductVariant, variant_id)
    if not variant or variant.product_id != product.id:
        abort(404)
    variant.is_active = not variant.is_active
    db.session.commit()
    flash(gettext("Variant availability updated."), "success")
    return redirect(url_for("seller.product_variants", product_id=product.id))


@seller_bp.post("/seller/products/<int:product_id>/variants/<int:variant_id>/stock")
@approved_seller_required
def product_variant_stock(product_id, variant_id):
    seller = _approved_seller()
    product = _seller_product_or_404(product_id, seller.id)
    variant = db.session.get(ProductVariant, variant_id)
    if not variant or variant.product_id != product.id:
        abort(404)
    try:
        stock = int(request.form.get("stock_quantity", ""))
        if not 0 <= stock <= MAX_STOCK:
            raise ValueError("Stock is outside the supported range.")
    except (TypeError, ValueError):
        flash(gettext("Enter a valid non-negative stock quantity."), "error")
        return redirect(url_for("seller.product_variants", product_id=product.id))
    variant.stock_quantity = stock
    db.session.commit()
    flash(gettext("Variant stock updated."), "success")
    return redirect(url_for("seller.product_variants", product_id=product.id))
