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


def test_admin_can_deactivate_and_activate_customer(client, app, login_admin):
    csrf_off(client)
    with app.app_context():
        admin = User(email="admin-toggle@example.com", role="admin")
        admin.set_password("unused")
        customer = User(email="cust-toggle@example.com", role="customer", is_active=True)
        customer.set_password("password123")
        customer.customer_profile = CustomerProfile(full_name="Toggle Cust", phone="01700000000")
        db.session.add_all([admin, customer])
        db.session.commit()
        cust_id = customer.id

    assert login_admin(client, "admin-toggle@example.com").status_code == 302

    # 1. Admin deactivates customer
    res = client.post(f"/admin/customers/{cust_id}/deactivate", follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        c = db.session.get(User, cust_id)
        assert c.is_active is False
        assert db.session.query(AuditEvent).filter_by(action="customer.deactivated", target_id=cust_id).count() == 1

    # Customer client to test login
    cust_client = app.test_client()
    csrf_off(cust_client)

    # Inactive customer cannot authenticate
    cust_client.post("/auth/login", data={"email": "cust-toggle@example.com", "password": "password123"}, follow_redirects=True)
    with cust_client.session_transaction() as sess:
        assert "user_id" not in sess

    # 2. Admin activates customer
    res = client.post(f"/admin/customers/{cust_id}/activate", follow_redirects=True)
    assert res.status_code == 200
    with app.app_context():
        c = db.session.get(User, cust_id)
        assert c.is_active is True
        assert db.session.query(AuditEvent).filter_by(action="customer.activated", target_id=cust_id).count() == 1

    # Now customer can log in
    cust_client.post("/auth/login", data={"email": "cust-toggle@example.com", "password": "password123"}, follow_redirects=True)
    with cust_client.session_transaction() as sess:
        assert sess.get("user_id") == cust_id


def test_admin_can_delete_customer_permanently(client, app, login_admin):
    from decimal import Decimal
    from app.models import Order
    csrf_off(client)
    with app.app_context():
        admin = User(email="admin-del@example.com", role="admin")
        admin.set_password("unused")
        customer = User(email="cust-del@example.com", role="customer")
        customer.set_password("password123")
        customer.customer_profile = CustomerProfile(full_name="Del Cust", phone="01711111111")
        db.session.add_all([admin, customer])
        db.session.commit()
        cust_id = customer.id

        order = Order(
            order_number="ORD-DEL-TEST-1",
            user_id=cust_id,
            customer_name="Del Cust",
            phone="01711111111",
            address="Dhaka",
            total=Decimal("500.00"),
        )
        db.session.add(order)
        db.session.commit()
        order_id = order.id

    assert login_admin(client, "admin-del@example.com").status_code == 302

    # Admin deletes customer
    res = client.post(f"/admin/customers/{cust_id}/remove", follow_redirects=True)
    assert res.status_code == 200

    with app.app_context():
        assert db.session.get(User, cust_id) is None
        assert db.session.query(CustomerProfile).filter_by(full_name="Del Cust").first() is None
        # Order still exists with user_id = None
        ord_obj = db.session.get(Order, order_id)
        assert ord_obj is not None
        assert ord_obj.user_id is None
        assert db.session.query(AuditEvent).filter_by(action="customer.remove", target_id=cust_id).count() == 1


def test_non_admin_cannot_manage_customer_accounts(client, app):
    csrf_off(client)
    with app.app_context():
        customer1 = User(email="user1@example.com", role="customer")
        customer1.set_password("password123")
        customer2 = User(email="user2@example.com", role="customer")
        customer2.set_password("password123")
        db.session.add_all([customer1, customer2])
        db.session.commit()
        c2_id = customer2.id

    # Unauthenticated
    assert client.post(f"/admin/customers/{c2_id}/remove").status_code == 403
    assert client.post(f"/admin/customers/{c2_id}/deactivate").status_code == 403
    assert client.post(f"/admin/customers/{c2_id}/activate").status_code == 403

    # Authenticated as regular customer
    client.post("/auth/login", data={"email": "user1@example.com", "password": "password123"})
    assert client.post(f"/admin/customers/{c2_id}/remove").status_code == 403
    assert client.post(f"/admin/customers/{c2_id}/deactivate").status_code == 403
    assert client.post(f"/admin/customers/{c2_id}/activate").status_code == 403
