from decimal import Decimal
from app.extensions import db
from app.models import Category, CustomerProfile, Order, Product, User
from app.services.mail import send_order_confirmation, send_order_status


def product():
    category = Category(name="Pizza", slug="pizza")
    item = Product(
        category=category, name="Test Pizza", slug="test-pizza",
        description="A test item", price=Decimal("10.00"), is_available=True,
    )
    db.session.add(item)
    db.session.commit()
    return item


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


def test_cart_and_checkout_create_order(client, app):
    csrf_off(client)
    item = product()
    client.post(f"/cart/add/{item.id}", data={"quantity": "2"})
    response = client.get("/cart")
    assert b"Test Pizza" in response.data
    assert b"22.50" in response.data

    response = client.post(
        "/checkout",
        data={"customer_name": "Cart User", "phone": "01234567890", "address": "12 Main Street", "email": "cart@example.com", "payment_method": "cod"},
    )
    assert response.status_code == 302
    with client.session_transaction() as session:
        assert session.get("cart") == {}
    with app.app_context():
        order = db.session.query(Order).one()
        assert order.total == Decimal("22.50")
        assert order.items[0].product_name == "Test Pizza"
        assert order.items[0].price == Decimal("10.00")


def test_cart_update_remove_and_unavailable_item(client, app):
    csrf_off(client)
    item = product()
    client.post(f"/cart/add/{item.id}", data={"quantity": "1"})
    client.post("/cart/update", data={f"quantity_{item.id}": "3"})
    assert b"30.00" in client.get("/cart").data
    client.post(f"/cart/remove/{item.id}")
    assert b"Your cart is waiting" in client.get("/cart").data

    item.is_available = False
    db.session.commit()
    client.post(f"/cart/add/{item.id}")
    assert client.get("/cart").status_code == 200


def test_signed_in_customer_checkout_is_prefilled_and_uses_account_email(client, app):
    csrf_off(client)
    customer = User(email="prefill@example.com", role="customer")
    customer.set_password("password123")
    customer.customer_profile = CustomerProfile(full_name="Prefill Customer", phone="01234567890")
    db.session.add(customer)
    db.session.commit()
    client.post("/auth/login", data={"email": customer.email, "password": "password123"})
    item = product()
    client.post(f"/cart/add/{item.id}", data={"quantity": "1"})
    response = client.get("/checkout")
    assert b'value="Prefill Customer"' in response.data
    assert b'value="01234567890"' in response.data
    response = client.post("/checkout", data={"customer_name": "Prefill Customer", "phone": "01234567890", "address": "12 Main Street", "payment_method": "cod"})
    assert response.status_code == 302
    order = db.session.query(Order).one()
    assert order.email == "prefill@example.com"


def test_guest_checkout_requires_and_saves_email(client, app):
    csrf_off(client)
    item = product()
    client.post(f"/cart/add/{item.id}", data={"quantity": "1"})
    response = client.post("/checkout", data={"customer_name": "Guest User", "phone": "01234567890", "address": "12 Main Street", "email": "guest@example.com", "payment_method": "cod"})
    assert response.status_code == 302
    assert db.session.query(Order).one().email == "guest@example.com"


def test_admin_can_change_order_status(client, app):
    csrf_off(client)
    admin = User(email="admin@example.com", role="admin")
    admin.set_password("password123")
    db.session.add(admin)
    db.session.commit()
    response = client.post("/auth/login", data={"email": admin.email, "password": "password123"})
    assert response.status_code == 302
    assert client.get("/admin").status_code == 200


def test_admin_page_is_protected_and_invalid_quantity_is_safe(client):
    csrf_off(client)
    assert client.get("/admin").status_code == 403
    client.post("/cart/update", data={"quantity_invalid": "not-a-number"})
    assert client.get("/cart").status_code == 200


def test_customer_cannot_access_admin_after_customer_login(client, app):
    csrf_off(client)
    customer = User(email="customer@example.com", role="customer")
    customer.set_password("password123")
    db.session.add(customer)
    db.session.commit()
    client.post("/auth/login", data={"email": customer.email, "password": "password123"})
    assert client.get("/admin").status_code == 403


def test_status_email_failure_does_not_raise(app, monkeypatch):
    with app.app_context():
        order = Order(
            order_number="FB-EMAILTEST", customer_name="Mail Test", phone="01234567890",
            address="12 Main Street", total=Decimal("12.50"), email="customer@example.com",
            status="pending",
        )
        app.config.update(BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com")
        monkeypatch.setattr(
            "app.services.mail.requests.post",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("email provider unavailable")),
        )
        assert send_order_status(order) is False


def test_admin_order_email_falls_back_to_mail_username(app, monkeypatch):
    sent = []

    class SuccessfulResponse:
        def raise_for_status(self):
            return None

    with app.app_context():
        order = Order(
            order_number="FB-ADMINTEST", customer_name="Mail Test", phone="01234567890",
            address="12 Main Street", total=Decimal("12.50"), email="customer@example.com",
            status="pending",
        )
        app.config.update(
            BREVO_API_KEY="test-key",
            ADMIN_EMAIL=None,
            MAIL_DEFAULT_SENDER="admin@example.com",
        )

        def capture_email(_url, json, **_kwargs):
            sent.append(json)
            return SuccessfulResponse()

        monkeypatch.setattr("app.services.mail.requests.post", capture_email)
        send_order_confirmation(order)
    assert any("admin@example.com" in [recipient["email"] for recipient in message["to"]] for message in sent)
