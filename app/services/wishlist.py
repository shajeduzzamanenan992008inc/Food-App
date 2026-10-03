"""Customer wishlist (saved products)."""

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Product, WishlistItem


def add(user, product):
    """Add a product to the user's wishlist. Idempotent; returns (item, created)."""
    if user is None or product is None:
        return None, False
    existing = db.session.scalar(
        select(WishlistItem).where(
            WishlistItem.user_id == user.id, WishlistItem.product_id == product.id
        )
    )
    if existing is not None:
        return existing, False
    item = WishlistItem(user_id=user.id, product_id=product.id)
    db.session.add(item)
    db.session.commit()
    return item, True


def remove(user, product_id):
    """Remove a product from the user's wishlist. Returns True when a row was removed."""
    if user is None:
        return False
    result = db.session.execute(
        delete(WishlistItem).where(
            WishlistItem.user_id == user.id, WishlistItem.product_id == product_id
        )
    )
    db.session.commit()
    return bool(result.rowcount)


def has(user, product_id):
    """Return True when the product is already saved by the user."""
    if user is None:
        return False
    return db.session.scalar(
        select(WishlistItem.id).where(
            WishlistItem.user_id == user.id, WishlistItem.product_id == product_id
        )
    ) is not None


def saved_product_ids(user):
    if user is None:
        return set()
    return set(
        db.session.scalars(
            select(WishlistItem.product_id).where(WishlistItem.user_id == user.id)
        ).all()
    )


def count(user):
    if user is None:
        return 0
    return len(saved_product_ids(user))


def products_for(user):
    """Return the user's saved products that are still active, newest first."""
    if user is None:
        return []
    return db.session.scalars(
        select(Product)
        .join(WishlistItem, WishlistItem.product_id == Product.id)
        .options(selectinload(Product.category))
        .where(WishlistItem.user_id == user.id)
        .order_by(WishlistItem.created_at.desc(), WishlistItem.id.desc())
    ).all()