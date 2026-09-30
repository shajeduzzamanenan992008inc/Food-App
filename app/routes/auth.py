import re
import hashlib
import hmac
import secrets
import time
from datetime import datetime, timedelta, timezone

from urllib.parse import urlsplit

from flask import Blueprint, abort, current_app, flash, make_response, redirect, render_template, request, session, url_for
from flask_babel import get_locale, gettext
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash
from ..extensions import db
from ..i18n import SUPPORTED_LOCALES
from ..models import (
    AccountInvitation, AdminProfile, CustomerAddress, CustomerProfile,
    RiderProfile, SellerProfile, User,
)
from ..security import (
    admin_required as admin_account_required,
    clear_login_failures,
    customer_required,
    current_session_user,
    login_is_throttled,
    role_dashboard_url,
    role_required,
    record_login_failure,
    save_raster_upload,
)
from ..services.mail import queue_account_invitation, queue_password_reset_code


auth_bp = Blueprint("auth", __name__)
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
DUMMY_LOGIN_HASH = generate_password_hash(secrets.token_urlsafe(32))


def _capture_request_locale():
    locale = request.form.get("locale")
    if locale in SUPPORTED_LOCALES:
        session["locale"] = locale


def _start_authenticated_session(user, permanent=True):
    locale = user.preferred_locale if user.preferred_locale in SUPPORTED_LOCALES else session.get("locale")
    session.clear()
    if locale in SUPPORTED_LOCALES:
        session["locale"] = locale
    session.permanent = permanent
    session["user_id"] = user.id
    session["role"] = user.role
    session["auth_version"] = user.auth_version


def _role_destination(user):
    return role_dashboard_url(user)


def _invitation_base_url(token):
    base_url = (current_app.config.get("PUBLIC_BASE_URL") or "").strip().rstrip("/")
    if base_url:
        parsed = urlsplit(base_url)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
            or any(ord(character) < 32 for character in base_url)
            or (
                current_app.config.get("ENVIRONMENT") == "production"
                and parsed.scheme != "https"
            )
        ):
            raise RuntimeError("PUBLIC_BASE_URL must be a valid HTTPS site URL in production.")
        return f"{base_url}{url_for('auth.accept_invitation', token=token)}"
    if current_app.config.get("ENVIRONMENT") == "production":
        raise RuntimeError("PUBLIC_BASE_URL must be configured before sending staff invitations.")
    return url_for("auth.accept_invitation", token=token, _external=True)


def _staff_email_ready():
    return bool(
        current_app.config.get("BREVO_API_KEY")
        and current_app.config.get("MAIL_DEFAULT_SENDER")
    )


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        _capture_request_locale()
        email = request.form.get("email", "").strip().lower()
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        password_confirmation = request.form.get("password_confirmation", "")

        if (
            not EMAIL_PATTERN.match(email)
            or len(email) > 255
            or not 2 <= len(full_name) <= 120
            or not 7 <= len(phone) <= 30
        ):
            flash(gettext("Please provide valid name, email, and phone details."), "error")
        elif _password_length_error(password):
            flash(_password_length_error(password), "error")
        elif password != password_confirmation:
            flash(gettext("Passwords do not match."), "error")
        elif db.session.scalar(select(User).where(User.email == email)):
            flash(gettext("An account with this email already exists."), "error")
        else:
            user = User(
                email=email,
                role="customer",
                preferred_locale=session.get("locale") if session.get("locale") in SUPPORTED_LOCALES else None,
            )
            user.set_password(password)
            user.customer_profile = CustomerProfile(full_name=full_name, phone=phone)
            db.session.add(user)
            db.session.commit()
            flash(gettext("Account created. You can now sign in."), "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/register.html")


