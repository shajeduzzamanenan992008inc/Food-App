"""Admin operations API, scoped to active administrator accounts."""

from datetime import datetime, timezone

from flask import Blueprint, request, url_for
from flask_babel import gettext
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from ...extensions import db
from ...models import Category, Order, Product, Review, SellerProfile, User
from ...services.audit import record_audit
from ...services.mail import queue_order_receipt, queue_order_status
from ...services.notifications import notify
from ...services.orders import transition_order
from ...security import current_session_user
from ..errors import ApiError
from ..responses import paginated_response, success_response
from ..serializers import order_to_dict, product_to_dict, review_to_dict, user_to_dict


admin_api = Blueprint("api_admin", __name__, url_prefix="/admin")


def _admin():
    user = current_session_user()
    if user is None:
        raise ApiError("Sign in as an administrator to continue.", "UNAUTHENTICATED", 401)
    if user.role != "admin":
        raise ApiError("Administrator access is required.", "FORBIDDEN", 403)
    return user


def _page():
    page = request.args.get("page", default=1, type=int)
    limit = request.args.get("limit", default=20, type=int)
    if page is None or limit is None or page < 1 or not 1 <= limit <= 100:
        raise ApiError("Page must be positive and limit must be between 1 and 100.", "VALIDATION_ERROR", 422)
    return page, limit, (page - 1) * limit


def _paged(statement, model, serializer):
    page, limit, offset = _page()
    total = db.session.scalar(select(func.count()).select_from(statement.order_by(None).subquery())) or 0
    rows = db.session.scalars(statement.limit(limit).offset(offset)).all()
    return paginated_response(
        [serializer(row) for row in rows], page=page, limit=limit, total=total
    )


@admin_api.get("/dashboard")
def dashboard():
    _admin()
    return success_response({
        "users": db.session.scalar(select(func.count(User.id))) or 0,
        "customers": db.session.scalar(select(func.count(User.id)).where(User.role == "customer")) or 0,
        "sellers": db.session.scalar(select(func.count(User.id)).where(User.role == "seller")) or 0,
        "pending_sellers": db.session.scalar(
            select(func.count(SellerProfile.id)).where(SellerProfile.approval_status == "pending")
        ) or 0,
        "products": db.session.scalar(select(func.count(Product.id))) or 0,
        "pending_products": db.session.scalar(
            select(func.count(Product.id)).where(Product.moderation_status == "pending")
        ) or 0,
        "orders": db.session.scalar(select(func.count(Order.id))) or 0,
        "pending_orders": db.session.scalar(
            select(func.count(Order.id)).where(Order.status == "pending")
        ) or 0,
        "pending_reviews": db.session.scalar(
            select(func.count(Review.id)).where(Review.status == "pending")
        ) or 0,
    })


@admin_api.get("/users")
def users():
    _admin()
    return _paged(select(User).order_by(User.created_at.desc(), User.id.desc()), User, user_to_dict)


