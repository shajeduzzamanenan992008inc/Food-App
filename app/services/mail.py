import logging
import os
import requests
import base64
from contextlib import nullcontext
from threading import Thread
from flask import current_app, has_request_context, render_template
from flask_babel import force_locale, gettext, lazy_gettext
from sqlalchemy import select

from ..extensions import db
from ..models import Order
from .invoice import build_invoice_pdf

logger = logging.getLogger(__name__)

def _send(template, subject, recipients, attachments=None, locale=None, **context):
    request_context = nullcontext() if has_request_context() else current_app.test_request_context("/")
    with request_context:
        with force_locale(locale or current_app.config.get("BABEL_DEFAULT_LOCALE", "en_US")):
            return _send_for_locale(template, subject, recipients, attachments, context)


def _send_for_locale(template, subject, recipients, attachments, context):
    subject = str(subject) if not isinstance(subject, str) else gettext(subject)
    recipients_list = [{"email": address} for address in recipients if address]
    if not recipients_list:
        logger.warning("Skipping %s email: no recipient address.", template)
        return False

    # Get Brevo API Key
    api_key = current_app.config.get("BREVO_API_KEY") or os.environ.get("BREVO_API_KEY")
    sender_email = current_app.config.get("MAIL_DEFAULT_SENDER") or os.environ.get("MAIL_DEFAULT_SENDER")

    if not api_key:
        logger.warning("Skipping %s email: BREVO_API_KEY is not configured.", template)
        return False

    try:
        html_content = render_template(f"email/{template}.html", **context)
    except Exception:
        html_content = render_template(f"email/{template}.txt", **context)

    # Prepare Payload for Brevo API
    payload = {
        "sender": {"email": sender_email, "name": "NexHaat"},
        "to": recipients_list,
        "subject": subject,
        "htmlContent": html_content
    }

    if attachments:
        brevo_attachments = []
        for filename, content, content_type in attachments:
            if isinstance(content, str):
                content = content.encode("utf-8")
            b64_content = base64.b64encode(content).decode("utf-8")
            brevo_attachments.append({
                "name": filename,
                "content": b64_content
            })
        payload["attachment"] = brevo_attachments

    headers = {
        "accept": "application/json",
        "api-key": api_key,
        "content-type": "application/json"
    }

    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=current_app.config.get("MAIL_TIMEOUT", 15),
        )
        response.raise_for_status()
        return True
    except Exception as e:
        logger.exception("Email delivery failed for template %s: %s", template, e)
        return False

def send_order_confirmation(order):
    sent = send_order_pending(order)
    admin_email = (
        current_app.config.get("ADMIN_EMAIL")
        or current_app.config.get("MAIL_DEFAULT_SENDER")
    )
    if admin_email:
        _send(
            "admin_order",
            f"New order received: {order.order_number}",
            [admin_email],
            order=order,
            restaurant_name="NexHaat",
        )
    return sent

def queue_order_confirmation(order_number):
    app = current_app._get_current_object()

    def deliver():
        with app.app_context():
            try:
                order = db.session.scalar(
                    select(Order).where(Order.order_number == order_number)
                )
                if order is None:
                    logger.error("Cannot send order email: order %s was not found.", order_number)
                    return
                send_order_confirmation(order)
            finally:
                db.session.remove()

    Thread(
        target=deliver,
        name=f"order-email-{order_number}",
        daemon=True,
    ).start()

def send_order_pending(order):
    return _send(
        "order_pending",
        f"NexHaat order received: {order.order_number}",
        [order.email],
        order=order,
        restaurant_name="NexHaat",
    )

def send_order_receipt(order):
    try:
        invoice = build_invoice_pdf(order)
    except Exception:
        logger.exception("Invoice generation failed for order %s", order.order_number)
        invoice = None
    attachments = (
        [(f"NexHaat-Invoice-{order.order_number}.pdf", invoice, "application/pdf")]
        if invoice
        else []
    )
    return _send(
        "order_receipt",
        f"Your NexHaat receipt and invoice: {order.order_number}",
        [order.email],
        attachments=attachments,
        order=order,
        restaurant_name="NexHaat",
    )

def send_order_status(order):
    return _send(
        "order_status",
        f"Order {order.order_number} is {order.status.title()}",
        [order.email],
        order=order,
        restaurant_name="NexHaat",
    )

def send_password_reset_code(recipient, code, locale=None):
    return _send(
        "password_reset_code",
        lazy_gettext("Your NexHaat password reset code"),
        [recipient],
        code=code,
        restaurant_name="NexHaat",
        locale=locale,
    )


def queue_password_reset_code(recipient, code, locale=None):
    """Send reset mail off the request path to avoid account timing leaks."""
    app = current_app._get_current_object()

    def deliver():
        with app.app_context():
            try:
                send_password_reset_code(recipient, code, locale=locale)
            finally:
                db.session.remove()

    Thread(target=deliver, name="password-reset-email", daemon=True).start()


def queue_account_invitation(recipient, invitation_url, role, locale=None):
    """Deliver a short-lived staff setup link without exposing its token in logs."""
    app = current_app._get_current_object()

    def deliver():
        with app.app_context():
            try:
                _send(
                    "account_invitation",
                    "Your NexHaat team invitation",
                    [recipient],
                    invitation_url=invitation_url,
                    role=role,
                    locale=locale,
                )
            finally:
                db.session.remove()

    Thread(target=deliver, name="account-invitation-email", daemon=True).start()
