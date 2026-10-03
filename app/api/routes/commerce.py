"""Session-cart, checkout, customer-order, and seller-order API routes."""

from decimal import Decimal, InvalidOperation
import re

from flask import Blueprint, request, session, url_for
from flask_babel import gettext
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from ...extensions import db
from ...models import Category, Order, Product, ProductTranslation, ProductVariant
from ...i18n import SUPPORTED_LOCALES
from ...routes.orders import _cart_key, cart_rows, parse_quantity
from ...security import current_session_user
from ...services.audit import record_audit
from ...services.checkout import CheckoutError, create_checkout_orders
from ...services.mail import queue_order_status
from ...services.notifications import notify
from ...services.orders import transition_order
from ..errors import ApiError
from ..responses import created_response, success_response
from ..serializers import order_to_dict, product_to_dict


commerce_api = Blueprint("api_commerce", __name__)


def _customer():
    user = current_session_user()
    if user is None:
        raise ApiError("Sign in as a customer to continue.", "UNAUTHENTICATED", 401)
    if user.role != "customer":
        raise ApiError("This action is only available to customers.", "FORBIDDEN", 403)
    return user


def _seller():
    user = current_session_user()
    if user is None:
        raise ApiError("Sign in as an approved seller to continue.", "UNAUTHENTICATED", 401)
    if (
        user.role != "seller" or not user.seller_profile
        or user.seller_profile.approval_status != "approved"
    ):
        raise ApiError("An approved seller account is required.", "FORBIDDEN", 403)
    return user


def _cart_data():
    rows, subtotal = cart_rows()
    return {
        "items": [
            {
                "key": row["cart_key"],
                "product_id": row["product"].id,
                "variant_id": row["variant_id"],
                "variant_label": row["variant_label"],
                "sku": row["variant"].sku if row["variant"] else None,
                "name": row["product"].name,
                "price": f"{row['price']:.2f}",
                "quantity": row["quantity"],
                "available_stock": row["available_stock"],
                "subtotal": f"{row['subtotal']:.2f}",
            }
            for row in rows
        ],
        "subtotal": f"{subtotal:.2f}",
        "delivery_fee": f"{Decimal('2.50'):.2f}" if rows else "0.00",
        "total": f"{(subtotal + Decimal('2.50')):.2f}" if rows else "0.00",
    }


@commerce_api.get("/cart")
def get_cart():
    _customer()
    return success_response(_cart_data())


@commerce_api.post("/cart/items")
def add_cart_item():
    _customer()
    payload = request.get_json(silent=True) or {}
    product_id = payload.get("product_id")
    if isinstance(product_id, bool) or not isinstance(product_id, int):
        raise ApiError("product_id must be an integer.", "VALIDATION_ERROR", 422)
    product = db.session.get(Product, product_id)
    if not product or not product.is_available or not product.category.is_active:
        raise ApiError("Product is unavailable.", "NOT_FOUND", 404)
    variant_id = payload.get("variant_id")
    active_variants = [variant for variant in product.variants if variant.is_active]
    variant = next((item for item in active_variants if item.id == variant_id), None)
    if active_variants and variant is None:
        raise ApiError("Choose an active product variant.", "VALIDATION_ERROR", 422)
    if variant_id is not None and variant is None:
        raise ApiError("Product variant not found.", "NOT_FOUND", 404)
    stock = variant.stock_quantity if variant else product.stock_quantity
    if stock <= 0:
        raise ApiError("Product is out of stock.", "OUT_OF_STOCK", 409)
    quantity = payload.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 20:
        raise ApiError("quantity must be between 1 and 20.", "VALIDATION_ERROR", 422)
    key = _cart_key(product.id, variant.id if variant else None)
    cart = session.get("cart", {})
    requested = parse_quantity(cart.get(key), default=0) + quantity
    if requested > stock:
        raise ApiError("Requested quantity exceeds available stock.", "OUT_OF_STOCK", 409)
    cart[key] = requested
    session["cart"] = cart
    return created_response(_cart_data(), "Cart item added.")


