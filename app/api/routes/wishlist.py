"""Wishlist API routes."""

from flask import Blueprint, request

from ...extensions import db
from ...models import Product
from ...security import current_session_user
from ...services.wishlist import add, count, products_for, remove
from ..errors import ApiError
from ..responses import created_response, success_response
from ..serializers import product_to_dict


wishlist_api = Blueprint("api_wishlist", __name__)


def _current_user():
    user = current_session_user()
    if user is None or user.role != "customer":
        raise ApiError("Sign in as a customer to use your wishlist.", "UNAUTHENTICATED", 401)
    return user


def _payload():
    return request.get_json(silent=True) or request.form


@wishlist_api.get("/wishlist")
def list_wishlist():
    user = _current_user()
    products = products_for(user)
    return success_response({"count": len(products), "products": [product_to_dict(item) for item in products]})


@wishlist_api.post("/wishlist/items")
def add_wishlist_item():
    user = _current_user()
    product_id = _payload().get("product_id")
    try:
        product_id = int(product_id)
    except (TypeError, ValueError):
        raise ApiError("A valid product_id is required.", "VALIDATION_ERROR", 422)
    product = db.session.get(Product, product_id)
    if product is None:
        raise ApiError("Product not found.", "NOT_FOUND", 404)
    item, was_created = add(user, product)
    message = "Saved to your wishlist." if was_created else "Already in your wishlist."
    return created_response({"product_id": product.id, "saved": True}, message)


@wishlist_api.delete("/wishlist/items/<int:product_id>")
def remove_wishlist_item(product_id):
    user = _current_user()
    removed = remove(user, product_id)
    return success_response({"product_id": product_id, "removed": removed}, "Wishlist updated.")