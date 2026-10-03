from app.extensions import db
from io import BytesIO
import struct
import tempfile
import zlib
from pathlib import Path

from app.models import (
    AccountInvitation, AdminLoginChallenge, AdminProfile, Category, CustomerAddress, CustomerProfile,
    Product,
    RiderProfile, SellerProfile, User,
)
from unittest.mock import patch


def tiny_png():
    def chunk(kind, payload):
        checksum = zlib.crc32(kind + payload) & 0xFFFFFFFF
        return struct.pack(">I", len(payload)) + kind + payload + struct.pack(">I", checksum)

    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\xff\xff\xff"))
        + chunk(b"IEND", b"")
    )


def test_registration_verification_page_uses_otp_card_pattern(client, app):
    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    with patch("app.routes.auth.secrets.randbelow", return_value=123456), patch(
        "app.routes.auth.queue_registration_code"
    ):
        client.post(
            "/auth/register",
            data={
                "full_name": "Test Customer",
                "phone": "01234567890",
                "email": "otp-form@example.com",
                "password": "password123",
                "password_confirmation": "password123",
                "locale": "bn_BD",
            },
        )

    response = client.get("/auth/verify-registration")
    assert response.status_code == 200
    assert b'form class="otp-form"' in response.data
    assert b'data-otp-form' in response.data
    assert b"otp-resend" in response.data


