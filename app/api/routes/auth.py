"""Session-authenticated REST endpoints for account access."""

import hmac
import re
import secrets
from datetime import datetime, timezone

from flask import Blueprint, current_app, request, session
from flask_wtf.csrf import generate_csrf
from flask_login import logout_user
from sqlalchemy import select
from werkzeug.security import check_password_hash

from ...extensions import db
from ...models import AdminLoginChallenge, CustomerProfile, RegistrationChallenge, SellerProfile, User
from ...security import (
    clear_login_failures,
    current_session_user,
    login_is_throttled,
    record_login_failure,
)
from ...i18n import SUPPORTED_LOCALES
from ...services.audit import record_audit
from ..errors import ApiError
from ..responses import created_response, success_response
from ..serializers import user_to_dict


auth_api = Blueprint("api_auth", __name__, url_prefix="/auth")


@auth_api.get("/csrf")
def csrf_token():
    """Return a CSRF token for state-changing API requests.

    API clients authenticate with the session cookie and echo this token back in
    the ``X-CSRFToken`` header on POST/PATCH/DELETE requests.
    """
    return success_response({"csrf_token": generate_csrf()})


@auth_api.post("/register")
def register():
    from ...routes.auth import (
        EMAIL_PATTERN,
        _create_registration_challenge,
        _password_length_error,
        _staff_email_ready,
    )

    payload = request.get_json(silent=True) or {}
    role = str(payload.get("role", "customer")).strip().lower()
    email = str(payload.get("email", "")).strip().lower()
    full_name = str(payload.get("full_name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    password = payload.get("password", "")
    if role not in {"customer", "seller"}:
        raise ApiError("Choose customer or seller registration.", "VALIDATION_ERROR", 422)
    if not EMAIL_PATTERN.fullmatch(email) or len(email) > 255:
        raise ApiError("Enter a valid email address.", "VALIDATION_ERROR", 422)
    if not 2 <= len(full_name) <= 120 or not 7 <= len(phone) <= 30:
        raise ApiError("Enter a valid name and phone number.", "VALIDATION_ERROR", 422)
    password_error = _password_length_error(password)
    if password_error:
        raise ApiError(str(password_error), "VALIDATION_ERROR", 422)
    if db.session.scalar(select(User.id).where(User.email == email)):
        raise ApiError("An account with this email already exists.", "CONFLICT", 409)
    if not _staff_email_ready():
        raise ApiError("Email verification is unavailable.", "EMAIL_UNAVAILABLE", 503)

    if role == "customer":
        profile_data = {"full_name": full_name, "phone": phone}
    else:
        store_name = str(payload.get("store_name", "")).strip()
        business_address = str(payload.get("business_address", "")).strip()
        if not 2 <= len(store_name) <= 120 or len(business_address) > 500:
            raise ApiError("Enter valid seller store details.", "VALIDATION_ERROR", 422)
        profile_data = {
            "store_name": store_name,
            "contact_name": full_name,
            "phone": phone,
            "business_address": business_address or None,
        }
    challenge = _create_registration_challenge(
        email=email, role=role, password=password, profile_data=profile_data
    )
    return success_response(
        {"email": challenge.email, "expires_at": challenge.expires_at.isoformat()},
        message="Verification code sent.",
        status=202,
    )


@auth_api.post("/register/verify")
def verify_registration():
    from ...i18n import SUPPORTED_LOCALES
    from ...routes.auth import (
        REGISTRATION_CODE_MAX_ATTEMPTS,
        _as_utc,
        _reset_code_digest,
    )

    challenge_id = session.get("registration_challenge_id")
    challenge = db.session.get(RegistrationChallenge, challenge_id) if challenge_id else None
    now = datetime.now(timezone.utc)
    expires = _as_utc(challenge.expires_at) if challenge else None
    if not challenge or challenge.consumed_at or not expires or expires < now:
        if challenge:
            db.session.delete(challenge)
            db.session.commit()
        session.pop("registration_challenge_id", None)
        raise ApiError("Registration code is invalid or expired.", "CODE_EXPIRED", 400)

    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip()
    if not re.fullmatch(r"[0-9]{6}", code) or not hmac.compare_digest(
        _reset_code_digest(code), challenge.code_hash
    ):
        challenge.failed_attempts += 1
        locked = challenge.failed_attempts >= REGISTRATION_CODE_MAX_ATTEMPTS
        if locked:
            db.session.delete(challenge)
            session.pop("registration_challenge_id", None)
        db.session.commit()
        raise ApiError(
            "Too many incorrect codes." if locked else "The verification code is incorrect.",
            "CODE_LOCKED" if locked else "INVALID_CODE",
            429 if locked else 400,
        )

    if db.session.scalar(select(User.id).where(User.email == challenge.email)):
        db.session.delete(challenge)
        db.session.commit()
        session.pop("registration_challenge_id", None)
        raise ApiError("An account with this email already exists.", "CONFLICT", 409)

    user = User(
        email=challenge.email,
        role=challenge.role,
        password_hash=challenge.password_hash,
        preferred_locale=(
            challenge.locale if challenge.locale in SUPPORTED_LOCALES else None
        ),
    )
    if challenge.role == "customer":
        user.customer_profile = CustomerProfile(**challenge.profile_data)
    else:
        user.seller_profile = SellerProfile(
            **challenge.profile_data,
            approval_status="pending",
        )
    db.session.delete(challenge)
    db.session.add(user)
    db.session.commit()
    session.pop("registration_challenge_id", None)
    record_audit("auth.register", actor=user)
    return created_response(user_to_dict(user), "Account verified and created.")


@auth_api.post("/login")
def login():
    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    password = payload.get("password", "")
    if not isinstance(password, str) or len(password) > current_app.config["MAX_PASSWORD_LENGTH"]:
        password = ""
    remote_addr = request.remote_addr
    if login_is_throttled(remote_addr):
        raise ApiError("Too many attempts. Try again later.", "RATE_LIMITED", 429)
    user = db.session.scalar(select(User).where(User.email == email)) if email else None
    valid = bool(
        user and user.is_active and user.role in {"customer", "seller", "rider"}
        and user.check_password(password)
    )
    if not valid:
        record_login_failure(remote_addr)
        raise ApiError("Invalid email or password.", "INVALID_CREDENTIALS", 401)
    clear_login_failures(remote_addr)
    from ...routes.auth import _start_authenticated_session
    _start_authenticated_session(user)
    record_audit("auth.login", actor=user)
    return success_response(user_to_dict(user), "Signed in.")


@auth_api.post("/logout")
def logout():
    user = current_session_user()
    if user:
        record_audit("auth.logout", actor=user)
    logout_user()
    session.clear()
    return success_response(message="Signed out.")


@auth_api.get("/me")
def me():
    user = current_session_user()
    if not user:
        raise ApiError("Sign in is required.", "UNAUTHENTICATED", 401)
    return success_response(user_to_dict(user))


@auth_api.post("/admin/code")
def request_admin_code():
    from ...routes.auth import (
        ADMIN_LOGIN_CODE_RESEND_SECONDS,
        ADMIN_LOGIN_CODE_TTL,
        _as_utc,
        _queue_admin_code,
        _reset_code_digest,
        _staff_email_ready,
    )

    payload = request.get_json(silent=True) or {}
    email = str(payload.get("email", "")).strip().lower()
    remote_addr = request.remote_addr
    if login_is_throttled(remote_addr):
        raise ApiError("Too many attempts. Try again later.", "RATE_LIMITED", 429)
    user = db.session.scalar(select(User).where(User.email == email)) if email else None
    now = datetime.now(timezone.utc)
    if user and user.role == "admin" and user.is_active and _staff_email_ready():
        latest = db.session.scalar(
            select(AdminLoginChallenge)
            .where(AdminLoginChallenge.user_id == user.id)
            .order_by(AdminLoginChallenge.sent_at.desc())
            .limit(1)
        )
        last_sent = _as_utc(latest.sent_at) if latest else None
        if last_sent is None or (now - last_sent).total_seconds() >= ADMIN_LOGIN_CODE_RESEND_SECONDS:
            for previous in db.session.scalars(
                select(AdminLoginChallenge).where(
                    AdminLoginChallenge.user_id == user.id,
                    AdminLoginChallenge.consumed_at.is_(None),
                )
            ):
                previous.consumed_at = now
            code = f"{secrets.randbelow(1_000_000):06d}"
            challenge = AdminLoginChallenge(
                id=secrets.token_urlsafe(32),
                user_id=user.id,
                code_hash=_reset_code_digest(code),
                sent_at=now,
                expires_at=now + ADMIN_LOGIN_CODE_TTL,
                failed_attempts=0,
            )
            db.session.add(challenge)
            db.session.commit()
            session["admin_login_challenge_id"] = challenge.id
            _queue_admin_code(user, code)
        elif latest:
            session["admin_login_challenge_id"] = latest.id
    elif user and user.role != "admin":
        record_login_failure(remote_addr)
        record_audit("auth.admin_login_denied", target_id=email, detail="not an admin account")
        raise ApiError("That email is not an Admin account.", "NOT_ADMIN", 403)
    else:
        record_login_failure(remote_addr)
    return success_response(
        {"code_requested": True},
        message="If an active Admin account matches that email, a sign-in code will be sent.",
        status=202,
    )


@auth_api.post("/admin/verify")
def verify_admin_code():
    from ...routes.auth import (
        ADMIN_LOGIN_CODE_MAX_ATTEMPTS,
        _as_utc,
        _reset_code_digest,
        _start_authenticated_session,
    )

    remote_addr = request.remote_addr
    if login_is_throttled(remote_addr):
        raise ApiError("Too many attempts. Request a new sign-in code.", "RATE_LIMITED", 429)
    challenge_id = session.get("admin_login_challenge_id")
    challenge = db.session.get(AdminLoginChallenge, challenge_id) if challenge_id else None
    user = db.session.get(User, challenge.user_id) if challenge else None
    now = datetime.now(timezone.utc)
    expires = _as_utc(challenge.expires_at) if challenge else None
    valid_challenge = bool(
        challenge and challenge.consumed_at is None and expires and expires >= now
        and user and user.role == "admin" and user.is_active
    )
    payload = request.get_json(silent=True) or {}
    code = str(payload.get("code", "")).strip()
    valid_code = bool(
        valid_challenge and re.fullmatch(r"[0-9]{6}", code)
        and hmac.compare_digest(_reset_code_digest(code), challenge.code_hash)
    )
    if not valid_code:
        if challenge and challenge.consumed_at is None:
            if valid_challenge:
                challenge.failed_attempts += 1
                locked = challenge.failed_attempts >= ADMIN_LOGIN_CODE_MAX_ATTEMPTS
            else:
                locked = True
            if locked:
                db.session.delete(challenge)
                session.pop("admin_login_challenge_id", None)
            db.session.commit()
        record_login_failure(remote_addr)
        raise ApiError(
            "The code is incorrect or expired.", "INVALID_CODE", 400
        )

    challenge.consumed_at = now
    db.session.commit()
    clear_login_failures(remote_addr)
    session.pop("admin_login_challenge_id", None)
    _start_authenticated_session(user, permanent=True)
    record_audit("auth.admin_login", actor=user)
    return success_response(user_to_dict(user), "Admin signed in.")
