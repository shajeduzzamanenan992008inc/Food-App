from app.extensions import db
from io import BytesIO
import struct
import zlib

from app.models import (
    AccountInvitation, AdminProfile, CustomerAddress, CustomerProfile,
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


def test_customer_can_register_and_login(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
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
        follow_redirects=True,
    )
    assert response.status_code == 200
    with app.app_context():
        user = db.session.query(User).filter_by(email="test@example.com").one()
        assert user.role == "customer"
        assert user.customer_profile.full_name == "Test Customer"
        assert user.preferred_locale == "bn_BD"

    response = client.post("/auth/login", data={"email": "test@example.com", "password": "password123"})
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session["role"] == "customer"


def test_invalid_login_is_rejected(client):
    client.application.config["WTF_CSRF_ENABLED"] = False
    response = client.post("/auth/login", data={"email": "unknown@example.com", "password": "wrong"}, follow_redirects=True)
    assert b"Invalid email or password" in response.data


def test_one_login_dispatches_customer_and_admin_roles(client, app):
    csrf_off = {"WTF_CSRF_ENABLED": False}
    client.application.config.update(csrf_off)
    customer = User(email="customer@example.com", role="customer")
    customer.set_password("password123")
    admin = User(email="admin@example.com", role="admin")
    admin.set_password("password123")
    with app.app_context():
        db.session.add_all([customer, admin])
        db.session.commit()

    response = client.post("/admin/login", data={"email": "customer@example.com", "password": "password123"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/login")

    response = client.post("/auth/login", data={"email": "customer@example.com", "password": "password123"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/customer/dashboard")
    with client.session_transaction() as session:
        assert session["role"] == "customer"

    client.post("/auth/logout")
    response = client.post("/auth/login", data={"email": "admin@example.com", "password": "password123"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin")
    with client.session_transaction() as session:
        assert session["role"] == "admin"


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


def test_seller_application_waits_for_admin_review(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
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
        user = db.session.query(User).filter_by(email="seller@example.com").one()
        assert user.role == "seller"
        assert user.seller_profile.approval_status == "pending"
        seller_id = user.id
        seller_profile_id = user.seller_profile.id
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
    admin_client.post("/auth/login", data={"email": admin_email, "password": "password123"})
    assert admin_client.get("/admin").status_code == 200
    response = admin_client.post(
        f"/admin/sellers/{seller_profile_id}/review",
        data={"decision": "approved"},
    )
    assert response.status_code == 302
    with app.app_context():
        profile = db.session.get(User, seller_id).seller_profile
        assert profile.approval_status == "approved"


def test_admin_invited_rider_uses_expiring_single_use_setup_link(client, app):
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
    client.post("/auth/login", data={"email": admin_email, "password": "password123"})
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


def test_each_role_portal_uses_the_saved_language_and_rtl_direction(app):
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
            role_client.post("/auth/login", data={"email": email, "password": "password123"})
            page = role_client.get("/admin" if role == "admin" else "/auth/portal").get_data(as_text=True)
            language, direction, translated_copy = expected[role]
            assert f'<html lang="{language}" dir="{direction}">' in page
            assert translated_copy in page


def test_each_role_is_sent_to_its_own_dashboard_and_other_roles_are_denied(app):
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
        response = role_client.post("/auth/login", data={"email": email, "password": "password123"})
        assert response.status_code == 302
        assert response.headers["Location"].endswith(dashboard)
        assert role_client.get(dashboard).status_code == 200
        clients[role] = role_client

    assert clients["customer"].get("/admin").status_code == 403
    assert clients["seller"].get("/rider/dashboard").status_code == 403
    assert clients["rider"].get("/seller/dashboard").status_code == 403
    assert clients["admin"].get("/customer/dashboard").status_code == 403


def test_customer_can_update_account_details_and_password(client, app, tmp_path):
    client.application.config["WTF_CSRF_ENABLED"] = False
    client.application.config["UPLOAD_FOLDER"] = str(tmp_path)
    user = User(email="account@example.com", role="customer")
    user.set_password("oldpassword")
    user.customer_profile = CustomerProfile(full_name="Old Name", phone="01234567890")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    client.post("/auth/login", data={"email": "account@example.com", "password": "oldpassword"})
    response = client.post(
        "/auth/account",
        data={
            "full_name": "New Name",
            "phone": "01999999999",
            "address_line": "12 FreshBite Street",
            "city": "Dhaka",
            "profile_image": (BytesIO(tiny_png()), "profile.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
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


def test_admin_cannot_open_customer_account(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    admin = User(email="account-admin@example.com", role="admin")
    admin.set_password("password123")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
    client.post("/auth/login", data={"email": "account-admin@example.com", "password": "password123"})
    assert client.get("/auth/account").status_code == 403


def test_admin_can_update_profile_password_and_logout(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    admin = User(email="admin-account@example.com", role="admin")
    admin.set_password("oldpassword")
    admin.admin_profile = AdminProfile(full_name="Old Admin")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
        admin_id = admin.id
    client.post("/auth/login", data={"email": admin.email, "password": "oldpassword"})
    assert client.get("/auth/admin-account").status_code == 200
    response = client.post("/auth/admin-account", data={"full_name": "New Admin"})
    assert response.status_code == 302
    response = client.post("/auth/admin-account/password", data={"current_password": "oldpassword", "password": "newpassword", "password_confirmation": "newpassword"})
    assert response.status_code == 302
    with app.app_context():
        admin = db.session.get(User, admin_id)
        assert admin.admin_profile.full_name == "New Admin"
        assert admin.check_password("newpassword")
    response = client.post("/auth/logout")
    assert response.status_code == 302


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


def test_env_admin_is_bootstrapped_without_overwriting_existing_password(tmp_path):
    from app import create_app
    from app.config import TestingConfig

    class BootstrapConfig(TestingConfig):
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{tmp_path / 'bootstrap.sqlite'}"
        ADMIN_EMAIL = "env-admin@example.com"
        ADMIN_PASSWORD = "strong-password-123"

    app = create_app(BootstrapConfig)
    with app.app_context():
        admin = db.session.query(User).filter_by(email="env-admin@example.com").one()
        assert admin.role == "admin"
        assert admin.check_password("strong-password-123")

    app = create_app(BootstrapConfig)
    with app.app_context():
        admin = db.session.query(User).filter_by(email="env-admin@example.com").one()
        assert admin.check_password("strong-password-123")
