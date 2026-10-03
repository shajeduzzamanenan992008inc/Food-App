"""Order state transitions and inventory release rules."""

from ..extensions import db
from ..models import Order, Product, ProductVariant


ORDER_STATUS_TRANSITIONS = {
    "pending": {"confirmed", "declined", "cancelled"},
    "confirmed": {"preparing", "declined", "cancelled"},
    "preparing": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
    "declined": set(),
}
MAX_STOCK = 2_147_483_647


def release_reserved_stock(order):
    """Return inventory reserved by an order that is cancelled or declined."""
    for item in order.items:
        if item.variant_id:
            variant = db.session.get(ProductVariant, item.variant_id)
            if variant:
                variant.stock_quantity = min(MAX_STOCK, variant.stock_quantity + item.quantity)
        elif item.product_id:
            product = db.session.get(Product, item.product_id)
            if product:
                product.stock_quantity = min(MAX_STOCK, product.stock_quantity + item.quantity)


def transition_order(order: Order, target_status):
    """Apply an allowed status transition and release stock when appropriate."""
    if target_status not in ORDER_STATUS_TRANSITIONS.get(order.status, set()):
        return False
    if target_status in {"cancelled", "declined"}:
        release_reserved_stock(order)
    order.status = target_status
    return True