@auth_bp.route("/seller-application", methods=["GET", "POST"])
def seller_application():
    if request.method == "POST":
        _capture_request_locale()
        email = request.form.get("email", "").strip().lower()
        store_name = request.form.get("store_name", "").strip()
        contact_name = request.form.get("contact_name", "").strip()
        phone = request.form.get("phone", "").strip()
        business_address = request.form.get("business_address", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if (
            not EMAIL_PATTERN.fullmatch(email) or len(email) > 255
            or not 2 <= len(store_name) <= 120
            or not 2 <= len(contact_name) <= 120
            or not 7 <= len(phone) <= 30
            or (business_address and len(business_address) > 500)
        ):
            flash(gettext("Please provide valid store, contact, email, and phone details."), "error")
        elif _password_length_error(password):
            flash(_password_length_error(password), "error")
        elif password != confirmation:
            flash(gettext("Passwords do not match."), "error")
        elif db.session.scalar(select(User).where(User.email == email)):
            flash(gettext("An account with this email already exists."), "error")
        else:
            user = User(
                email=email,
                role="seller",
                preferred_locale=session.get("locale") if session.get("locale") in SUPPORTED_LOCALES else None,
            )
            user.set_password(password)
            user.seller_profile = SellerProfile(
                store_name=store_name,
                contact_name=contact_name,
                phone=phone,
                business_address=business_address or None,
                approval_status="pending",
            )
            db.session.add(user)
            db.session.commit()
            flash(gettext("Your seller application is submitted. Sign in to check its review status."), "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/seller_application.html")


def _reset_code_digest(code):
    secret = current_app.secret_key
    if isinstance(secret, str):
        secret = secret.encode("utf-8")
    return hmac.new(secret, code.encode("utf-8"), hashlib.sha256).hexdigest()


def _as_utc(value):
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _password_length_error(password):
    minimum = current_app.config["MIN_PASSWORD_LENGTH"]
    maximum = current_app.config["MAX_PASSWORD_LENGTH"]
    if len(password) < minimum:
        return gettext("Password must contain at least %(minimum)s characters.", minimum=minimum)
    if len(password) > maximum:
        return gettext("Password must contain no more than %(maximum)s characters.", maximum=maximum)
    return None


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        _capture_request_locale()
        email = request.form.get("email", "").strip().lower()
        remote_addr = request.remote_addr
        throttled = login_is_throttled(remote_addr)
        user = None if throttled else db.session.scalar(select(User).where(User.email == email))
        password = request.form.get("password", "")
        password_within_limit = len(password) <= current_app.config["MAX_PASSWORD_LENGTH"]
        password_valid = (
            user.check_password(password[:current_app.config["MAX_PASSWORD_LENGTH"]])
            if user and not throttled
            else check_password_hash(
                DUMMY_LOGIN_HASH, password[:current_app.config["MAX_PASSWORD_LENGTH"]]
            ) if not throttled else False
        )
        valid_login = bool(not throttled and password_within_limit and user and user.is_active and password_valid)
        if not valid_login:
            if not throttled:
                record_login_failure(remote_addr)
            flash(gettext("Invalid email or password."), "error")
        else:
            clear_login_failures(remote_addr)
            _start_authenticated_session(user, permanent=request.form.get("remember") == "on")
            return redirect(_role_destination(user))
    return render_template("auth/login.html")


@auth_bp.get("/portal")
@role_required("customer", "seller", "rider", "admin")
def portal():
    user = current_session_user()
    if user.role == "admin":
        return redirect(url_for("admin.dashboard"))
    if user.role == "customer":
        return render_template("portals/dashboard.html", role=user.role, user=user, profile=user.customer_profile)
    if user.role == "seller":
        if user.seller_profile is None:
            abort(403)
        return render_template(
            "portals/dashboard.html", role=user.role, user=user, profile=user.seller_profile
        )
    if user.rider_profile is None:
        abort(403)
    return render_template("portals/dashboard.html", role=user.role, user=user, profile=user.rider_profile)


def _active_invitation(token):
    if not token or len(token) > 128:
        return None
    digest = _reset_code_digest(token)
    invitation = db.session.scalar(
        select(AccountInvitation)
        .where(AccountInvitation.token_digest == digest)
        .with_for_update()
    )
    if (
        not invitation or invitation.accepted_at
        or _as_utc(invitation.expires_at) <= datetime.now(timezone.utc)
    ):
        return None
    return invitation


@auth_bp.route("/invitation/<token>", methods=["GET", "POST"])
def accept_invitation(token):
    invitation = _active_invitation(token)
    if invitation is None:
        flash(gettext("This invitation is invalid, expired, or already used."), "error")
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        _capture_request_locale()
        name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if not EMAIL_PATTERN.fullmatch(invitation.email) or not 2 <= len(name) <= 120:
            flash(gettext("Please provide a valid name for this account."), "error")
        elif invitation.role == "rider" and not 7 <= len(phone) <= 30:
            flash(gettext("Please provide a valid phone number."), "error")
        elif _password_length_error(password):
            flash(_password_length_error(password), "error")
        elif password != confirmation:
            flash(gettext("Passwords do not match."), "error")
        elif db.session.scalar(select(User.id).where(User.email == invitation.email)):
            db.session.rollback()
            flash(gettext("An account with this email already exists. Ask an administrator to resend the invitation."), "error")
            return redirect(url_for("auth.login"))
        else:
            user = User(
                email=invitation.email,
                role=invitation.role,
                preferred_locale=(
                    invitation.locale
                    if invitation.locale in SUPPORTED_LOCALES
                    else session.get("locale") if session.get("locale") in SUPPORTED_LOCALES else None
                ),
            )
            user.set_password(password)
            if invitation.role == "rider":
                user.rider_profile = RiderProfile(full_name=name, phone=phone)
            else:
                user.admin_profile = AdminProfile(full_name=name)
            db.session.add(user)
            invitation.accepted_at = datetime.now(timezone.utc)
            db.session.commit()
            flash(gettext("Your account is ready. Sign in to continue."), "success")
            return redirect(url_for("auth.login"))
    response = make_response(render_template("auth/accept_invitation.html", invitation=invitation))
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@auth_bp.post("/admin/invitations")
@admin_account_required
def create_staff_invitation():
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "").strip().lower()
    locale = request.form.get("locale", "").strip()
    if (
        not EMAIL_PATTERN.fullmatch(email) or len(email) > 255
        or role not in {"rider", "admin"}
    ):
        flash(gettext("Enter a valid email and choose Rider or Admin."), "error")
        return redirect(url_for("admin.dashboard"))
    if db.session.scalar(select(User.id).where(User.email == email)):
        flash(gettext("An account with this email already exists."), "error")
        return redirect(url_for("admin.dashboard"))
    if not _staff_email_ready():
        flash(gettext("Staff invitations need a configured email provider and sender address."), "error")
        return redirect(url_for("admin.dashboard"))
    now = datetime.now(timezone.utc)
    existing = db.session.scalar(
        select(AccountInvitation).where(
            AccountInvitation.email == email,
            AccountInvitation.role == role,
            AccountInvitation.accepted_at.is_(None),
            AccountInvitation.expires_at > now,
        )
    )
    if existing:
        flash(gettext("A valid invitation already exists for this email and role."), "error")
        return redirect(url_for("admin.dashboard"))

    token = secrets.token_urlsafe(32)
    invitation = AccountInvitation(
        email=email,
        role=role,
        token_digest=_reset_code_digest(token),
        invited_by_id=session["user_id"],
        expires_at=now + timedelta(hours=24),
        locale=locale if locale in SUPPORTED_LOCALES else current_app.config.get("BABEL_DEFAULT_LOCALE"),
    )
    try:
        invitation_url = _invitation_base_url(token)
    except RuntimeError:
        flash(gettext("Staff invitations are unavailable until the public site URL is configured."), "error")
        return redirect(url_for("admin.dashboard"))
    db.session.add(invitation)
    db.session.commit()
    queue_account_invitation(email, invitation_url, role, locale=invitation.locale)
    flash(gettext("The account invitation was created and queued for email."), "success")
    return redirect(url_for("admin.dashboard"))


