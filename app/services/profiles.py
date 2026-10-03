from pathlib import Path

from flask import current_app, url_for
from flask_babel import gettext
from sqlalchemy import select

from ..extensions import db
from ..models import CustomerProfile, Order


def password_change_error(user, current_password, password, confirmation):
    """Validate a self-service password change; return an error message or None.

    Shared by the customer, seller, and rider account pages so the rules and
    wording stay identical everywhere.
    """
    if not user.check_password(current_password):
        return gettext("Your current password is incorrect.")
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    maximum = current_app.config["MAX_PASSWORD_LENGTH"]
    if len(password) < minimum:
        return gettext("Password must contain at least %(minimum)s characters.", minimum=minimum)
    if len(password) > maximum:
        return gettext("Password must contain no more than %(maximum)s characters.", maximum=maximum)
    if password != confirmation:
        return gettext("Passwords do not match.")
    return None


def apply_password_change(user, password):
    """Store a new password, revoke other sessions, and clear the current session."""
    user.set_password(password)
    user.auth_version += 1
    db.session.commit()


def ensure_customer_profile(user):
    """Repair legacy customer accounts that predate their profile row."""
    if user.customer_profile is not None:
        return user.customer_profile

    recent_order = db.session.scalar(
        select(Order)
        .where(Order.user_id == user.id)
        .order_by(Order.created_at.desc(), Order.id.desc())
        .limit(1)
    )
    profile = CustomerProfile(
        full_name=recent_order.customer_name if recent_order else "",
        phone=recent_order.phone if recent_order else "",
    )
    user.customer_profile = profile
    db.session.commit()
    return profile


def customer_profile_image_url(profile):
    """Return a URL only for an existing profile image inside the static root."""
    filename = (profile.profile_image or "").strip()
    if not filename or Path(filename).name != filename:
        return None

    static_root = Path(current_app.static_folder).resolve()
    upload_root = Path(current_app.config["UPLOAD_FOLDER"]).resolve()
    source_path = upload_root / filename
    if source_path.is_symlink():
        return None
    image_path = source_path.resolve()
    try:
        relative_path = image_path.relative_to(static_root)
    except ValueError:
        return None
    if not image_path.is_file():
        return None
    return url_for(
        "static",
        filename=relative_path.as_posix(),
        v=image_path.stat().st_mtime_ns,
    )
