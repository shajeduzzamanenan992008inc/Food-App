from decimal import Decimal, InvalidOperation
from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, session, url_for
from flask_babel import gettext
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..extensions import db
from ..i18n import SUPPORTED_LOCALES

from ..services.catalog import (
    get_active_categories,
    get_category_by_slug,
    get_catalog_products,
    get_home_products,
    get_product_by_slug,
    get_reference_food_categories,
    get_reference_foods,
    search_suggestions,
)
from ..services.reviews import (
    ReviewError,
    create_review,
    eligible_order_id,
    rating_summary,
    reviews_for_product,
)
from ..services.wishlist import has as wishlist_has


main_bp = Blueprint("main", __name__)


def _price_filter(name):
    raw_value = request.args.get(name, "").strip()
    if not raw_value:
        return None
    try:
        price = Decimal(raw_value)
    except InvalidOperation:
        abort(400)
    if not price.is_finite() or price < 0 or price > Decimal("99999999.99"):
        abort(400)
    return price


@main_bp.post("/language")
def set_language():
    locale = request.form.get("locale", "")
    if locale not in SUPPORTED_LOCALES:
        abort(400)

    destination = request.form.get("next", "/")
    parsed = urlsplit(destination)
    if (
        not destination.startswith("/")
        or destination.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or "\\" in destination
        or any(ord(character) < 32 for character in destination)
    ):
        destination = url_for("main.index")

    user = getattr(g, "current_user", None)
    if user:
        user.preferred_locale = locale
        try:
            db.session.commit()
        except SQLAlchemyError:
            db.session.rollback()
            flash(gettext("We could not save your language preference. Please try again."), "error")
            return redirect(destination)

    session["locale"] = locale
    flash(gettext("Language preference updated."), "success")
    return redirect(destination)


@main_bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Readiness check could not reach the database.")
        return {"status": "unavailable"}, 503
    return {"status": "ok"}, 200


@main_bp.get("/health/db")
def health_db():
    """Dedicated database readiness probe for deployment checks."""
    try:
        db.session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.exception("Database readiness check failed.")
        return {"status": "unavailable"}, 503
    return {"status": "ok"}, 200


@main_bp.get("/")
def index():
    return render_template(
        "home.html",
        categories=get_active_categories(),
        products=get_home_products(),
        current_user_id=session.get("user_id"),
    )


@main_bp.get("/menu")
def menu():
    page = max(1, request.args.get("page", 1, type=int))
    reference_page = max(1, request.args.get("ref_page", 1, type=int))
    category_id = request.args.get("category_id", type=int)
    reference_category_id = request.args.get("ref_category_id", type=int)
    query = request.args.get("q", "").strip()[:current_app.config["MAX_SEARCH_LENGTH"]]
    min_price = _price_filter("min_price")
    max_price = _price_filter("max_price")
    if min_price is not None and max_price is not None and min_price > max_price:
        abort(400)
    sort = request.args.get("sort", "featured")
    if sort not in {"featured", "relevance", "newest", "price_asc", "price_desc"}:
        abort(400)
    products, pagination = get_catalog_products(
        page,
        current_app.config["CATALOG_PAGE_SIZE"],
        query=query,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )
    reference_categories = []
    reference_foods = []
    reference_pagination = None
    if query or category_id is not None:
        if reference_category_id is not None:
            reference_categories = get_reference_food_categories()
            if reference_category_id not in {category.id for category, _ in reference_categories}:
                reference_category_id = None
        reference_foods, reference_pagination = get_reference_foods(
            reference_page,
            min(current_app.config["CATALOG_PAGE_SIZE"], 20),
            category_id=reference_category_id,
            query=query,
        )
    return render_template(
        "catalog/menu.html",
        categories=get_active_categories(),
        products=products,
        pagination=pagination,
        query=query,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
        selected_category_id=category_id,
        selected_reference_category_id=reference_category_id,
        reference_categories=reference_categories,
        reference_foods=reference_foods,
        reference_pagination=reference_pagination,
    )


@main_bp.get("/category/<slug>")
def category(slug):
    selected = get_category_by_slug(slug)
    if selected is None:
        abort(404)
    min_price = _price_filter("min_price")
    max_price = _price_filter("max_price")
    if min_price is not None and max_price is not None and min_price > max_price:
        abort(400)
    sort = request.args.get("sort", "featured")
    if sort not in {"featured", "relevance", "newest", "price_asc", "price_desc"}:
        abort(400)
    products, pagination = get_catalog_products(
        max(1, request.args.get("page", 1, type=int)),
        current_app.config["CATALOG_PAGE_SIZE"],
        category_id=selected.id,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )
    return render_template(
        "catalog/category.html",
        category=selected,
        products=products,
        pagination=pagination,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )


@main_bp.get("/food/<slug>")
def food(slug):
    product = get_product_by_slug(slug)
    if product is None:
        abort(404)
    user = getattr(g, "current_user", None)
    return render_template(
        "catalog/food.html",
        product=product,
        reviews=reviews_for_product(product.id),
        rating=rating_summary(product.id),
        is_saved=bool(user and user.role == "customer" and wishlist_has(user, product.id)),
        can_review=(
            user is not None
            and user.role == "customer"
            and eligible_order_id(user, product.id) is not None
        ),
    )


@main_bp.post("/food/<slug>/reviews")
def submit_review(slug):
    """Accept a purchase-verified product review for moderation."""
    product = get_product_by_slug(slug)
    if product is None:
        abort(404)
    user = getattr(g, "current_user", None)
    if user is None or user.role != "customer":
        flash(gettext("Sign in to review this product."), "error")
        return redirect(url_for("auth.login"))
    try:
        create_review(user, product, request.form.get("rating"), request.form.get("comment", ""))
    except ReviewError as error:
        db.session.rollback()
        flash(str(error), "error")
    else:
        flash(gettext("Thanks! Your review is waiting for moderation."), "success")
    return redirect(url_for("main.food", slug=slug))


@main_bp.get("/search")
def search():
    query = request.args.get("q", "").strip()[:current_app.config["MAX_SEARCH_LENGTH"]]
    if not query:
        return redirect(url_for("main.menu"))
    page = max(1, request.args.get("page", 1, type=int))
    category_id = request.args.get("category_id", type=int)
    min_price = _price_filter("min_price")
    max_price = _price_filter("max_price")
    if min_price is not None and max_price is not None and min_price > max_price:
        abort(400)
    sort = request.args.get("sort", "relevance")
    if sort not in {"featured", "relevance", "newest", "price_asc", "price_desc"}:
        abort(400)
    products, pagination = get_catalog_products(
        page,
        current_app.config["CATALOG_PAGE_SIZE"],
        query=query,
        category_id=category_id,
        min_price=min_price,
        max_price=max_price,
        sort=sort,
    )
    reference_foods, reference_pagination = get_reference_foods(
        page, min(current_app.config["CATALOG_PAGE_SIZE"], 20), query=query
    )
    return render_template(
        "catalog/menu.html",
        categories=get_active_categories(),
        products=products,
        pagination=pagination,
        query=query,
        sort=sort,
        min_price=min_price,
        max_price=max_price,
        selected_category_id=category_id,
        selected_reference_category_id=None,
        reference_categories=[],
        reference_foods=reference_foods,
        reference_pagination=reference_pagination,
    )


@main_bp.get("/api/search-suggestions")
def search_suggestions_api():
    products = search_suggestions(request.args.get("q", ""))
    return jsonify([
        {"name": product.name, "slug": product.slug, "price": f"{product.display_price:.2f}"}
        for product in products
    ])