@auth_bp.post("/admin/invitations/<int:invitation_id>/resend")
@admin_account_required
def resend_staff_invitation(invitation_id):
    invitation = db.session.get(AccountInvitation, invitation_id)
    now = datetime.now(timezone.utc)
    if not invitation or invitation.accepted_at:
        abort(404)
    if not _staff_email_ready():
        flash(gettext("Staff invitations need a configured email provider and sender address."), "error")
        return redirect(url_for("admin.dashboard"))
    if db.session.scalar(select(User.id).where(User.email == invitation.email)):
        invitation.expires_at = now
        db.session.commit()
        flash(gettext("This invitation was closed because an account already exists."), "error")
        return redirect(url_for("admin.dashboard"))
    token = secrets.token_urlsafe(32)
    invitation.token_digest = _reset_code_digest(token)
    invitation.expires_at = now + timedelta(hours=24)
    try:
        invitation_url = _invitation_base_url(token)
    except RuntimeError:
        flash(gettext("Staff invitations are unavailable until the public site URL is configured."), "error")
        return redirect(url_for("admin.dashboard"))
    db.session.commit()
    queue_account_invitation(
        invitation.email, invitation_url, invitation.role, locale=invitation.locale
    )
    flash(gettext("A fresh invitation link was queued for email."), "success")
    return redirect(url_for("admin.dashboard"))


