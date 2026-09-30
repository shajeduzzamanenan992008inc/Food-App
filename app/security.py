"""Small security helpers shared by authentication and upload routes."""

import hashlib
import hmac
from functools import wraps
from datetime import datetime, timedelta, timezone
from pathlib import Path

from flask import abort, current_app, g, session, url_for
from sqlalchemy import case, delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from werkzeug.datastructures import FileStorage

from .extensions import db
from .models import AuthThrottle, User


IMAGE_TYPES = {
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".png": "png",
    ".webp": "webp",
}

ROLE_DASHBOARD_ENDPOINTS = {
    "customer": "customer.dashboard",
    "seller": "seller.dashboard",
    "rider": "rider.dashboard",
    "admin": "admin.dashboard",
}


def role_dashboard_url(role_or_user):
    """Return the canonical dashboard URL for a role or User instance."""
    role = getattr(role_or_user, "role", role_or_user)
    endpoint = ROLE_DASHBOARD_ENDPOINTS.get(role)
    if endpoint is None:
        raise ValueError(f"No dashboard is configured for role {role!r}.")
    return url_for(endpoint)


def current_session_user(role=None):
    """Return the authenticated active user, rejecting revoked/old sessions."""
    user_id = session.get("user_id")
    user = db.session.get(User, user_id) if user_id else None
    if (
        not user
        or not user.is_active
        or user.auth_version != session.get("auth_version")
        or (role is not None and user.role != role)
    ):
        return None
    return user


def role_required(*roles):
    """Require an active authenticated user whose role is explicitly allowed."""
    allowed_roles = frozenset(roles)

    def decorate(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_session_user()
            if not user or user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorate


def admin_required(view):
    return role_required("admin")(view)


def customer_required(view):
    return role_required("customer")(view)


def customer_or_guest_required(view):
    """Allow guests and customers, but reject authenticated staff sessions."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("user_id") is not None and not current_session_user("customer"):
            abort(403)
        return view(*args, **kwargs)

    return wrapped


def current_approved_seller():
    user = current_session_user("seller")
    if not user or not user.seller_profile or user.seller_profile.approval_status != "approved":
        abort(403)
    return user


def approved_seller_required(view):
    """Require a seller account that has passed the Admin approval gate."""
    @wraps(view)
    def wrapped(*args, **kwargs):
        g.current_seller = current_approved_seller()
        return view(*args, **kwargs)

    return wrapped


def _login_throttle_key(remote_addr):
    secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(
        secret, (remote_addr or "unknown").encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def login_is_throttled(remote_addr):
    key = _login_throttle_key(remote_addr)
    throttle = db.session.get(AuthThrottle, key)
    if not throttle or not throttle.blocked_until:
        return False
    blocked_until = _utc(throttle.blocked_until)
    now = datetime.now(timezone.utc)
    if blocked_until > now:
        return True
    throttle.failures = 0
    throttle.blocked_until = None
    throttle.window_started_at = now
    db.session.commit()
    return False


def record_login_failure(remote_addr):
    key = _login_throttle_key(remote_addr)
    now = datetime.now(timezone.utc)
    reset_before = now - timedelta(minutes=15)
    blocked_until = now + timedelta(minutes=5)
    insert = postgres_insert if db.engine.dialect.name == "postgresql" else sqlite_insert
    statement = insert(AuthThrottle).values(
        key_hash=key, failures=1, window_started_at=now, blocked_until=None, last_attempt_at=now
    )
    expired_window = AuthThrottle.window_started_at < reset_before
    statement = statement.on_conflict_do_update(
        index_elements=[AuthThrottle.key_hash],
        set_={
            "failures": case((expired_window, 1), else_=AuthThrottle.failures + 1),
            "window_started_at": case((expired_window, now), else_=AuthThrottle.window_started_at),
            "blocked_until": case(
                (expired_window, None),
                (AuthThrottle.failures + 1 >= 10, blocked_until),
                else_=AuthThrottle.blocked_until,
            ),
            "last_attempt_at": now,
        },
    )
    db.session.execute(statement)
    db.session.execute(
        delete(AuthThrottle).where(AuthThrottle.last_attempt_at < now - timedelta(days=1))
    )
    db.session.commit()


def clear_login_failures(remote_addr):
    key = _login_throttle_key(remote_addr)
    db.session.execute(delete(AuthThrottle).where(AuthThrottle.key_hash == key))
    db.session.commit()


def save_raster_upload(upload: FileStorage, folder, stem):
    """Save a small JPEG, PNG, or WebP after checking its actual file signature."""
    if not upload or not upload.filename:
        return None, "Choose an image file first."

    extension = Path(upload.filename).suffix.lower()
    image_type = IMAGE_TYPES.get(extension)
    if image_type is None:
        return None, "Use a JPG, PNG, or WEBP image."

    limit = current_app.config["MAX_IMAGE_UPLOAD_BYTES"]
    contents = upload.stream.read(limit + 1)
    upload.stream.seek(0)
    if len(contents) > limit:
        return None, "Image files must be 2 MB or smaller."

    if image_type == "jpeg":
        valid_signature = contents.startswith(b"\xff\xd8\xff")
    elif image_type == "png":
        valid_signature = contents.startswith(b"\x89PNG\r\n\x1a\n")
    else:
        valid_signature = len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP"
    if not valid_signature:
        return None, "The uploaded file does not match its image type."

    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    filename = f"{stem}{extension}"
    (folder / filename).write_bytes(contents)
    return filename, None
