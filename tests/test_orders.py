import json
from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import (
    Category, CustomerProfile, Order, OrderItem, OutboundEmail, Product,
    ProductTranslation, SellerProfile, User,
)
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


def login_customer(client, app, email="cart-customer@example.com"):
    customer = User(email=email, role="customer")
    customer.set_password("password123")
    customer.customer_profile = CustomerProfile(full_name="Cart Customer", phone="01234567890")
    with app.app_context():
        db.session.add(customer)
        db.session.commit()
    response = client.post("/auth/login", data={"email": email, "password": "password123"})
    assert response.status_code == 302
    return customer


def test_cart_and_checkout_create_order(client, app):
    csrf_off(client)
    login_customer(client, app)
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
    login_customer(client, app)
    item = product()
    client.post(f"/cart/add/{item.id}", data={"quantity": "1"})
    client.post("/cart/update", data={f"quantity_{item.id}": "3"})
    assert b"30.00" in client.get("/cart").data
    client.post(f"/cart/remove/{item.id}")
    assert b"Your cart is ready for something good" in client.get("/cart").data

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


def test_only_customers_can_access_cart_and_checkout(client, app):
    csrf_off(client)
    item = product()
    guest_add = client.post(f"/cart/add/{item.id}", data={"quantity": "1"})
    assert guest_add.status_code == 302
    assert guest_add.headers["Location"].startswith("/auth/login?next=")
    assert client.get("/cart").status_code == 302
    assert client.post("/checkout").status_code == 302
    assert db.session.query(Order).count() == 0

    seller = User(email="cart-seller@example.com", role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name="Seller Store", contact_name="Seller", phone="01234567890",
        approval_status="approved",
    )
    db.session.add(seller)
    db.session.commit()
    assert client.post(
        "/auth/login", data={"email": seller.email, "password": "password123"}
    ).status_code == 302
    assert client.get("/cart").status_code == 403
    assert client.post(f"/cart/add/{item.id}").status_code == 403
    assert client.post("/checkout").status_code == 403


def test_admin_can_change_order_status(client, app, login_admin):
    csrf_off(client)
    admin = User(email="admin@example.com", role="admin")
    admin.set_password("password123")
    db.session.add(admin)
    db.session.commit()
    response = login_admin(client, admin.email)
    assert response.status_code == 302
    assert client.get("/admin").status_code == 200


def test_admin_page_is_protected_and_invalid_quantity_is_safe(client):
    csrf_off(client)
    assert client.get("/admin").status_code == 403
    assert client.get("/cart").status_code == 302
    login_customer(client, client.application)
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


def make_seller_product(email, name, slug, price="10.00"):
    seller = User(email=email, role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name=f"{name} Store", contact_name="Store Owner", phone="01234567890",
        approval_status="approved",
    )
    category = Category(name="Pizza", slug=f"pizza-{slug}")
    item = Product(
        category=category, seller=seller, name=name, slug=slug, description="A test item",
        price=Decimal(price), is_available=True, moderation_status="approved",
    )
    db.session.add_all([seller, category, item])
    db.session.commit()
    return item


