"""Shared server-authoritative COD checkout for HTML and API clients."""

from decimal import Decimal
from uuid import uuid4

from flask import url_for
from flask_babel import gettext
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from ..extensions import db
from ..models import Order, OrderItem, Product, ProductVariant
from .mail import enqueue_order_emails
from .notifications import notify


DELIVERY_FEE = Decimal("2.50")


class CheckoutError(ValueError):
    """A safe checkout validation or inventory error suitable for clients."""


def create_checkout_orders(user, rows, *, name, phone, address, email, payment_method):
    """Validate current inventory, reserve it, split seller orders, and commit."""
    if not rows:
        raise CheckoutError(gettext("Your cart is empty."))
    if (
        not email or len(email) > 255 or "@" not in email
        or "." not in email.rsplit("@", 1)[-1]
    ):
        raise CheckoutError(gettext("Please provide a valid email address for order updates."))
    if payment_method != "cod":
        raise CheckoutError(gettext("Please choose a supported payment method."))
    if not 2 <= len(name) <= 120 or not 7 <= len(phone) <= 30 or not 8 <= len(address) <= 2000:
        raise CheckoutError(gettext("Please provide a valid name, phone, and delivery address."))

    for row in rows:
        product = db.session.scalar(
            select(Product)
            .options(selectinload(Product.category))
            .where(Product.id == row["product"].id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if not product or not product.is_available or not product.category.is_active:
            raise CheckoutError(gettext("A cart item is no longer available. Please review your cart."))

        variant = None
        if row.get("variant_id"):
            variant = db.session.scalar(
                select(ProductVariant)
                .where(
                    ProductVariant.id == row["variant_id"],
                    ProductVariant.product_id == product.id,
                    ProductVariant.is_active.is_(True),
                )
                .with_for_update()
                .execution_options(populate_existing=True)
            )
            if variant is None:
                raise CheckoutError(gettext("A cart option is no longer available. Please review your cart."))
        elif db.session.scalar(
            select(ProductVariant.id).where(
                ProductVariant.product_id == product.id,
                ProductVariant.is_active.is_(True),
            ).limit(1)
        ):
            raise CheckoutError(gettext("Choose a product option before checkout."))

        stock = variant.stock_quantity if variant else product.stock_quantity
        if stock < row["quantity"]:
            raise CheckoutError(
                gettext("Not enough stock is available for one or more items. Please update your cart.")
            )
        if variant:
            variant.stock_quantity -= row["quantity"]
            row["variant_label"] = f"{variant.option_name}: {variant.option_value}"
            row["sku_snapshot"] = variant.sku
            row["price"] = variant.price if variant.price is not None else product.display_price
        else:
            product.stock_quantity -= row["quantity"]
            row["variant_label"] = None
            row["sku_snapshot"] = None
            row["price"] = product.display_price
        row["product"] = product
        row["variant_id"] = variant.id if variant else None
        row["subtotal"] = row["price"] * row["quantity"]
        row["seller_id"] = product.seller_id

    checkout_group = f"FB-{uuid4().hex.upper()}"
    seller_groups = {}
    for row in rows:
        seller_groups.setdefault(row["seller_id"], []).append(row)
    orders = []
    for index, (seller_id, group_rows) in enumerate(seller_groups.items(), start=1):
        subtotal = sum((row["subtotal"] for row in group_rows), Decimal("0.00"))
        order = Order(
            order_number=f"{checkout_group}-{index}",
            checkout_group=checkout_group,
            user_id=user.id if user else None,
            seller_id=seller_id,
            customer_name=name,
            phone=phone,
            email=email,
            address=address,
            delivery_fee=DELIVERY_FEE,
            total=subtotal + DELIVERY_FEE,
            payment_method=payment_method,
            status="pending",
        )
        for row in group_rows:
            order.items.append(OrderItem(
                product_id=row["product"].id,
                variant_id=row.get("variant_id"),
                variant_label=row.get("variant_label"),
                sku_snapshot=row.get("sku_snapshot"),
                product_name=row["product"].name,
                price=row["price"],
                quantity=row["quantity"],
                subtotal=row["subtotal"],
            ))
        db.session.add(order)
        orders.append(order)
    db.session.commit()

    for order in orders:
        enqueue_order_emails(order)
        confirmation_link = url_for("orders.confirmation", order_number=order.order_number)
        if order.user_id:
            notify(
                order.user_id,
                gettext("Order %(number)s was received.", number=order.order_number),
                type="order",
                link=confirmation_link,
            )
        if order.seller_id:
            notify(
                order.seller_id,
                gettext("New order %(number)s for your store.", number=order.order_number),
                type="order",
                link=url_for("seller.dashboard"),
            )
    return orders
