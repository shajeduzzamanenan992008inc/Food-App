"""Seller-specific, localized PDF invoices.

Invoices are generated with ReportLab. A Unicode TrueType font is registered
when available (``INVOICE_FONT_PATH`` or a common system font) so Bengali,
Hindi, and Arabic text render correctly; otherwise the built-in Helvetica font
is used and non-Latin characters are replaced rather than raising.
"""

from contextlib import nullcontext
from decimal import Decimal
from io import BytesIO
from pathlib import Path

from flask import current_app, has_request_context
from flask_babel import force_locale, format_datetime, gettext
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


FONT_NAME = "NexHaatInvoice"
_FONT_CANDIDATES = (
    "C:/Windows/Fonts/Nirmala.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansBengali-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)
_registered_paths = set()


def _invoice_font():
    """Return (font_name, supports_unicode). Prefer a Unicode TTF when found."""
    configured = (current_app.config.get("INVOICE_FONT_PATH") or "").strip()
    candidates = ([configured] if configured else []) + list(_FONT_CANDIDATES)
    for candidate in candidates:
        if not candidate:
            continue
        path = Path(candidate)
        if not path.is_file():
            continue
        key = str(path)
        if key not in _registered_paths:
            try:
                pdfmetrics.registerFont(TTFont(FONT_NAME, key))
            except Exception:
                continue
            _registered_paths.add(key)
        return FONT_NAME, True
    return "Helvetica", False


def _safe(text, unicode_ok):
    value = str(text)
    if unicode_ok:
        return value
    return value.encode("latin-1", "replace").decode("latin-1")


def _localized_item_name(item, products, locale):
    product = products.get(item.product_id)
    if product is None or not locale:
        return item.product_name
    return product.localized_name(locale)


def build_invoice_pdf(order, locale=None, restaurant_name="NexHaat"):
    """Build a seller-specific invoice PDF and return the raw bytes."""
    request_context = nullcontext() if has_request_context() else current_app.test_request_context("/")
    with request_context, force_locale(locale or current_app.config.get("BABEL_DEFAULT_LOCALE", "en_US")):
        return _render_invoice(order, locale, restaurant_name)


def _render_invoice(order, locale, restaurant_name):
    from sqlalchemy import select

    from ..extensions import db
    from ..models import Product

    product_ids = [item.product_id for item in order.items if item.product_id]
    products = {}
    if product_ids:
        products = {
            product.id: product
            for product in db.session.scalars(select(Product).where(Product.id.in_(product_ids)))
        }

    font, unicode_ok = _invoice_font()
    buffer = BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    left = 56.7
    right = width - 56.7
    y = height - 64

    def line(text, size=11, gap=16):
        nonlocal y
        pdf.setFont(font, size)
        pdf.drawString(left, y, _safe(text, unicode_ok))
        y -= gap

    pdf.setFont(font, 20)
    pdf.drawString(left, y, _safe(restaurant_name, unicode_ok))
    pdf.setFont(font, 13)
    pdf.drawRightString(right, y, _safe(gettext("INVOICE"), unicode_ok))
    y -= 30

    store = None
    if order.seller is not None and order.seller.seller_profile is not None:
        store = order.seller.seller_profile.store_name
    if store:
        line(gettext("Seller: %(store)s", store=store))
    line(f"{gettext('Invoice number')}: {order.order_number}")
    if order.created_at is not None:
        line(f"{gettext('Date')}: {format_datetime(order.created_at, format='medium')}")
    line(f"{gettext('Payment method')}: {gettext('Cash on delivery')}")
    y -= 6

    pdf.setFont(font, 11)
    pdf.drawString(left, y, _safe(gettext("Bill to"), unicode_ok))
    y -= 15
    for detail in (order.customer_name, order.phone, order.email or "", order.address):
        if detail:
            line(detail, size=10, gap=14)
    y -= 12

    pdf.setFont(font, 11)
    pdf.drawString(left, y, _safe(gettext("Item"), unicode_ok))
    pdf.drawString(left + 300, y, _safe(gettext("Qty"), unicode_ok))
    pdf.drawRightString(left + 400, y, _safe(gettext("Price"), unicode_ok))
    pdf.drawRightString(right, y, _safe(gettext("Subtotal"), unicode_ok))
    y -= 6
    pdf.line(left, y, right, y)
    y -= 16

    for item in order.items:
        name = (_localized_item_name(item, products, locale) or "")[:42]
        pdf.setFont(font, 10)
        pdf.drawString(left, y, _safe(name, unicode_ok))
        pdf.drawString(left + 300, y, _safe(str(item.quantity), unicode_ok))
        pdf.drawRightString(left + 400, y, _safe(f"{Decimal(item.price):.2f}", unicode_ok))
        pdf.drawRightString(right, y, _safe(f"{Decimal(item.subtotal):.2f}", unicode_ok))
        y -= 16

    y -= 6
    pdf.line(left + 300, y, right, y)
    y -= 18

    def total_row(label, amount, bold=False):
        nonlocal y
        pdf.setFont(font, 12 if bold else 11)
        pdf.drawString(left + 300, y, _safe(label, unicode_ok))
        pdf.drawRightString(right, y, _safe(f"৳{Decimal(amount):.2f}", unicode_ok))
        y -= 18

    delivery_fee = getattr(order, "delivery_fee", None) or Decimal("0.00")
    total_row(gettext("Subtotal"), getattr(order, "items_subtotal", Decimal("0.00")))
    total_row(gettext("Delivery"), delivery_fee)
    total_row(gettext("Total"), order.total, bold=True)

    y -= 10
    pdf.setFont(font, 10)
    pdf.drawString(left, y, _safe(gettext("Thank you for ordering with NexHaat."), unicode_ok))

    pdf.showPage()
    pdf.save()
    return buffer.getvalue()