@commerce_api.patch("/cart/items/<path:cart_key>")
def update_cart_item(cart_key):
    _customer()
    payload = request.get_json(silent=True) or {}
    quantity = payload.get("quantity")
    if isinstance(quantity, bool) or not isinstance(quantity, int) or not 0 <= quantity <= 20:
        raise ApiError("quantity must be between 0 and 20.", "VALIDATION_ERROR", 422)
    cart = session.get("cart", {})
    if cart_key not in cart:
        raise ApiError("Cart item not found.", "NOT_FOUND", 404)
    if quantity == 0:
        cart.pop(cart_key, None)
    else:
        (product_id, variant_id) = (int(part) for part in cart_key.split(":", 1)) if ":" in cart_key else (int(cart_key), None)
        product = db.session.get(Product, product_id)
        variant = db.session.get(ProductVariant, variant_id) if variant_id else None
        if not product or not product.is_available or (variant_id and (not variant or not variant.is_active)):
            raise ApiError("Cart item is unavailable.", "NOT_FOUND", 404)
        stock = variant.stock_quantity if variant else product.stock_quantity
        if quantity > stock:
            raise ApiError("Requested quantity exceeds available stock.", "OUT_OF_STOCK", 409)
        cart[cart_key] = quantity
    session["cart"] = cart
    return success_response(_cart_data())


@commerce_api.delete("/cart/items/<path:cart_key>")
def remove_cart_item(cart_key):
    _customer()
    cart = session.get("cart", {})
    if cart_key not in cart:
        raise ApiError("Cart item not found.", "NOT_FOUND", 404)
    cart.pop(cart_key, None)
    session["cart"] = cart
    return success_response(_cart_data(), "Cart item removed.")


@commerce_api.delete("/cart")
def clear_cart():
    _customer()
    session["cart"] = {}
    return success_response(_cart_data(), "Cart cleared.")


@commerce_api.post("/checkout/preview")
def checkout_preview():
    _customer()
    rows, _subtotal = cart_rows()
    if not rows:
        raise ApiError("Your cart is empty.", "EMPTY_CART", 409)
    groups = {}
    for row in rows:
        group = groups.setdefault(row["seller_id"], {"items": [], "subtotal": Decimal("0.00")})
        group["items"].append({
            "product_id": row["product"].id,
            "variant_id": row["variant_id"],
            "name": row["product"].name,
            "variant_label": row["variant_label"],
            "quantity": row["quantity"],
            "unit_price": f"{row['price']:.2f}",
            "subtotal": f"{row['subtotal']:.2f}",
        })
        group["subtotal"] += row["subtotal"]
    return success_response({
        "orders": [
            {
                "seller_id": seller_id,
                "items": group["items"],
                "subtotal": f"{group['subtotal']:.2f}",
                "delivery_fee": "2.50",
                "total": f"{group['subtotal'] + Decimal('2.50'):.2f}",
            }
            for seller_id, group in groups.items()
        ]
    })


@commerce_api.post("/checkout")
def checkout():
    user = _customer()
    rows, _subtotal = cart_rows()
    payload = request.get_json(silent=True) or {}
    try:
        orders = create_checkout_orders(
            user,
            rows,
            name=str(payload.get("customer_name", "")).strip(),
            phone=str(payload.get("phone", "")).strip(),
            address=str(payload.get("address", "")).strip(),
            email=user.email,
            payment_method=str(payload.get("payment_method", "")).strip().lower(),
        )
    except CheckoutError as error:
        db.session.rollback()
        status = 409 if "stock" in str(error).lower() or "cart" in str(error).lower() else 422
        raise ApiError(str(error), "CHECKOUT_REJECTED", status) from error
    session["cart"] = {}
    return created_response(
        {"orders": [order_to_dict(order) for order in orders]},
        "Order placed.",
    )


@commerce_api.get("/orders")
def customer_orders():
    user = _customer()
    orders = db.session.scalars(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(100)
    ).all()
    return success_response([order_to_dict(order) for order in orders])


@commerce_api.get("/orders/<order_number>")
def customer_order_detail(order_number):
    user = _customer()
    order = db.session.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.order_number == order_number, Order.user_id == user.id)
    )
    if order is None:
        raise ApiError("Order not found.", "NOT_FOUND", 404)
    return success_response(order_to_dict(order))


