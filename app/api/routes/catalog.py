"""Paginated marketplace catalog and product-review API routes."""

from decimal import Decimal, InvalidOperation

from flask import Blueprint, request
from sqlalchemy import select

from ...extensions import db
from ...models import Category, Product
from ...security import current_session_user
from ...services.catalog import get_active_categories, get_catalog_products
from ...services.reviews import (
    ReviewError,
    create_review,
    rating_summary,
    reviews_for_product,
)
from ..errors import ApiError
from ..responses import created_response, paginated_response, success_response
from ..serializers import category_to_dict, product_to_dict, review_to_dict


catalog_api = Blueprint("api_catalog", __name__)


def _page_args():
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=20, type=int)
    if page is None or limit is None or page < 1 or limit < 1 or limit > 100:
        raise ApiError("Page must be positive and limit must be between 1 and 100.", "VALIDATION_ERROR", 422)
    return page, limit


def _price_arg(name):
    value = request.args.get(name, "").strip()
    if not value:
        return None
    try:
        price = Decimal(value)
    except InvalidOperation as error:
        raise ApiError(f"{name} must be a valid decimal amount.", "VALIDATION_ERROR", 422) from error
    if not price.is_finite() or price < 0 or price > Decimal("99999999.99"):
        raise ApiError(f"{name} is outside the supported range.", "VALIDATION_ERROR", 422)
    return price


def _listing(category_id_override=None):
    page, limit = _page_args()
    query = request.args.get("q", "").strip()[:100]
    category_id = (
        category_id_override
        if category_id_override is not None
        else request.args.get("category_id", type=int)
    )
    minimum = _price_arg("min_price")
    maximum = _price_arg("max_price")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ApiError("min_price cannot exceed max_price.", "VALIDATION_ERROR", 422)
    sort = request.args.get("sort", "relevance" if query else "featured")
    if sort not in {"featured", "relevance", "newest", "price_asc", "price_desc"}:
        raise ApiError("Unsupported product sort order.", "VALIDATION_ERROR", 422)
    products, pagination = get_catalog_products(
        page, limit, query, category_id, minimum, maximum, sort
    )
    return paginated_response(
        [product_to_dict(product) for product in products],
        page=pagination["page"],
        limit=limit,
        total=pagination["total"],
    )


@catalog_api.get("/products")
def list_products():
    return _listing()


@catalog_api.get("/products/<int:product_id>")
def product_detail(product_id):
    product = db.session.scalar(
        select(Product)
        .join(Product.category)
        .where(
            Product.id == product_id,
            Product.is_available.is_(True),
            Product.moderation_status == "approved",
            Category.is_active.is_(True),
        )
    )
    if product is None:
        raise ApiError("Product not found.", "NOT_FOUND", 404)
    return success_response(product_to_dict(product))


@catalog_api.get("/categories")
def list_categories():
    return success_response([category_to_dict(category) for category in get_active_categories()])


@catalog_api.get("/categories/<slug>")
def category_products(slug):
    category = db.session.scalar(
        select(Category).where(Category.slug == slug, Category.is_active.is_(True))
    )
    if category is None:
        raise ApiError("Category not found.", "NOT_FOUND", 404)
    return _listing(category_id_override=category.id)


@catalog_api.get("/search")
def search_products():
    if not request.args.get("q", "").strip():
        raise ApiError("A search query is required.", "VALIDATION_ERROR", 422)
    return _listing()


@catalog_api.get("/products/<int:product_id>/reviews")
def list_product_reviews(product_id):
    product = db.session.get(Product, product_id)
    if product is None:
        raise ApiError("Product not found.", "NOT_FOUND", 404)
    return success_response(
        {
            "product_id": product_id,
            "summary": rating_summary(product_id),
            "reviews": [review_to_dict(review) for review in reviews_for_product(product_id)],
        }
    )


@catalog_api.post("/products/<int:product_id>/reviews")
def submit_product_review(product_id):
    user = current_session_user()
    if user is None or user.role != "customer":
        raise ApiError("Sign in as a customer to write a review.", "UNAUTHENTICATED", 401)
    product = db.session.get(Product, product_id)
    if product is None:
        raise ApiError("Product not found.", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or request.form
    try:
        review = create_review(
            user, product, payload.get("rating"), payload.get("comment", "")
        )
    except ReviewError as error:
        raise ApiError(str(error), "REVIEW_NOT_ALLOWED", 422)
    return created_response(review_to_dict(review), "Review submitted for moderation.")
