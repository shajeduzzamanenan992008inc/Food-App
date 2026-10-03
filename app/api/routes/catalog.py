"""Catalog API routes: product reviews (products/categories are added later)."""

from flask import Blueprint, request

from ...extensions import db
from ...models import Product
from ...security import current_session_user
from ...services.reviews import (
    ReviewError,
    create_review,
    rating_summary,
    reviews_for_product,
)
from ..errors import ApiError
from ..responses import created_response, success_response
from ..serializers import review_to_dict


catalog_api = Blueprint("api_catalog", __name__)


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