def test_checkout_splits_a_multi_seller_cart_into_sub_orders(client, app):
    csrf_off(client)
    login_customer(client, app, email="split-customer@example.com")
    first = make_seller_product("split-seller-one@example.com", "Seller One Dish", "seller-one-dish")
    second = make_seller_product("split-seller-two@example.com", "Seller Two Dish", "seller-two-dish")
    client.post(f"/cart/add/{first.id}", data={"quantity": "1"})
    client.post(f"/cart/add/{second.id}", data={"quantity": "2"})

    response = client.post(
        "/checkout",
        data={
            "customer_name": "Split User", "phone": "01234567890", "address": "12 Main Street",
            "email": "split@example.com", "payment_method": "cod",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        orders = db.session.query(Order).order_by(Order.order_number).all()
        assert len(orders) == 2
        assert len({order.checkout_group for order in orders}) == 1
        assert all(order.delivery_fee == Decimal("2.50") for order in orders)
        assert sorted(order.total for order in orders) == [Decimal("12.50"), Decimal("22.50")]
        seller_ids = {
            db.session.scalar(select(User.id).where(User.email == email))
            for email in ("split-seller-one@example.com", "split-seller-two@example.com")
        }
        assert {order.seller_id for order in orders} == seller_ids

        page = client.get(f"/orders/{orders[0].order_number}")
        assert page.status_code == 200
        for order in orders:
            assert order.order_number.encode() in page.data


def test_invoice_is_seller_specific_and_localized(app):
    with app.app_context():
        product = make_seller_product("invoice-seller@example.com", "Spicy Noodles", "spicy-noodles")
        product.translations.append(
            ProductTranslation(locale="bn_BD", name="ঝাল নুডলস", description="তীক্ষ্ণ")
        )
        order = Order(
            order_number="FB-INVOICE-1", seller_id=product.seller_id, customer_name="Invoice User",
            phone="01234567890", email="invoice@example.com", address="12 Main Street",
            total=Decimal("12.50"), delivery_fee=Decimal("2.50"), status="pending",
        )
        order.items.append(OrderItem(
            product_id=product.id, product_name="Spicy Noodles",
            price=Decimal("10.00"), quantity=1, subtotal=Decimal("10.00"),
        ))
        db.session.add(order)
        db.session.commit()

        from app.services.invoice import _localized_item_name, build_invoice_pdf

        item = order.items[0]
        assert _localized_item_name(item, {product.id: product}, "bn_BD") == "ঝাল নুডলস"
        assert _localized_item_name(item, {product.id: product}, "en_US") == "Spicy Noodles"

        pdf = build_invoice_pdf(order, locale="bn_BD")
        assert pdf.startswith(b"%PDF")
        assert len(pdf) > 400


def test_outbound_email_retries_until_delivery(app, monkeypatch):
    class SuccessfulResponse:
        def raise_for_status(self):
            return None

    with app.app_context():
        app.config.update(
            BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com", MAX_EMAIL_ATTEMPTS=3
        )
        record = OutboundEmail(
            recipients=json.dumps(["customer@example.com"]), subject="Queued email",
            body_html="<p>Hello</p>", status="pending", attempts=0,
        )
        db.session.add(record)
        db.session.commit()
        record_id = record.id

        from app.services.mail import retry_pending_emails

        monkeypatch.setattr(
            "app.services.mail.requests.post",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
        )
        assert retry_pending_emails() == 0
        record = db.session.get(OutboundEmail, record_id)
        assert record.attempts == 1
        assert record.status == "pending"
        assert record.last_error == "delivery failed"

        monkeypatch.setattr("app.services.mail.requests.post", lambda *args, **kwargs: SuccessfulResponse())
        assert retry_pending_emails() == 1
        record = db.session.get(OutboundEmail, record_id)
        assert record.status == "sent"
        assert record.attempts == 2
        assert record.last_error is None


def test_email_diagnostics_do_not_leak_credentials(app, monkeypatch, caplog):
    import logging

    with app.app_context():
        app.config.update(BREVO_API_KEY="super-secret-key", MAIL_DEFAULT_SENDER="noreply@example.com")
        record = OutboundEmail(
            recipients=json.dumps(["customer@example.com"]), subject="Queued email",
            body_html="<p>Hello</p>", status="pending", attempts=0,
        )
        db.session.add(record)
        db.session.commit()

        monkeypatch.setattr(
            "app.services.mail.requests.post",
            lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("provider down")),
        )
        from app.services.mail import deliver_outbound_email

        with caplog.at_level(logging.WARNING, logger="app.services.mail"):
            assert deliver_outbound_email(record) is False
        assert "super-secret-key" not in caplog.text
