"""Customer wishlist pages."""

from urllib.parse import urlsplit

from flask import Blueprint, abort, flash, redirect, render_template, request, session, url_for
from flask_babel import gettext

from ..extensions import db
from ..models import Product
from ..security import current_session_user
from ..services.wishlist import add, products_for, remove


wishlist_bp = Blueprint("wishlist", __name__)


def _safe_redirect(target, fallback_endpoint):
    """Redirect only to a local path; anything else falls back to a known route."""
    target = target or ""
    parsed = urlsplit(target)
    safe = bool(
        target.startswith("/")
        and not target.startswith("//")
        and not parsed.scheme
        and not parsed.netloc
        and "\\" not in target
    )
    return redirect(target if safe else url_for(fallback_endpoint))


@wishlist_bp.get("/wishlist")
def index():
    user = current_session_user("customer")
    if not user:
        if session.get("user_id") is not None:
            abort(403)
        return redirect(url_for("auth.login", next=url_for("wishlist.index")))
    saved = products_for(user)
    return render_template(
        "wishlist/index.html",
        user=user,
        products=saved,
        saved_ids=[item.id for item in saved],
    )


@wishlist_bp.post("/wishlist/add/<int:product_id>")
def add_item(product_id):
    user = current_session_user("customer")
    if not user:
        if session.get("user_id") is not None:
            abort(403)
        return redirect(url_for("auth.login", next=url_for("wishlist.index")))
    product = db.session.get(Product, product_id)
    if product is None:
        abort(404)
    _, created = add(user, product)
    flash(
        gettext("Saved to your wishlist.") if created else gettext("Already in your wishlist."),
        "success",
    )
    return _safe_redirect(request.form.get("next"), "wishlist.index")


@wishlist_bp.post("/wishlist/remove/<int:product_id>")
def remove_item(product_id):
    user = current_session_user("customer")
    if not user:
        if session.get("user_id") is not None:
            abort(403)
        return redirect(url_for("auth.login", next=url_for("wishlist.index")))
    remove(user, product_id)
    flash(gettext("Removed from your wishlist."), "success")
    return _safe_redirect(request.form.get("next"), "wishlist.index")