@admin_api.patch("/users/<int:user_id>")
def update_user(user_id):
    admin = _admin()
    user = db.session.get(User, user_id)
    if user is None:
        raise ApiError("User not found.", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    is_active = payload.get("is_active")
    if user.role == "admin" or not isinstance(is_active, bool):
        raise ApiError("Only a boolean is_active value for a non-admin account is supported.", "VALIDATION_ERROR", 422)
    if user.is_active != is_active:
        user.is_active = is_active
        user.auth_version += 1
        db.session.commit()
        record_audit(
            "account.activated" if is_active else "account.deactivated",
            actor=admin,
            target_type="user",
            target_id=user.id,
        )
    return success_response(user_to_dict(user), "User status updated.")


@admin_api.get("/sellers")
def sellers():
    _admin()
    statement = (
        select(SellerProfile)
        .options(selectinload(SellerProfile.user))
        .order_by(SellerProfile.created_at.desc(), SellerProfile.id.desc())
    )
    return _paged(statement, SellerProfile, lambda profile: {
        "id": profile.id,
        "user_id": profile.user_id,
        "email": profile.user.email,
        "store_name": profile.store_name,
        "contact_name": profile.contact_name,
        "approval_status": profile.approval_status,
        "review_note": profile.review_note,
    })


@admin_api.get("/categories")
def categories():
    _admin()
    statement = select(Category).order_by(Category.name.asc())
    return _paged(statement, Category, lambda category: {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "is_active": category.is_active,
    })


@admin_api.post("/categories")
def create_category():
    admin = _admin()
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", "")).strip()
    slug = str(payload.get("slug", "")).strip()
    if not 2 <= len(name) <= 100 or not slug:
        raise ApiError("Enter a category name and slug.", "VALIDATION_ERROR", 422)
    category = Category(
        name=name,
        slug=slug,
        description=str(payload.get("description", "")).strip() or None,
        image=payload.get("image"),
        is_active=True,
    )
    try:
        db.session.add(category)
        db.session.commit()
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        raise ApiError("Category details are invalid or already in use.", "CONFLICT", 409) from error
    record_audit("category.create", actor=admin, target_type="category", target_id=category.id)
    return success_response({"id": category.id, "name": category.name, "slug": category.slug}, "Category created.", 201)


@admin_api.patch("/categories/<int:category_id>")
def update_category(category_id):
    admin = _admin()
    category = db.session.get(Category, category_id)
    if category is None:
        raise ApiError("Category not found.", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    try:
        if "name" in payload:
            name = str(payload["name"]).strip()
            if not 2 <= len(name) <= 100:
                raise ValueError
            category.name = name
        if "slug" in payload:
            category.slug = str(payload["slug"]).strip()
        if "description" in payload:
            category.description = str(payload["description"]).strip() or None
        if "image" in payload:
            category.image = payload["image"]
        if "is_active" in payload:
            if not isinstance(payload["is_active"], bool):
                raise ValueError
            category.is_active = payload["is_active"]
            if not category.is_active:
                for product in category.products:
                    product.is_available = False
        db.session.commit()
    except (ValueError, IntegrityError) as error:
        db.session.rollback()
        raise ApiError("Category update is invalid or conflicts with an existing category.", "CONFLICT", 409) from error
    record_audit("category.update", actor=admin, target_type="category", target_id=category.id)
    return success_response({"id": category.id, "name": category.name, "slug": category.slug, "is_active": category.is_active})


@admin_api.delete("/categories/<int:category_id>")
def deactivate_category(category_id):
    admin = _admin()
    category = db.session.get(Category, category_id)
    if category is None:
        raise ApiError("Category not found.", "NOT_FOUND", 404)
    category.is_active = False
    for product in category.products:
        product.is_available = False
    db.session.commit()
    record_audit("category.deactivate", actor=admin, target_type="category", target_id=category.id)
    return success_response({"id": category.id, "is_active": False}, "Category deactivated.")


@admin_api.get("/products")
def products():
    _admin()
    statement = select(Product).options(selectinload(Product.variants)).order_by(
        Product.created_at.desc(), Product.id.desc()
    )
    return _paged(statement, Product, product_to_dict)


@admin_api.get("/orders")
def orders():
    _admin()
    statement = select(Order).options(selectinload(Order.items)).order_by(
        Order.created_at.desc(), Order.id.desc()
    )
    return _paged(statement, Order, order_to_dict)


@admin_api.get("/reviews")
def reviews():
    _admin()
    statement = select(Review).order_by(Review.created_at.desc(), Review.id.desc())
    return _paged(statement, Review, review_to_dict)


@admin_api.patch("/reviews/<int:review_id>")
def moderate_review(review_id):
    admin = _admin()
    review = db.session.get(Review, review_id)
    if review is None:
        raise ApiError("Review not found.", "NOT_FOUND", 404)
    if review.status != "pending":
        raise ApiError("Review has already been moderated.", "CONFLICT", 409)
    payload = request.get_json(silent=True) or {}
    status = payload.get("status")
    if status not in {"approved", "rejected"}:
        raise ApiError("status must be approved or rejected.", "VALIDATION_ERROR", 422)
    note = str(payload.get("moderation_note", "")).strip()
    if len(note) > 500:
        raise ApiError("Moderation note must be 500 characters or fewer.", "VALIDATION_ERROR", 422)
    review.status = status
    review.moderation_note = note or None
    review.moderated_at = datetime.now(timezone.utc)
    review.moderated_by_id = admin.id
    db.session.commit()
    record_audit("review.moderate", actor=admin, target_type="review", target_id=review.id, detail=status)
    return success_response(review_to_dict(review), "Review moderated.")


@admin_api.patch("/sellers/<int:profile_id>")
def review_seller(profile_id):
    admin = _admin()
    profile = db.session.get(SellerProfile, profile_id)
    if profile is None:
        raise ApiError("Seller not found.", "NOT_FOUND", 404)
    if profile.approval_status != "pending":
        raise ApiError("Seller application has already been reviewed.", "CONFLICT", 409)
    payload = request.get_json(silent=True) or {}
    decision = payload.get("approval_status")
    if decision not in {"approved", "rejected"}:
        raise ApiError("approval_status must be approved or rejected.", "VALIDATION_ERROR", 422)
    note = str(payload.get("review_note", "")).strip()
    if len(note) > 500:
        raise ApiError("Review note must be 500 characters or fewer.", "VALIDATION_ERROR", 422)
    profile.approval_status = decision
    profile.review_note = note or None
    profile.reviewed_at = datetime.now(timezone.utc)
    profile.reviewed_by_id = admin.id
    db.session.commit()
    record_audit("seller.review", actor=admin, target_type="seller_profile", target_id=profile.id, detail=decision)
    if decision == "approved":
        notify(
            profile.user_id,
            gettext("Your store was approved. You can now publish products."),
            type="account",
            link=url_for("seller.dashboard"),
        )
    return success_response({"id": profile.id, "approval_status": profile.approval_status})


@admin_api.patch("/products/<int:product_id>")
def moderate_product(product_id):
    admin = _admin()
    product = db.session.get(Product, product_id)
    if product is None or product.seller_id is None:
        raise ApiError("Seller product not found.", "NOT_FOUND", 404)
    if product.moderation_status != "pending":
        raise ApiError("Product has already been reviewed.", "CONFLICT", 409)
    payload = request.get_json(silent=True) or {}
    decision = payload.get("moderation_status")
    if decision not in {"approved", "rejected"}:
        raise ApiError("moderation_status must be approved or rejected.", "VALIDATION_ERROR", 422)
    note = str(payload.get("moderation_note", "")).strip()
    if len(note) > 500:
        raise ApiError("Moderation note must be 500 characters or fewer.", "VALIDATION_ERROR", 422)
    product.moderation_status = decision
    product.is_available = decision == "approved"
    product.moderation_note = note or None
    product.reviewed_at = datetime.now(timezone.utc)
    product.reviewed_by_id = admin.id
    db.session.commit()
    record_audit("catalog.product_review", actor=admin, target_type="product", target_id=product.id, detail=decision)
    return success_response({"id": product.id, "moderation_status": product.moderation_status})


@admin_api.patch("/orders/<int:order_id>")
def update_order(order_id):
    admin = _admin()
    order = db.session.scalar(
        select(Order).options(selectinload(Order.items)).where(Order.id == order_id)
    )
    if order is None:
        raise ApiError("Order not found.", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    target = payload.get("status")
    if not isinstance(target, str) or not transition_order(order, target):
        raise ApiError("That order status transition is not allowed.", "INVALID_TRANSITION", 409)
    db.session.commit()
    record_audit("order.status", actor=admin, target_type="order", target_id=order.id, detail=target)
    queue_order_status(order)
    if target == "confirmed":
        queue_order_receipt(order)
    if order.user_id:
        notify(
            order.user_id,
            gettext("Order %(number)s is now %(status)s.", number=order.order_number, status=target),
            type="order",
            link=url_for("orders.confirmation", order_number=order.order_number),
        )
    return success_response(order_to_dict(order), "Order status updated.")