@commerce_api.post("/orders/<order_number>/cancel")
def cancel_customer_order(order_number):
    user = _customer()
    order = db.session.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.order_number == order_number, Order.user_id == user.id)
        .with_for_update()
    )
    if order is None:
        raise ApiError("Order not found.", "NOT_FOUND", 404)
    if order.status not in {"pending", "confirmed"} or not transition_order(order, "cancelled"):
        raise ApiError("This order can no longer be cancelled.", "INVALID_TRANSITION", 409)
    db.session.commit()
    record_audit("order.cancel", actor=user, target_type="order", target_id=order.id)
    queue_order_status(order)
    return success_response(order_to_dict(order), "Order cancelled.")


@commerce_api.get("/seller/orders")
def seller_orders():
    user = _seller()
    orders = db.session.scalars(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.seller_id == user.id)
        .order_by(Order.created_at.desc())
        .limit(100)
    ).all()
    return success_response([order_to_dict(order) for order in orders])


@commerce_api.get("/seller/dashboard")
def seller_dashboard():
    user = _seller()
    return success_response({
        "products": db.session.scalar(
            select(func.count(Product.id)).where(Product.seller_id == user.id)
        ) or 0,
        "active_products": db.session.scalar(
            select(func.count(Product.id)).where(
                Product.seller_id == user.id, Product.is_available.is_(True)
            )
        ) or 0,
        "pending_orders": db.session.scalar(
            select(func.count(Order.id)).where(
                Order.seller_id == user.id, Order.status == "pending"
            )
        ) or 0,
        "completed_orders": db.session.scalar(
            select(func.count(Order.id)).where(
                Order.seller_id == user.id, Order.status == "delivered"
            )
        ) or 0,
        "sales": f"{db.session.scalar(
            select(func.coalesce(func.sum(Order.total), 0)).where(
                Order.seller_id == user.id, Order.status == "delivered"
            )
        ) or Decimal('0.00'):.2f}",
    })


@commerce_api.get("/seller/products")
def seller_products():
    user = _seller()
    products = db.session.scalars(
        select(Product)
        .options(selectinload(Product.variants), selectinload(Product.translations))
        .where(Product.seller_id == user.id)
        .order_by(Product.updated_at.desc(), Product.id.desc())
        .limit(100)
    ).all()
    return success_response([product_to_dict(product) for product in products])


def _seller_product_payload(payload, product=None):
    name = str(payload.get("name", "")).strip()
    description = str(payload.get("description", "")).strip()
    slug = str(payload.get("slug", "")).strip() or re.sub(
        r"[^a-z0-9-]+", "-", name.lower()
    ).strip("-")
    category_id = payload.get("category_id")
    locale = payload.get("original_locale", "en_US")
    if not 2 <= len(name) <= 160 or not description or len(description) > 10000:
        raise ApiError("Enter a product name and description within the allowed length.", "VALIDATION_ERROR", 422)
    if locale not in SUPPORTED_LOCALES:
        raise ApiError("Choose a supported source language.", "VALIDATION_ERROR", 422)
    if isinstance(category_id, bool) or not isinstance(category_id, int):
        raise ApiError("category_id must be an integer.", "VALIDATION_ERROR", 422)
    category = db.session.get(Category, category_id)
    if not category or not category.is_active:
        raise ApiError("Choose an active category.", "VALIDATION_ERROR", 422)
    try:
        price = Decimal(str(payload.get("price", "")))
        discount = (
            Decimal(str(payload["discount_price"]))
            if payload.get("discount_price") not in (None, "") else None
        )
        stock = int(payload.get("stock_quantity", 0))
    except (InvalidOperation, TypeError, ValueError) as error:
        raise ApiError("Enter valid price and stock values.", "VALIDATION_ERROR", 422) from error
    if (
        not price.is_finite() or price < 0 or price > Decimal("99999999.99")
        or price != price.quantize(Decimal("0.01"))
        or (discount is not None and (
            not discount.is_finite() or discount < 0 or discount >= price
            or discount != discount.quantize(Decimal("0.01"))
        ))
    ):
        raise ApiError("Enter a valid price and lower optional discount price.", "VALIDATION_ERROR", 422)
    if not 0 <= stock <= 2_147_483_647:
        raise ApiError("Stock must be a non-negative whole number.", "VALIDATION_ERROR", 422)
    duplicate = db.session.scalar(
        select(Product.id).where(Product.slug == slug, Product.id != (product.id if product else -1))
    )
    if not slug or len(slug) > 180 or duplicate:
        raise ApiError("That product URL is invalid or already in use.", "CONFLICT", 409)
    return {
        "name": name,
        "description": description,
        "slug": slug,
        "category_id": category.id,
        "original_locale": locale,
        "price": price,
        "discount_price": discount,
        "stock_quantity": stock,
    }


