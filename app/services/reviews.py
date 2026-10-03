"""Product reviews: purchase eligibility, submission, aggregation, moderation."""

from flask_babel import gettext
from sqlalchemy import func, select

from ..extensions import db
from ..models import Order, OrderItem, Review


class ReviewError(Exception):
    """Raised when a review cannot be created for a business reason."""


def reviews_for_product(product_id, status="approved"):
    """Return a product's reviews, newest first (approved by default)."""
    statement = select(Review).where(Review.product_id == product_id)
    if status is not None:
        statement = statement.where(Review.status == status)
    return db.session.scalars(statement.order_by(Review.created_at.desc())).all()


def rating_summary(product_id):
    count, average = db.session.execute(
        select(func.count(Review.id), func.avg(Review.rating)).where(
            Review.product_id == product_id, Review.status == "approved"
        )
    ).one()
    count = count or 0
    return {
        "count": count,
        "average": round(float(average), 1) if count and average is not None else None,
    }


def pending_reviews(limit=100):
    return db.session.scalars(
        select(Review)
        .where(Review.status == "pending")
        .order_by(Review.created_at.asc())
        .limit(limit)
    ).all()


def eligible_order_id(user, product_id):
    """Return a delivered order the user can still review this product with, else None."""
    if user is None or getattr(user, "id", None) is None:
        return None
    reviewed_orders = select(Review.order_id).where(
        Review.product_id == product_id, Review.user_id == user.id
    )
    return db.session.scalar(
        select(OrderItem.order_id)
        .join(Order, Order.id == OrderItem.order_id)
        .where(
            OrderItem.product_id == product_id,
            Order.user_id == user.id,
            Order.status == "delivered",
            OrderItem.order_id.not_in(reviewed_orders),
        )
        .order_by(OrderItem.order_id.desc())
    )


def author_name(user):
    """Return a display name snapshot for a review author."""
    profile = getattr(user, "customer_profile", None)
    if profile and profile.full_name:
        return profile.full_name[:120]
    return (user.email or "Customer")[:120]


def create_review(user, product, rating, comment=""):
    """Create a pending review for a delivered purchase, or raise ReviewError."""
    if user is None:
        raise ReviewError(gettext("Sign in to review this product."))
    order_id = eligible_order_id(user, product.id)
    if order_id is None:
        raise ReviewError(gettext("You can review a product after your order is delivered."))
    try:
        rating_value = int(rating)
    except (TypeError, ValueError) as error:
        raise ReviewError(gettext("Choose a rating from 1 to 5 stars.")) from error
    if not 1 <= rating_value <= 5:
        raise ReviewError(gettext("Choose a rating from 1 to 5 stars."))
    clean_comment = (comment or "").strip()
    if len(clean_comment) > 2000:
        raise ReviewError(gettext("Your review must be 2000 characters or fewer."))
    review = Review(
        product_id=product.id,
        user_id=user.id,
        order_id=order_id,
        rating=rating_value,
        comment=clean_comment or None,
        author_name=author_name(user),
        status="pending",
    )
    db.session.add(review)
    db.session.commit()
    return review