def test_customer_can_register_and_login(client, app):
    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    with patch("app.routes.auth.secrets.randbelow", return_value=123456), patch(
        "app.routes.auth.queue_registration_code"
    ):
        response = client.post(
            "/auth/register",
            data={
                "full_name": "Test Customer",
                "phone": "01234567890",
                "email": "test@example.com",
                "password": "password123",
                "password_confirmation": "password123",
                "locale": "bn_BD",
            },
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/auth/verify-registration")
        with app.app_context():
            assert db.session.query(User).filter_by(email="test@example.com").first() is None
        wrong_code = client.post("/auth/verify-registration", data={"code": "000000"})
        assert wrong_code.status_code == 200
        with app.app_context():
            assert db.session.query(User).filter_by(email="test@example.com").first() is None
        response = client.post("/auth/verify-registration", data={"code": "123456"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")
    with app.app_context():
        user = db.session.query(User).filter_by(email="test@example.com").one()
        assert user.role == "customer"
        assert user.customer_profile.full_name == "Test Customer"
        assert user.preferred_locale == "bn_BD"

    response = client.post("/auth/login", data={"email": "test@example.com", "password": "password123"})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["role"] == "customer"


def test_flask_login_session_tracks_the_authenticated_user(client, app):
    from flask import session
    from flask_login import current_user

    client.application.config["WTF_CSRF_ENABLED"] = False
    user = User(email="flask-login@example.com", role="customer")
    user.set_password("password123")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with client:
        response = client.post(
            "/auth/login",
            data={"email": "flask-login@example.com", "password": "password123"},
        )
        assert response.status_code == 302
        assert session["_user_id"] == str(user_id)
        assert current_user.is_authenticated
        assert current_user.id == user_id

        response = client.post("/auth/logout")
        assert response.status_code == 302
        assert not current_user.is_authenticated


def test_invalid_login_is_rejected(client):
    client.application.config["WTF_CSRF_ENABLED"] = False
    response = client.post("/auth/login", data={"email": "unknown@example.com", "password": "wrong"}, follow_redirects=True)
    assert b"Invalid email or password" in response.data


def test_one_login_dispatches_customer_and_admin_roles(client, app, login_admin):
    csrf_off = {"WTF_CSRF_ENABLED": False}
    client.application.config.update(csrf_off)
    customer = User(email="customer@example.com", role="customer")
    customer.set_password("password123")
    admin = User(email="admin@example.com", role="admin")
    admin.set_password("password123")
    with app.app_context():
        db.session.add_all([customer, admin])
        db.session.commit()

    # A non-Admin email is refused at the dedicated Admin entry point.
    response = client.post("/admin/login", data={"email": "customer@example.com"})
    assert response.status_code == 403
    assert b"not an Admin account" in response.data

    response = client.post("/auth/login", data={"email": "customer@example.com", "password": "password123"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/customer/dashboard")
    with client.session_transaction() as session:
        assert session["role"] == "customer"

    client.post("/auth/logout")
    response = client.post(
        "/auth/login", data={"email": "admin@example.com", "password": "password123"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    with client.session_transaction() as session:
        assert "user_id" not in session
    login_admin(client, "admin@example.com")
    with client.session_transaction() as session:
        assert session["role"] == "admin"


def test_admin_otp_request_is_gated_and_code_is_single_use(client, app):
    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    admin_email = "otp-admin@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("old-admin-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()

    queued = []
    with patch("app.routes.auth.secrets.randbelow", return_value=123456), patch(
        "app.routes.auth.queue_admin_login_code",
        side_effect=lambda email, code, **kwargs: queued.append((email, code)),
    ):
        known = client.post("/admin/login", data={"email": admin_email})

    assert known.status_code == 302
    assert known.headers["Location"].endswith("/auth/verify-admin-login")

    unknown_client = app.test_client()
    unknown_client.application.config["WTF_CSRF_ENABLED"] = False
    unknown = unknown_client.post("/admin/login", data={"email": "missing@example.com"})
    assert unknown.status_code == 403
    assert b"not an Admin account" in unknown.data
    assert queued == [(admin_email, "123456")]
    with app.app_context():
        challenge = db.session.query(AdminLoginChallenge).one()
        assert challenge.code_hash != "123456"

    response = client.post("/auth/verify-admin-login", data={"code": "123456"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")
    client.post("/auth/logout")
    replay = client.post("/auth/verify-admin-login", data={"code": "123456"}, follow_redirects=True)
    assert replay.status_code == 200
    with client.session_transaction() as browser_session:
        assert "user_id" not in browser_session


def test_admin_otp_rejects_wrong_and_expired_codes(client, app):
    from datetime import datetime, timedelta, timezone

    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    admin_email = "otp-expiry@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("old-admin-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()

    with patch("app.routes.auth.secrets.randbelow", return_value=222222), patch(
        "app.routes.auth.queue_admin_login_code"
    ):
        client.post("/admin/login", data={"email": admin_email})
        wrong = client.post(
            "/auth/verify-admin-login", data={"code": "000000"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert wrong.status_code == 400
        with client.session_transaction() as browser_session:
            challenge_id = browser_session["admin_login_challenge_id"]
        with app.app_context():
            challenge = db.session.get(AdminLoginChallenge, challenge_id)
            challenge.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
            db.session.commit()
        expired = client.post(
            "/auth/verify-admin-login", data={"code": "222222"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
    assert expired.status_code == 400
    assert expired.get_json()["verified"] is False
    with client.session_transaction() as browser_session:
        assert "user_id" not in browser_session


def test_admin_otp_locks_after_five_wrong_attempts(client, app):
    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    admin_email = "otp-lock@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("old-admin-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()

    with patch("app.routes.auth.secrets.randbelow", return_value=333333), patch(
        "app.routes.auth.queue_admin_login_code"
    ):
        client.post("/admin/login", data={"email": admin_email})
        for attempt in range(5):
            response = client.post(
                "/auth/verify-admin-login", data={"code": "000000"},
                headers={"X-Requested-With": "XMLHttpRequest"},
            )
            assert response.status_code == (429 if attempt == 4 else 400)
        with app.app_context():
            challenge = db.session.query(AdminLoginChallenge).one()
            assert challenge.failed_attempts == 5
            assert challenge.consumed_at is not None
        rejected = client.post(
            "/auth/verify-admin-login", data={"code": "333333"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
    assert rejected.status_code == 400
    assert rejected.get_json()["verified"] is False


def test_admin_otp_resend_obeys_cooldown_and_rotates_code(client, app):
    from datetime import datetime, timedelta, timezone

    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    admin_email = "otp-resend@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("old-admin-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()

    codes = []
    with patch("app.routes.auth.secrets.randbelow", side_effect=[444444, 555555]), patch(
        "app.routes.auth.queue_admin_login_code",
        side_effect=lambda _email, code, **_kwargs: codes.append(code),
    ):
        client.post("/admin/login", data={"email": admin_email})
        client.post("/auth/resend-admin-login-code")
        assert codes == ["444444"]
        with client.session_transaction() as browser_session:
            challenge_id = browser_session["admin_login_challenge_id"]
        with app.app_context():
            challenge = db.session.get(AdminLoginChallenge, challenge_id)
            challenge.sent_at = datetime.now(timezone.utc) - timedelta(seconds=61)
            db.session.commit()
        client.post("/auth/resend-admin-login-code")
        assert codes == ["444444", "555555"]
        response = client.post("/auth/verify-admin-login", data={"code": "555555"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")


def test_admin_password_reset_does_not_issue_a_password_code(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    admin_email = "otp-reset@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("legacy-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()

    with patch("app.routes.auth.queue_password_reset_code") as queue:
        response = client.post("/auth/forgot-password", data={"email": admin_email})
    assert response.status_code == 302
    queue.assert_not_called()
    with app.app_context():
        stored_admin = db.session.query(User).filter_by(email=admin_email).one()
        assert stored_admin.password_reset_hash is None


def test_admin_login_without_mail_settings_stays_generic_for_admin_accounts(client, app):
    client.application.config.update(
        WTF_CSRF_ENABLED=False, BREVO_API_KEY=None, MAIL_DEFAULT_SENDER=None
    )
    admin_email = "no-mail-admin@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("legacy-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()

    # Without mail settings no challenge is created, but a real Admin account
    # still receives the generic "code will be sent" response.
    existing = client.post("/admin/login", data={"email": admin_email})
    assert existing.status_code == 302
    assert existing.headers["Location"].endswith("/auth/verify-admin-login")
    with app.app_context():
        assert db.session.query(AdminLoginChallenge).count() == 0

    # An email that is not an Admin account is refused with a clear message.
    unknown_client = app.test_client()
    unknown_client.application.config["WTF_CSRF_ENABLED"] = False
    missing = unknown_client.post("/admin/login", data={"email": "missing@example.com"})
    assert missing.status_code == 403
    assert b"not an Admin account" in missing.data


def test_admin_sign_in_email_renders_one_time_code(app):
    from app.services.mail import send_admin_login_code

    app.config.update(BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com")
    with app.app_context(), patch("app.services.mail.requests.post") as send:
        send.return_value.raise_for_status.return_value = None
        assert send_admin_login_code("admin@example.com", "765432", locale="en_US")
    payload = send.call_args.kwargs["json"]
    assert payload["subject"] == "Your NexHaat admin sign-in code"
    assert "765432" in payload["htmlContent"]
    assert "sign in to the NexHaat admin account" in payload["htmlContent"]


def test_link_hover_underline_is_scoped_to_auth_text_links():
    css_root = Path(__file__).resolve().parents[1] / "app" / "static" / "css"
    site_css = (css_root / "site.css").read_text(encoding="utf-8")
    auth_css = (css_root / "auth.css").read_text(encoding="utf-8")
    assert "html body a:any-link:hover { text-decoration: underline" not in site_css
    assert "html body .auth-main a:any-link" in auth_css
    assert ":not(.brand-lockup):hover {\n  text-decoration: underline;" in auth_css


def test_customer_password_reset_updates_password(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    user = User(email="reset@example.com", role="customer")
    user.set_password("oldpassword")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
    with patch("app.routes.auth.secrets.randbelow", return_value=123456):
        response = client.post("/auth/forgot-password", data={"email": "reset@example.com"})
    assert response.status_code == 302
    response = client.post("/auth/verify-reset-code", data={"code": "123456"})
    assert response.status_code == 302
    response = client.post("/auth/reset-password", data={"password": "newpassword", "password_confirmation": "newpassword"})
    assert response.status_code == 302
    response = client.post("/auth/login", data={"email": "reset@example.com", "password": "newpassword"})
    assert response.status_code == 302


def test_password_reset_ajax_rejects_wrong_code_and_keeps_reset_locked(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    user = User(email="wrong-code@example.com", role="customer")
    user.set_password("oldpassword")
    with app.app_context():
        db.session.add(user)
        db.session.commit()

    with patch("app.routes.auth.secrets.randbelow", return_value=123456), patch(
        "app.routes.auth.queue_password_reset_code"
    ):
        assert client.post("/auth/forgot-password", data={"email": "wrong-code@example.com"}).status_code == 302

    response = client.post(
        "/auth/verify-reset-code",
        data={"code": "000000"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 400
    assert response.get_json()["verified"] is False
    with client.session_transaction() as browser_session:
        assert browser_session["password_reset"]["verified"] is False

    response = client.get("/auth/reset-password")
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/forgot-password")


def test_password_reset_ajax_accepts_valid_code_and_opens_new_password_page(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    user = User(email="valid-code@example.com", role="customer")
    user.set_password("oldpassword")
    with app.app_context():
        db.session.add(user)
        db.session.commit()

    with patch("app.routes.auth.secrets.randbelow", return_value=123456), patch(
        "app.routes.auth.queue_password_reset_code"
    ):
        assert client.post("/auth/forgot-password", data={"email": "valid-code@example.com"}).status_code == 302

    response = client.post(
        "/auth/verify-reset-code",
        data={"code": "123456"},
        headers={"X-Requested-With": "XMLHttpRequest"},
    )
    assert response.status_code == 200
    assert response.get_json()["verified"] is True
    assert response.get_json()["redirect"].endswith("/auth/reset-password")
    with client.session_transaction() as browser_session:
        assert browser_session["password_reset"]["verified"] is True

    response = client.get("/auth/reset-password")
    assert response.status_code == 200
    assert b"Set a new password" in response.data


def test_seller_application_waits_for_admin_review(client, app, login_admin):
    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    with patch("app.routes.auth.secrets.randbelow", return_value=654321), patch(
        "app.routes.auth.queue_registration_code"
    ):
        response = client.post(
            "/auth/seller-application",
            data={
                "store_name": "Green Basket",
                "contact_name": "Sadia Seller",
                "phone": "01712345678",
                "business_address": "Dhaka",
                "email": "seller@example.com",
                "password": "password123",
                "password_confirmation": "password123",
                "locale": "bn_BD",
            },
        )
        assert response.status_code == 302
        with app.app_context():
            assert db.session.query(User).filter_by(email="seller@example.com").first() is None
        response = client.post("/auth/verify-registration", data={"code": "654321"})
    assert response.status_code == 302
    with app.app_context():
        user = db.session.query(User).filter_by(email="seller@example.com").one()
        assert user.role == "seller"
        assert user.seller_profile.approval_status == "pending"
        seller_id = user.id
        seller_profile_id = user.seller_profile.id
        category = Category(name="Seller test goods", slug="seller-test-goods", is_active=True)
        db.session.add(category)
        db.session.commit()
        category_id = category.id
    response = client.post("/auth/login", data={"email": "seller@example.com", "password": "password123"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/seller/dashboard")
    assert b"pending" in client.get("/auth/portal").data.lower()
    assert client.get("/admin").status_code == 403
    assert client.get("/my-orders").status_code == 403

    admin_client = app.test_client()
    admin_email = "review-admin@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("password123")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
    login_admin(admin_client, admin_email)
    assert admin_client.get("/admin").status_code == 200
    response = admin_client.post(
        f"/admin/sellers/{seller_profile_id}/review",
        data={"decision": "approved"},
    )
    assert response.status_code == 302
    with app.app_context():
        profile = db.session.get(User, seller_id).seller_profile
        assert profile.approval_status == "approved"

    client.post("/auth/login", data={"email": "seller@example.com", "password": "password123"})
    upload = client.post(
        "/seller/products/new",
        data={
            "name": "Seller Test Mango",
            "category_id": str(category_id),
            "original_locale": "bn_BD",
            "price": "12.50",
            "stock_quantity": "8",
            "description": "Fresh mango submitted by the verified seller.",
        },
    )
    assert upload.status_code == 302
    with app.app_context():
        product = db.session.query(Product).filter_by(slug="seller-test-mango").one()
        assert product.seller_id == seller_id
        assert product.moderation_status == "pending"
        assert product.is_available is False


def test_admin_invited_rider_uses_expiring_single_use_setup_link(client, app, login_admin):
    client.application.config["WTF_CSRF_ENABLED"] = False
    client.application.config.update(
        BREVO_API_KEY="test-mail-key",
        MAIL_DEFAULT_SENDER="no-reply@example.com",
    )
    admin_email = "invite-admin@example.com"
    admin = User(email=admin_email, role="admin")
    admin.set_password("password123")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
    login_admin(client, admin_email)
    queued = []
    with patch("app.routes.auth.queue_account_invitation", side_effect=lambda *args, **kwargs: queued.append((args, kwargs))):
        response = client.post(
            "/auth/admin/invitations",
            data={"email": "rider@example.com", "role": "rider", "locale": "en_US"},
        )
    assert response.status_code == 302
    assert len(queued) == 1
    invitation_url = queued[0][0][1]
    token = invitation_url.rsplit("/", 1)[1]
    with app.app_context():
        invitation = db.session.query(AccountInvitation).filter_by(email="rider@example.com").one()
        assert invitation.token_digest != token
        invitation_id = invitation.id

    response = client.get(invitation_url)
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["X-Robots-Tag"] == "noindex, nofollow"
    response = client.post(
        invitation_url,
        data={
            "full_name": "Rafi Rider",
            "phone": "01812345678",
            "password": "riderpassword",
            "password_confirmation": "riderpassword",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        rider = db.session.query(User).filter_by(email="rider@example.com").one()
        assert rider.role == "rider"
        assert rider.rider_profile.full_name == "Rafi Rider"
        assert rider.check_password("riderpassword")
        assert db.session.get(AccountInvitation, invitation_id).accepted_at is not None
    assert client.get(invitation_url).status_code == 302
    client.post("/auth/login", data={"email": "rider@example.com", "password": "riderpassword"})
    assert client.get("/auth/portal").status_code == 200
    assert client.get("/cart").status_code == 403


def test_admin_invitation_activates_without_a_password(client, app, login_admin):
    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-mail-key",
        MAIL_DEFAULT_SENDER="no-reply@example.com",
    )
    inviter_email = "inviter@example.com"
    inviter = User(email=inviter_email, role="admin")
    inviter.set_password("legacy-password")
    with app.app_context():
        db.session.add(inviter)
        db.session.commit()
    login_admin(client, inviter_email)

    queued = []
    with patch(
        "app.routes.auth.queue_account_invitation",
        side_effect=lambda *args, **kwargs: queued.append((args, kwargs)),
    ):
        response = client.post(
            "/auth/admin/invitations",
            data={"email": "new-admin@example.com", "role": "admin", "locale": "en_US"},
        )
    assert response.status_code == 302
    invitation_url = queued[0][0][1]
    token = invitation_url.rsplit("/", 1)[1]
    invited_client = app.test_client()
    invited_client.application.config["WTF_CSRF_ENABLED"] = False
    setup_page = invited_client.get(invitation_url)
    assert b"one-time code" in setup_page.data
    assert b"invitation-password" not in setup_page.data
    response = invited_client.post(invitation_url, data={"full_name": "New Admin"})
    assert response.status_code == 302
    with app.app_context():
        invited = db.session.query(User).filter_by(email="new-admin@example.com").one()
        assert invited.role == "admin"
        assert invited.admin_profile.full_name == "New Admin"
        assert invited.password_hash
        stored_invitation = db.session.query(AccountInvitation).filter_by(email=invited.email).one()
        assert stored_invitation.token_digest != token

    login_admin(invited_client, invited.email)
    assert invited_client.get("/admin").status_code == 200


def test_staff_invitation_email_renders_role_in_selected_language(app):
    from app.services.mail import _send

    app.config.update(BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com")
    with app.app_context(), patch("app.services.mail.requests.post") as send:
        send.return_value.raise_for_status.return_value = None
        assert _send(
            "account_invitation",
            "Your NexHaat team invitation",
            ["rider@example.com"],
            invitation_url="https://example.com/invitation/token",
            role="rider",
            locale="bn_BD",
        )

    email_html = send.call_args.kwargs["json"]["htmlContent"]
    assert 'lang="bn-BD"' in email_html
    assert "আপনাকে নেক্সহাট টিমে রাইডার হিসেবে" in email_html


def test_password_reset_works_for_rider_accounts(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    rider = User(email="rider-reset@example.com", role="rider")
    rider.set_password("oldpassword")
    rider.rider_profile = RiderProfile(full_name="Rider Reset", phone="01712345678")
    with app.app_context():
        db.session.add(rider)
        db.session.commit()
    with patch("app.routes.auth.secrets.randbelow", return_value=654321), patch(
        "app.routes.auth.queue_password_reset_code"
    ):
        response = client.post("/auth/forgot-password", data={"email": "rider-reset@example.com"})
    assert response.status_code == 302
    assert client.post("/auth/verify-reset-code", data={"code": "654321"}).status_code == 302
    assert client.post(
        "/auth/reset-password",
        data={"password": "newpassword", "password_confirmation": "newpassword"},
    ).status_code == 302
    assert client.post("/auth/login", data={"email": "rider-reset@example.com", "password": "newpassword"}).status_code == 302


def test_each_role_portal_uses_the_saved_language_and_rtl_direction(app, login_admin):
    accounts = [
        ("portal-customer@example.com", "customer", "bn_BD", CustomerProfile(full_name="Portal Customer", phone="01234567890")),
        ("portal-seller@example.com", "seller", "ar", SellerProfile(store_name="Portal Store", contact_name="Portal Seller", phone="01234567890")),
        ("portal-rider@example.com", "rider", "hi_IN", RiderProfile(full_name="Portal Rider", phone="01234567890")),
        ("portal-admin@example.com", "admin", "en_US", AdminProfile(full_name="Portal Admin")),
    ]
    with app.app_context():
        for email, role, locale, profile in accounts:
            user = User(email=email, role=role, preferred_locale=locale)
            user.set_password("password123")
            setattr(user, f"{role}_profile", profile)
            db.session.add(user)
        db.session.commit()

    expected = {
        "customer": ("bn-BD", "ltr", "আমার অর্ডার"),
        "seller": ("ar", "rtl", "طلبك في قائمة المراجعة"),
        "rider": ("hi-IN", "ltr", "राइडर कार्यक्षेत्र"),
        "admin": ("en-US", "ltr", "Admin dashboard"),
    }
    for email, role, _locale, _profile in accounts:
        with app.app_context():
            role_client = app.test_client()
            if role == "admin":
                login_admin(role_client, email)
            else:
                role_client.post("/auth/login", data={"email": email, "password": "password123"})
            page = role_client.get("/admin" if role == "admin" else "/auth/portal").get_data(as_text=True)
            language, direction, translated_copy = expected[role]
            assert f'<html lang="{language}" dir="{direction}">' in page
            assert translated_copy in page


def test_each_role_is_sent_to_its_own_dashboard_and_other_roles_are_denied(app, login_admin):
    accounts = (
        ("dash-customer@example.com", "customer", CustomerProfile(full_name="Dash Customer", phone="01234567890"), "/customer/dashboard"),
        ("dash-seller@example.com", "seller", SellerProfile(store_name="Dash Store", contact_name="Dash Seller", phone="01234567890", approval_status="pending"), "/seller/dashboard"),
        ("dash-rider@example.com", "rider", RiderProfile(full_name="Dash Rider", phone="01234567890"), "/rider/dashboard"),
        ("dash-admin@example.com", "admin", AdminProfile(full_name="Dash Admin"), "/admin"),
    )
    with app.app_context():
        for email, role, profile, _dashboard in accounts:
            user = User(email=email, role=role)
            user.set_password("password123")
            setattr(user, f"{role}_profile", profile)
            db.session.add(user)
        db.session.commit()

    clients = {}
    for email, role, _profile, dashboard in accounts:
        role_client = app.test_client()
        response = (
            login_admin(role_client, email)
            if role == "admin"
            else role_client.post("/auth/login", data={"email": email, "password": "password123"})
        )
        assert response.status_code == 302
        assert response.headers["Location"].endswith(dashboard)
        assert role_client.get(dashboard).status_code == 200
        clients[role] = role_client

    assert clients["customer"].get("/admin").status_code == 403
    assert clients["seller"].get("/rider/dashboard").status_code == 403
    assert clients["rider"].get("/seller/dashboard").status_code == 403
    assert clients["admin"].get("/customer/dashboard").status_code == 403


def test_customer_can_update_account_details_and_password(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    user = User(email="account@example.com", role="customer")
    user.set_password("oldpassword")
    user.customer_profile = CustomerProfile(full_name="Old Name", phone="01234567890")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client.post("/auth/login", data={"email": "account@example.com", "password": "oldpassword"})
    with tempfile.TemporaryDirectory(
        prefix="profile-image-test-", dir=client.application.static_folder
    ) as upload_root:
        client.application.config["UPLOAD_FOLDER"] = upload_root
        response = client.post(
            "/auth/account",
            data={
                "full_name": "New Name",
                "phone": "01999999999",
                "address_line": "12 NexHaat Street",
                "city": "Dhaka",
                "profile_image": (BytesIO(tiny_png()), "profile.png"),
            },
            content_type="multipart/form-data",
        )
        assert response.status_code == 302
        profile_page = client.get(response.headers["Location"])
        try:
            assert profile_page.status_code == 200
            assert b"data-profile-image-input" in profile_page.data
            assert b"/static/profile-image-test-" in profile_page.data
            image_marker = b'<img data-profile-avatar-image src="'
            image_start = profile_page.data.index(image_marker) + len(image_marker)
            image_end = profile_page.data.index(b'"', image_start)
            image_url = profile_page.data[image_start:image_end].decode("utf-8")
            assert "v=" in image_url
            image_response = client.get(image_url)
            try:
                assert image_response.status_code == 200
                assert image_response.mimetype == "image/png"
                assert image_response.data.startswith(b"\x89PNG\r\n\x1a\n")
            finally:
                image_response.close()
            dashboard_page = client.get("/customer/dashboard")
            try:
                assert dashboard_page.status_code == 200
                assert image_url.encode("utf-8") in dashboard_page.data
            finally:
                dashboard_page.close()
        finally:
            profile_page.close()
    response = client.post(
        "/auth/account/password",
        data={
            "current_password": "oldpassword",
            "password": "newpassword",
            "password_confirmation": "newpassword",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.customer_profile.full_name == "New Name"
        assert user.customer_profile.address.city == "Dhaka"
        assert user.customer_profile.profile_image == "customer-1.png"
        assert user.check_password("newpassword")

    response = client.post("/auth/logout")
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert "user_id" not in session


def test_customer_dashboard_and_account_repair_a_missing_profile_row(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    user = User(email="legacy-customer@example.com", role="customer")
    user.set_password("password123")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    assert client.post(
        "/auth/login", data={"email": "legacy-customer@example.com", "password": "password123"}
    ).status_code == 302
    dashboard = client.get("/customer/dashboard")
    assert dashboard.status_code == 200
    assert b"legacy-customer@example.com" in dashboard.data
    assert b"Account settings" in dashboard.data

    account = client.get("/auth/account")
    assert account.status_code == 200
    assert b"legacy-customer@example.com" in account.data
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.customer_profile is not None
        assert user.customer_profile.full_name == ""
        assert user.customer_profile.phone == ""


def test_admin_cannot_open_customer_account(client, app, login_admin):
    client.application.config["WTF_CSRF_ENABLED"] = False
    admin = User(email="account-admin@example.com", role="admin")
    admin.set_password("password123")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
    login_admin(client, "account-admin@example.com")
    assert client.get("/auth/account").status_code == 403


def test_admin_can_update_profile_and_logout(client, app, login_admin):
    client.application.config["WTF_CSRF_ENABLED"] = False
    admin = User(email="admin-account@example.com", role="admin")
    admin.set_password("oldpassword")
    admin.admin_profile = AdminProfile(full_name="Old Admin")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    login_admin(client, admin.email)
    assert client.get("/auth/admin-account").status_code == 200
    response = client.post("/auth/admin-account", data={"full_name": "New Admin"})
    assert response.status_code == 302
    assert b"Current password" not in client.get("/auth/admin-account").data
    response = client.post(
        "/auth/admin-account/password",
        data={"current_password": "oldpassword", "password": "newpassword", "password_confirmation": "newpassword"},
    )
    assert response.status_code == 404
    with app.app_context():
        admin = db.session.get(User, admin_id)
        assert admin.admin_profile.full_name == "New Admin"
        assert admin.check_password("oldpassword")
    response = client.post("/auth/logout")
    assert response.status_code == 302
def test_admin_otp_request_after_cooldown_with_existing_challenge_stays_valid(client, app):
    """A repeat Admin code request must not error and must rotate to one active challenge."""
    from datetime import datetime, timedelta, timezone

    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    admin = User(email="rotate-admin@example.com", role="admin")
    admin.set_password("unused-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
        stale = AdminLoginChallenge(
            id="stale-admin-challenge",
            user_id=admin.id,
            code_hash="a" * 64,
            sent_at=datetime.now(timezone.utc) - timedelta(days=2),
            expires_at=datetime.now(timezone.utc) - timedelta(days=2),
            failed_attempts=0,
        )
        db.session.add(stale)
        db.session.commit()

    with patch("app.routes.auth.queue_admin_login_code"):
        first = client.post("/admin/login", data={"email": "rotate-admin@example.com"})
        assert first.status_code == 302
        second = client.post("/admin/login", data={"email": "rotate-admin@example.com"})
        assert second.status_code == 302

    with app.app_context():
        remaining = db.session.query(AdminLoginChallenge).all()
        assert len(remaining) == 1
        assert remaining[0].consumed_at is None





def test_forgot_password_does_not_reveal_unknown_customer(client):
    client.application.config["WTF_CSRF_ENABLED"] = False
    response = client.post("/auth/forgot-password", data={"email": "unknown@example.com"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/verify-reset-code")


def test_registration_rejects_mismatched_password_confirmation(client, app):
    response = client.post(
        "/auth/register",
        data={
            "full_name": "Mismatch Customer",
            "phone": "01234567890",
            "email": "mismatch@example.com",
            "password": "password123",
            "password_confirmation": "password321",
            "locale": "bn_BD",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert "পাসওয়ার্ড দুটি মেলেনি" in response.get_data(as_text=True)
    with app.app_context():
        assert db.session.query(User).filter_by(email="mismatch@example.com").first() is None


def test_language_selector_sets_anonymous_locale_and_blocks_external_redirect(client):
    response = client.post("/language", data={"locale": "bn_BD", "next": "https://example.com"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/")
    with client.session_transaction() as session:
        assert session["locale"] == "bn_BD"

    response = client.get("/auth/login")
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert '<html lang="bn-BD" dir="ltr">' in page
    assert "স্বাগতম" in page


def test_browser_language_selects_arabic_rtl_and_translated_auth_ui(client):
    response = client.get("/auth/login", headers={"Accept-Language": "ar,en-US;q=0.8"})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in page
    assert "مرحبًا" in page
    assert "البريد الإلكتروني" in page


def test_browser_language_alias_selects_hindi_translation(client):
    response = client.get("/auth/login", headers={"Accept-Language": "hi-IN,hi;q=0.8"})
    assert response.status_code == 200
    page = response.get_data(as_text=True)
    assert '<html lang="hi-IN" dir="ltr">' in page
    assert "स्वागत है" in page


def test_authenticated_language_choice_is_saved_on_user(client, app):
    user = User(email="language@example.com", role="customer", preferred_locale="bn_BD")
    user.set_password("password123")
    user.customer_profile = CustomerProfile(full_name="Language Customer", phone="01234567890")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    response = client.post(
        "/auth/login",
        data={"email": "language@example.com", "password": "password123", "locale": "ar"},
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["locale"] == "bn_BD"

    client.post("/language", data={"locale": "ar", "next": "/auth/account"})
    with app.app_context():
        user = db.session.get(User, user_id)
        assert user.preferred_locale == "ar"
    page = client.get("/auth/login").get_data(as_text=True)
    assert '<html lang="ar" dir="rtl">' in page


def test_language_route_rejects_unknown_locale(client):
    response = client.post("/language", data={"locale": "xx_XX", "next": "/"})
    assert response.status_code == 400


def test_language_route_requires_csrf_token(client, app):
    app.config["WTF_CSRF_ENABLED"] = True
    response = client.post("/language", data={"locale": "bn_BD", "next": "/"})
    assert response.status_code == 400


def test_password_reset_email_uses_requested_locale(client, app):
    from app.services.mail import send_password_reset_code

    app.config.update(BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com")
    with app.app_context(), patch("app.services.mail.requests.post") as send:
        send.return_value.raise_for_status.return_value = None
        assert send_password_reset_code("customer@example.com", "123456", locale="ar")

    payload = send.call_args.kwargs["json"]
    assert payload["subject"] == "رمز إعادة تعيين كلمة مرور NexHaat"
    assert "استخدم هذا الرمز" in payload["htmlContent"]
    assert 'dir="rtl"' in payload["htmlContent"]


def test_env_admin_is_bootstrapped_from_email_without_password(tmp_path):
    from app import create_app
    from app.config import TestingConfig

    class BootstrapConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'bootstrap.sqlite'}"
        ADMIN_EMAIL = "env-admin@example.com"

    app = create_app(BootstrapConfig)
    with app.app_context():
        admin = db.session.query(User).filter_by(email="env-admin@example.com").one()
        assert admin.role == "admin"
        assert admin.password_hash
        password_hash = admin.password_hash

    app = create_app(BootstrapConfig)
    with app.app_context():
        admin = db.session.query(User).filter_by(email="env-admin@example.com").one()
        assert admin.password_hash == password_hash