def _apply_translations(product, payload):
    translations = payload.get("translations", {})
    if not isinstance(translations, dict):
        raise ApiError("translations must be an object keyed by locale.", "VALIDATION_ERROR", 422)
    existing = {translation.locale: translation for translation in product.translations}
    for locale, values in translations.items():
        if locale not in SUPPORTED_LOCALES or locale == product.original_locale or not isinstance(values, dict):
            raise ApiError("A translation has an unsupported locale or shape.", "VALIDATION_ERROR", 422)
        translated_name = str(values.get("name", "")).strip()
        translated_description = str(values.get("description", "")).strip()
        if not translated_name or len(translated_name) > 160 or len(translated_description) > 10000:
            raise ApiError("Translated name and description are invalid.", "VALIDATION_ERROR", 422)
        translation = existing.pop(locale, None)
        if translation:
            translation.name = translated_name
            translation.description = translated_description
        else:
            product.translations.append(ProductTranslation(
                locale=locale, name=translated_name, description=translated_description
            ))
    for stale in existing.values():
        product.translations.remove(stale)


@commerce_api.post("/seller/products")
def create_seller_product():
    user = _seller()
    payload = request.get_json(silent=True) or {}
    fields = _seller_product_payload(payload)
    product = Product(
        seller_id=user.id,
        **fields,
        moderation_status="pending",
        is_available=False,
        is_featured=False,
    )
    _apply_translations(product, payload)
    db.session.add(product)
    db.session.commit()
    return created_response(product_to_dict(product), "Product submitted for Admin review.")


@commerce_api.patch("/seller/products/<int:product_id>")
def update_seller_product(product_id):
    user = _seller()
    product = db.session.scalar(
        select(Product)
        .options(selectinload(Product.translations), selectinload(Product.variants))
        .where(Product.id == product_id, Product.seller_id == user.id)
    )
    if product is None:
        raise ApiError("Product not found.", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    fields = _seller_product_payload(payload, product)
    for key, value in fields.items():
        setattr(product, key, value)
    product.moderation_status = "pending"
    product.moderation_note = None
    product.reviewed_at = None
    product.reviewed_by_id = None
    product.is_available = False
    _apply_translations(product, payload)
    db.session.commit()
    return success_response(product_to_dict(product), "Updated product submitted for Admin review.")


@commerce_api.delete("/seller/products/<int:product_id>")
def deactivate_seller_product(product_id):
    user = _seller()
    product = db.session.scalar(
        select(Product).where(Product.id == product_id, Product.seller_id == user.id)
    )
    if product is None:
        raise ApiError("Product not found.", "NOT_FOUND", 404)
    product.is_available = False
    product.moderation_status = "suspended"
    db.session.commit()
    return success_response({"id": product.id, "is_available": False}, "Product deactivated.")


@commerce_api.patch("/seller/orders/<int:order_id>")
def update_seller_order(order_id):
    user = _seller()
    order = db.session.scalar(
        select(Order)
        .options(selectinload(Order.items))
        .where(Order.id == order_id, Order.seller_id == user.id)
    )
    if order is None:
        raise ApiError("Order not found.", "NOT_FOUND", 404)
    payload = request.get_json(silent=True) or {}
    target = payload.get("status")
    if target not in {"confirmed", "preparing", "declined"} or not transition_order(order, target):
        raise ApiError("That order status transition is not allowed.", "INVALID_TRANSITION", 409)
    db.session.commit()
    record_audit("order.status", actor=user, target_type="order", target_id=order.id, detail=target)
    queue_order_status(order)
    if order.user_id:
        notify(
            order.user_id,
            gettext("Order %(number)s is now %(status)s.", number=order.order_number, status=target),
            type="order",
            link=url_for("orders.confirmation", order_number=order.order_number),
        )
    return success_response(order_to_dict(order), "Order status updated.")
