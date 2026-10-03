import base64
import json
import logging
import os
from contextlib import nullcontext
from threading import Thread

import requests
from flask import current_app, has_request_context, render_template
from flask_babel import force_locale, gettext, lazy_gettext
from sqlalchemy import select

from ..extensions import db
from ..i18n import SUPPORTED_LOCALES
from ..models import OutboundEmail
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
        if current_app.config.get("ENVIRONMENT") == "production":
            logger.warning("Skipping %s email: BREVO_API_KEY is not configured.", template)
        else:
            # Local development without a configured mail provider: log the
            # message so developers can read one-time codes and invitation
            # links from the console. Production requires a real provider.
            try:
                preview = render_template(f"email/{template}.html", **context)
            except Exception:
                try:
                    preview = render_template(f"email/{template}.txt", **context)
                except Exception:
                    preview = "(preview unavailable)"
            logger.warning(
                "DEV ONLY: %s email for %s (mail provider not configured):\n%s",
                template,
                ", ".join(item["email"] for item in recipients_list),
                preview,
            )
        return False

    try:
        html_content = render_template(f"email/{template}.html", **context)
    except Exception:
        html_content = render_template(f"email/{template}.txt", **context)

    return _post_brevo(
        subject,
        [item["email"] for item in recipients_list],
        html_content,
        attachments,
        api_key,
        sender_email,
    )

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

def _encode_attachments(attachments):
    if not attachments:
        return None
    encoded = []
    for filename, content, content_type in attachments:
        if isinstance(content, str):
            content = content.encode("utf-8")
        encoded.append({
            "name": filename,
            "content_type": content_type,
            "content": base64.b64encode(content).decode("utf-8"),
        })
    return json.dumps(encoded)


def _decode_attachments(blob):
    if not blob:
        return []
    return [
        (item["name"], base64.b64decode(item["content"]), item.get("content_type"))
        for item in json.loads(blob)
    ]


def _max_attempts():
    return max(1, int(current_app.config.get("MAX_EMAIL_ATTEMPTS", 5)))


def _render_message(template, subject, locale, attachments, context):
    """Render an email in the target locale and encode any attachments."""
    request_context = nullcontext() if has_request_context() else current_app.test_request_context("/")
    with request_context:
        with force_locale(locale or current_app.config.get("BABEL_DEFAULT_LOCALE", "en_US")):
            rendered_subject = str(subject) if not isinstance(subject, str) else gettext(subject)
            try:
                html = render_template(f"email/{template}.html", **context)
            except Exception:
                html = render_template(f"email/{template}.txt", **context)
            encoded = _encode_attachments(attachments)
    return rendered_subject, html, encoded


def _post_brevo(subject, recipients, html_content, attachments, api_key, sender_email):
    payload = {
        "sender": {"email": sender_email, "name": "NexHaat"},
        "to": [{"email": address} for address in recipients],
        "subject": subject,
        "htmlContent": html_content,
    }
    if attachments:
        payload["attachment"] = [
            {"name": name, "content": base64.b64encode(content).decode("utf-8")}
            for name, content, _content_type in attachments
        ]
    headers = {"accept": "application/json", "api-key": api_key, "content-type": "application/json"}
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers=headers,
            timeout=current_app.config.get("MAIL_TIMEOUT", 15),
        )
        response.raise_for_status()
        return True
    except Exception as error:  # noqa: BLE001 - never surface provider or credential details
        logger.warning("Email delivery attempt failed (%s).", error.__class__.__name__)
        return False
def deliver_outbound_email(record):
    """Attempt one queued email and record the outcome (safe to retry)."""
    recipients = json.loads(record.recipients) if record.recipients else []
    if not recipients:
        record.attempts += 1
        record.status = "failed"
        record.last_error = "no recipient"
        db.session.commit()
        return False

    api_key = current_app.config.get("BREVO_API_KEY") or os.environ.get("BREVO_API_KEY")
    sender_email = current_app.config.get("MAIL_DEFAULT_SENDER") or os.environ.get("MAIL_DEFAULT_SENDER")
    if not api_key:
        if current_app.config.get("ENVIRONMENT") == "production":
            record.attempts += 1
            record.last_error = "mail provider not configured"
            record.status = "failed" if record.attempts >= _max_attempts() else "pending"
            db.session.commit()
            return False
        # Development without a provider: log the preview once, stop retrying.
        logger.warning(
            "DEV ONLY: queued email for %s (mail provider not configured):\n%s",
            ", ".join(recipients),
            record.body_html,
        )
        record.attempts += 1
        record.status = "sent"
        record.last_error = None
        db.session.commit()
        return True

    delivered = _post_brevo(
        record.subject,
        recipients,
        record.body_html,
        _decode_attachments(record.attachments),
        api_key,
        sender_email,
    )
    record.attempts += 1
    if delivered:
        record.status = "sent"
        record.last_error = None
    else:
        record.last_error = "delivery failed"
        if record.attempts >= _max_attempts():
            record.status = "failed"
    db.session.commit()
    return delivered