@auth_bp.post("/admin/invitations/<int:invitation_id>/revoke")
@admin_account_required
def revoke_staff_invitation(invitation_id):
    invitation = db.session.get(AccountInvitation, invitation_id)
    if not invitation or invitation.accepted_at:
        abort(404)
    invitation.expires_at = datetime.now(timezone.utc)
    db.session.commit()
    flash(gettext("The account invitation was revoked."), "success")
    return redirect(url_for("admin.dashboard"))


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        _capture_request_locale()
        email = request.form.get("email", "").strip().lower()
        user = db.session.scalar(select(User).where(User.email == email))
        reset_user_id = None
        expires_at = time.time() + 600
        if user and user.is_active and EMAIL_PATTERN.match(email):
            now = datetime.now(timezone.utc)
            sent_at = _as_utc(user.password_reset_sent_at)
            previous_expiry = _as_utc(user.password_reset_expires_at)
            token_still_valid = bool(user.password_reset_hash and previous_expiry and previous_expiry > now)
            cooldown_elapsed = sent_at is None or (now - sent_at).total_seconds() >= 60
            if cooldown_elapsed or not token_still_valid:
                code = f"{secrets.randbelow(1000000):06d}"
                user.password_reset_hash = _reset_code_digest(code)
                user.password_reset_expires_at = now + timedelta(minutes=10)
                user.password_reset_sent_at = now
                user.password_reset_attempts = 0
                db.session.commit()
                reset_locale = (
                    user.preferred_locale
                    if user.preferred_locale in SUPPORTED_LOCALES
                    else str(get_locale())
                )
                queue_password_reset_code(user.email, code, locale=reset_locale)
            reset_user_id = user.id
            expiry = _as_utc(user.password_reset_expires_at)
            if expiry:
                expires_at = expiry.timestamp()
        # A dummy state gives unknown and inactive emails the same redirect and
        # verification screen without ever creating a usable reset token.
        session["password_reset"] = {
            "user_id": reset_user_id,
            "expires_at": expires_at,
            "verified": False,
        }
        flash(gettext("If an active account exists for that email, a verification code has been sent."), "success")
        return redirect(url_for("auth.verify_reset_code"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/verify-reset-code", methods=["GET", "POST"])
def verify_reset_code():
    reset = session.get("password_reset")
    if not reset or reset.get("expires_at", 0) < time.time():
        session.pop("password_reset", None)
        flash(gettext("This password reset code is invalid or has expired."), "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        _capture_request_locale()
        code = request.form.get("code", "").strip()
        user = db.session.get(User, reset.get("user_id")) if reset.get("user_id") else None
        expires = _as_utc(user.password_reset_expires_at) if user else None
        valid_token = bool(
            user and user.is_active
            and user.password_reset_hash and expires and expires >= datetime.now(timezone.utc)
        )
        digest = _reset_code_digest(code)
        if not valid_token or not hmac.compare_digest(digest, user.password_reset_hash):
            if valid_token:
                user.password_reset_attempts += 1
                if user.password_reset_attempts >= 5:
                    user.password_reset_hash = None
                    user.password_reset_expires_at = None
                    db.session.commit()
                    session.pop("password_reset", None)
                    flash(gettext("Too many incorrect codes. Request a new verification code."), "error")
                    return redirect(url_for("auth.forgot_password"))
                db.session.commit()
            flash(gettext("The verification code is incorrect."), "error")
        else:
            reset["verified"] = True
            session["password_reset"] = reset
            return redirect(url_for("auth.reset_password"))
    return render_template("auth/verify_reset_code.html")


@auth_bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    reset = session.get("password_reset")
    user = db.session.get(User, reset.get("user_id")) if reset and reset.get("user_id") else None
    expires = _as_utc(user.password_reset_expires_at) if user else None
    if (
        not reset or not reset.get("verified") or reset.get("expires_at", 0) < time.time()
        or not user or not user.password_reset_hash or not expires
        or expires < datetime.now(timezone.utc)
    ):
        session.pop("password_reset", None)
        flash(gettext("Please verify a valid password reset code first."), "error")
        return redirect(url_for("auth.forgot_password"))
    if not user or not user.is_active:
        session.pop("password_reset", None)
        flash(gettext("This password reset request is invalid or has expired."), "error")
        return redirect(url_for("auth.forgot_password"))
    if request.method == "POST":
        _capture_request_locale()
        password = request.form.get("password", "")
        confirmation = request.form.get("password_confirmation", "")
        if _password_length_error(password):
            flash(_password_length_error(password), "error")
        elif password != confirmation:
            flash(gettext("Passwords do not match."), "error")
        else:
            user.set_password(password)
            user.auth_version += 1
            user.password_reset_hash = None
            user.password_reset_expires_at = None
            user.password_reset_attempts = 0
            db.session.commit()
            session.pop("password_reset", None)
            flash(gettext("Password updated. You can now sign in."), "success")
            return redirect(url_for("auth.login"))
    return render_template("auth/reset_password.html")


@auth_bp.route("/account", methods=["GET", "POST"])
@customer_required
def account():
    user = db.session.get(User, session["user_id"])
    profile = user.customer_profile
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        phone = request.form.get("phone", "").strip()
        address_line = request.form.get("address_line", "").strip()
        city = request.form.get("city", "").strip()
        if not 2 <= len(full_name) <= 120 or not 7 <= len(phone) <= 30:
            flash(gettext("Please provide a valid name and phone number."), "error")
        elif address_line and not 8 <= len(address_line) <= 1000:
            flash(gettext("Please provide a complete address."), "error")
        elif city and not 2 <= len(city) <= 100:
            flash(gettext("Please provide a valid city."), "error")
        else:
            profile.full_name = full_name
            profile.phone = phone
            image = request.files.get("profile_image")
            if image and image.filename:
                filename, upload_error = save_raster_upload(
                    image, current_app.config["UPLOAD_FOLDER"], f"customer-{user.id}"
                )
                if upload_error:
                    flash(upload_error, "error")
                    return render_template("auth/account.html", user=user, profile=profile, address=profile.address)
                profile.profile_image = filename
            if address_line and city:
                if profile.address:
                    profile.address.address_line = address_line
                    profile.address.city = city
                else:
                    profile.address = CustomerAddress(address_line=address_line, city=city)
            elif profile.address:
                db.session.delete(profile.address)
            db.session.commit()
            flash(gettext("Your account details were updated."), "success")
            return redirect(url_for("auth.account"))
    return render_template("auth/account.html", user=user, profile=profile, address=profile.address)


@auth_bp.post("/account/password")
@customer_required
def change_password():
    user = db.session.get(User, session["user_id"])
    current_password = request.form.get("current_password", "")
    password = request.form.get("password", "")
    confirmation = request.form.get("password_confirmation", "")
    if not user.check_password(current_password):
        flash(gettext("Your current password is incorrect."), "error")
    elif _password_length_error(password):
        flash(_password_length_error(password), "error")
    elif password != confirmation:
        flash(gettext("Passwords do not match."), "error")
    else:
        user.set_password(password)
        user.auth_version += 1
        db.session.commit()
        session.clear()
        flash(gettext("Your password was changed. Sign in again on this device."), "success")
        return redirect(url_for("auth.login"))
    return redirect(url_for("auth.account"))


@auth_bp.route("/admin-account", methods=["GET", "POST"])
@admin_account_required
def admin_account():
    user = db.session.get(User, session["user_id"])
    profile = user.admin_profile
    if profile is None:
        profile = AdminProfile(full_name="NexHaat Admin")
        user.admin_profile = profile
        db.session.flush()
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        image = request.files.get("profile_image")
        if not 2 <= len(full_name) <= 120:
            flash(gettext("Please provide a valid admin name."), "error")
        else:
            filename = None
            if image and image.filename:
                filename, upload_error = save_raster_upload(
                    image, current_app.config["UPLOAD_FOLDER"], f"admin-{user.id}"
                )
                if upload_error:
                    flash(upload_error, "error")
                    return render_template("auth/admin_account.html", user=user, profile=profile), 400
            profile.full_name = full_name
            if filename:
                profile.profile_image = filename
            db.session.commit()
            flash(gettext("Admin profile updated."), "success")
            return redirect(url_for("auth.admin_account"))
    return render_template("auth/admin_account.html", user=user, profile=profile)


@auth_bp.post("/admin-account/password")
@admin_account_required
def admin_change_password():
    user = db.session.get(User, session["user_id"])
    current_password = request.form.get("current_password", "")
    password = request.form.get("password", "")
    confirmation = request.form.get("password_confirmation", "")
    if not user.check_password(current_password):
        flash(gettext("Your current password is incorrect."), "error")
    elif _password_length_error(password):
        flash(_password_length_error(password), "error")
    elif password != confirmation:
        flash(gettext("Passwords do not match."), "error")
    else:
        user.set_password(password)
        user.auth_version += 1
        db.session.commit()
        session.clear()
        flash(gettext("Admin password changed. Sign in again on this device."), "success")
        return redirect(url_for("auth.admin_login"))
    return redirect(url_for("auth.admin_account"))


def admin_login():
    """Compatibility entry point that sends every role to the shared login."""
    return redirect(url_for("auth.login"))


@auth_bp.post("/logout")
def logout():
    locale = session.get("locale")
    session.clear()
    if locale in SUPPORTED_LOCALES:
        session["locale"] = locale
    flash(gettext("You have been signed out."), "success")
    return redirect(url_for("main.index"))
