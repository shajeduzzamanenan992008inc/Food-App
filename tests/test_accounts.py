from unittest.mock import patch

from app.extensions import db
from app.models import AuditEvent, CustomerProfile, RiderProfile, User


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


def test_customer_can_delete_their_own_account(client, app):
    csrf_off(client)
    user = User(email="self-delete@example.com", role="customer")
    user.set_password("password123")
    user.customer_profile = CustomerProfile(full_name="Delete Me", phone="01234567890")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    assert client.post(
        "/auth/login", data={"email": "self-delete@example.com", "password": "password123"}
    ).status_code == 302
    assert client.post("/auth/account/delete").status_code == 302
    with client.session_transaction() as browser_session:
        assert "user_id" not in browser_session
    with app.app_context():
        assert db.session.get(User, user_id) is None
        assert db.session.query(AuditEvent).filter_by(action="account.delete_self").count() == 1


def test_primary_admin_deletes_a_rider_but_not_the_primary_account(client, app, login_admin):
    csrf_off(client)
    client.application.config.update(ADMIN_EMAIL="primary@example.com")
    with app.app_context():
        primary = User(email="primary@example.com", role="admin")
        primary.set_password("unused-password")
        rider = User(email="rider-delete@example.com", role="rider")
        rider.set_password("password123")
        rider.rider_profile = RiderProfile(full_name="Rider To Delete", phone="01234567890")
        db.session.add_all([primary, rider])
        db.session.commit()
        primary_id = primary.id
        rider_id = rider.id

    assert login_admin(client, "primary@example.com").status_code == 302

    # The primary Admin account is protected.
    client.post(f"/admin/accounts/{primary_id}/remove", follow_redirects=True)
    with app.app_context():
        assert db.session.get(User, primary_id) is not None

    # Another staff account can be deleted.
    assert client.post(f"/admin/accounts/{rider_id}/remove").status_code == 302
    with app.app_context():
        assert db.session.get(User, rider_id) is None
        assert db.session.query(AuditEvent).filter_by(action="account.remove").count() == 1


def test_non_primary_admin_cannot_delete_accounts(client, app, login_admin):
    csrf_off(client)
    client.application.config.update(ADMIN_EMAIL="primary@example.com")
    with app.app_context():
        sub_admin = User(email="sub-admin@example.com", role="admin")
        sub_admin.set_password("unused-password")
        rider = User(email="keep-rider@example.com", role="rider")
        rider.set_password("password123")
        rider.rider_profile = RiderProfile(full_name="Keep Me", phone="01234567890")
        db.session.add_all([sub_admin, rider])
        db.session.commit()
        rider_id = rider.id

    assert login_admin(client, "sub-admin@example.com").status_code == 302
    assert client.post(f"/admin/accounts/{rider_id}/remove").status_code == 403
    with app.app_context():
        assert db.session.get(User, rider_id) is not None


def test_admin_login_rejects_a_non_admin_email(client, app):
    csrf_off(client)
    customer = User(email="plain@example.com", role="customer")
    customer.set_password("password123")
    with app.app_context():
        db.session.add(customer)
        db.session.commit()
    client.application.config.update(
        BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com"
    )

    response = client.post("/admin/login", data={"email": "plain@example.com"})
    assert response.status_code == 403
    assert b"not an Admin account" in response.data
    with app.app_context():
        assert db.session.query(AuditEvent).filter_by(detail="not an admin account").count() == 1


def test_admin_login_still_accepts_an_admin_email(client, app):
    csrf_off(client)
    admin = User(email="good-admin@example.com", role="admin")
    admin.set_password("unused-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
    client.application.config.update(
        BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com"
    )
    with patch("app.routes.auth.queue_admin_login_code"):
        response = client.post("/admin/login", data={"email": "good-admin@example.com"})
    assert response.status_code == 302
    assert response.headers["Location"].endswith("/auth/verify-admin-login")