def retry_pending_emails(limit=50):
    """Retry queued emails that have not reached the attempt ceiling."""
    records = db.session.scalars(
        select(OutboundEmail)
        .where(OutboundEmail.status == "pending", OutboundEmail.attempts < _max_attempts())
        .order_by(OutboundEmail.created_at.asc())
        .limit(limit)
    ).all()
    delivered = 0
    for record in records:
        if deliver_outbound_email(record):
            delivered += 1
    return delivered


def _enqueue(template, subject, recipients, locale=None, attachments=None, **context):
    recipients = [address for address in recipients if address]
    if not recipients:
        return None
    rendered_subject, html, encoded = _render_message(template, subject, locale, attachments, context)
    record = OutboundEmail(
        recipients=json.dumps(recipients),
        subject=rendered_subject[:255],
        body_html=html,
        attachments=encoded,
        status="pending",
        attempts=0,
    )
    db.session.add(record)
    db.session.commit()
    return record.id




def _deliver_in_background(record_id):
    # Tests deliver inline so the in-memory database stays on one connection.
    if not current_app.config.get("ASYNC_ORDER_EMAILS", True):
        record = db.session.get(OutboundEmail, record_id)
        if record is not None and record.status == "pending":
            deliver_outbound_email(record)
        return

    app = current_app._get_current_object()

    def deliver():
        with app.app_context():
            try:
                record = db.session.get(OutboundEmail, record_id)
                if record is not None and record.status == "pending":
                    deliver_outbound_email(record)
            finally:
                db.session.remove()

    Thread(target=deliver, name=f"outbound-email-{record_id}", daemon=True).start()


def _order_locale(order):
    user = getattr(order, "user", None)
    if user is not None and user.preferred_locale in SUPPORTED_LOCALES:
        return user.preferred_locale
    return None


def enqueue_order_emails(order):
    """Store the customer and Admin order emails and start background delivery."""
    locale = _order_locale(order)
    record_ids = [
        _enqueue(
            "order_pending",
            f"NexHaat order received: {order.order_number}",
            [order.email],
            locale,
            order=order,
            restaurant_name="NexHaat",
        )
    ]
    admin_email = (
        current_app.config.get("ADMIN_EMAIL") or current_app.config.get("MAIL_DEFAULT_SENDER")
    )
    if admin_email:
        record_ids.append(
            _enqueue(
                "admin_order",
                f"New order received: {order.order_number}",
                [admin_email],
                locale,
                order=order,
                restaurant_name="NexHaat",
            )
        )
    for record_id in record_ids:
        if record_id:
            _deliver_in_background(record_id)


def queue_order_receipt(order):
    locale = _order_locale(order)
    try:
        invoice = build_invoice_pdf(order, locale=locale)
        attachments = [(f"NexHaat-Invoice-{order.order_number}.pdf", invoice, "application/pdf")]
    except Exception:
        logger.exception("Invoice generation failed for order %s", order.order_number)
        attachments = None
    record_id = _enqueue(
        "order_receipt",
        f"Your NexHaat receipt and invoice: {order.order_number}",
        [order.email],
        locale,
        attachments=attachments,
        order=order,
        restaurant_name="NexHaat",
    )
    if record_id:
        _deliver_in_background(record_id)


def queue_order_status(order):
    record_id = _enqueue(
        "order_status",
        f"Order {order.order_number} is {order.status.title()}",
        [order.email],
        _order_locale(order),
        order=order,
        restaurant_name="NexHaat",
    )
    if record_id:
        _deliver_in_background(record_id)


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


def send_admin_login_code(recipient, code, locale=None):
    return _send(
        "admin_login_code",
        lazy_gettext("Your NexHaat admin sign-in code"),
        [recipient],
        code=code,
        restaurant_name="NexHaat",
        locale=locale,
    )


def queue_admin_login_code(recipient, code, locale=None):
    """Send an Admin sign-in code outside the request path."""
    app = current_app._get_current_object()

    def deliver():
        with app.app_context():
            try:
                send_admin_login_code(recipient, code, locale=locale)
            finally:
                db.session.remove()

    Thread(target=deliver, name="admin-login-email", daemon=True).start()


def queue_registration_code(recipient, code, locale=None):
    """Deliver a customer or seller registration verification code."""
    app = current_app._get_current_object()

    def deliver():
        with app.app_context():
            try:
                _send(
                    "registration_code",
                    lazy_gettext("Your NexHaat account verification code"),
                    [recipient],
                    code=code,
                    restaurant_name="NexHaat",
                    locale=locale,
                )
            finally:
                db.session.remove()

    Thread(target=deliver, name="registration-verification-email", daemon=True).start()


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
