"""Model-to-dict serializers shared by the versioned REST API."""

from flask import has_request_context
from flask_babel import get_locale


DEFAULT_LOCALE = "en_US"


def _current_locale():
    if has_request_context():
        return str(get_locale() or DEFAULT_LOCALE).replace("-", "_")
    return DEFAULT_LOCALE


def _money(value):
    # Return money as a fixed-precision string so JSON never loses cents.
    return None if value is None else f"{value:.2f}"


def _iso(value):
    return value.isoformat() if value is not None else None


def _product_sku(product):
    return next((variant.sku for variant in product.variants if variant.is_active), None)


def category_to_dict(category):
    return {
        "id": category.id,
        "name": category.name,
        "slug": category.slug,
        "description": category.description,
        "image": category.image,
        "is_active": category.is_active,
    }


def product_to_dict(product, locale=None):
    locale = locale or _current_locale()
    return {
        "id": product.id,
        "name": product.name,
        "slug": product.slug,
        "description": product.description,
        "localized_name": product.localized_name(locale),
        "localized_description": product.localized_description(locale),
        "source_language": product.original_locale,
        "price": _money(product.price),
        "discount_price": _money(product.discount_price),
        "display_price": _money(product.display_price),
        "stock": product.available_stock,
        "sku": _product_sku(product),
        "image": product.image,
        "is_available": product.is_available,
        "is_featured": product.is_featured,
        "moderation_status": product.moderation_status,
        "category_id": product.category_id,
        "seller_id": product.seller_id,
        "created_at": _iso(product.created_at),
        "updated_at": _iso(product.updated_at),
    }


def order_item_to_dict(item):
    return {
        "id": item.id,
        "product_id": item.product_id,
        "name": item.product_name,
        "price": _money(item.price),
        "quantity": item.quantity,
        "subtotal": _money(item.subtotal),
    }


def order_to_dict(order):
    return {
        "id": order.id,
        "order_number": order.order_number,
        "checkout_group": order.checkout_group,
        "status": order.status,
        "delivery_status": order.delivery_status,
        "payment_method": order.payment_method,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "email": order.email,
        "address": order.address,
        "total": _money(order.total),
        "delivery_fee": _money(order.delivery_fee),
        "items_subtotal": _money(order.items_subtotal),
        "seller_id": order.seller_id,
        "rider_id": order.rider_id,
        "created_at": _iso(order.created_at),
        "items": [order_item_to_dict(item) for item in order.items],
    }


def review_to_dict(review):
    return {
        "id": review.id,
        "product_id": review.product_id,
        "rating": review.rating,
        "comment": review.comment,
        "author_name": review.author_name,
        "status": review.status,
        "created_at": _iso(review.created_at),
    }


def notification_to_dict(notification):
    return {
        "id": notification.id,
        "type": notification.type,
        "message": notification.message,
        "link": notification.link,
        "is_read": notification.is_read,
        "created_at": _iso(notification.created_at),
    }


def user_to_dict(user):
    return {
        "id": user.id,
        "email": user.email,
        "role": user.role,
        "is_active": user.is_active,
        "preferred_locale": user.preferred_locale,
    }
