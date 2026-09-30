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
    get_category_products,
    get_home_products,
    get_menu_products,
    get_product_by_slug,
    get_reference_food_categories,
    get_reference_foods,
    search_products,
    search_suggestions,
)


main_bp = Blueprint("main", __name__)


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
    query = request.args.get("q", "").strip()[:current_app.config["MAX_SEARCH_LENGTH"]]
    products, pagination = get_menu_products(page, current_app.config["CATALOG_PAGE_SIZE"])
    reference_categories = []
    reference_foods = []
    reference_pagination = None
    if query or category_id is not None:
        if category_id is not None:
            reference_categories = get_reference_food_categories()
            if category_id not in {category.id for category, _ in reference_categories}:
                category_id = None
        reference_foods, reference_pagination = get_reference_foods(
            reference_page,
            min(current_app.config["CATALOG_PAGE_SIZE"], 20),
            category_id=category_id,
            query=query,
        )
    return render_template(
        "catalog/menu.html",
        categories=get_active_categories(),
        products=products,
        pagination=pagination,
        query=query,
        reference_categories=reference_categories,
        reference_foods=reference_foods,
        reference_pagination=reference_pagination,
        selected_category_id=category_id,
    )


@main_bp.get("/category/<slug>")
def category(slug):
    selected = get_category_by_slug(slug)
    if selected is None:
        abort(404)
    products, pagination = get_category_products(
        selected,
        max(1, request.args.get("page", 1, type=int)),
        current_app.config["CATALOG_PAGE_SIZE"],
    )
    return render_template(
        "catalog/category.html",
        category=selected,
        products=products,
        pagination=pagination,
    )


@main_bp.get("/food/<slug>")
def food(slug):
    product = get_product_by_slug(slug)
    if product is None:
        abort(404)
    return render_template("catalog/food.html", product=product)


@main_bp.get("/search")
def search():
    query = request.args.get("q", "").strip()[:current_app.config["MAX_SEARCH_LENGTH"]]
    if not query:
        return redirect(url_for("main.menu"))
    page = max(1, request.args.get("page", 1, type=int))
    products, pagination = search_products(query, page, current_app.config["CATALOG_PAGE_SIZE"])
    reference_foods, reference_pagination = get_reference_foods(
        page, min(current_app.config["CATALOG_PAGE_SIZE"], 20), query=query
    )
    return render_template(
        "catalog/menu.html",
        categories=get_active_categories(),
        products=products,
        pagination=pagination,
        query=query,
        reference_categories=[],
        reference_foods=reference_foods,
        reference_pagination=reference_pagination,
        selected_category_id=None,
    )


@main_bp.get("/api/search-suggestions")
def search_suggestions_api():
    products = search_suggestions(request.args.get("q", ""))
    return jsonify([
        {"name": product.name, "slug": product.slug, "price": f"{product.display_price:.2f}"}
        for product in products
    ])
