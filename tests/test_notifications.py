from decimal import Decimal

from app.extensions import db
from app.models import Category, CustomerProfile, Notification, Order, OrderItem, Product, RiderProfile, User


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


def make_customer(email="notify@example.com", name="Notify User"):
    user = User(email=email, role="customer")
    user.set_password("password123")
    user.customer_profile = CustomerProfile(full_name=name, phone="01234567890")
    db.session.add(user)
    db.session.commit()
    return user


def make_product(slug="notify-pizza"):
    category = Category(name="Pizza", slug="pizza", is_active=True)
    product = Product(
        category=category, name="Notify Pizza", slug=slug,
        description="A pizza", price=Decimal("10.00"), is_available=True,
    )
    db.session.add(product)
    db.session.commit()
    return product


def test_service_creates_and_reads_notifications(app):
    with app.app_context():
        user = make_customer()
        from app.services.notifications import (
            mark_all_read, mark_read, notifications_for, notify, unread_count,
        )

        first = notify(user.id, "Order received", type="order", link="/orders/FB-1")
        notify(user.id, "Second update", type="delivery")
        assert first is not None
        assert unread_count(user) == 2
        assert [item.message for item in notifications_for(user)][0] == "Second update"

        assert mark_read(user, first.id) is True
        assert unread_count(user) == 1
        assert mark_read(user, 999999) is False
        assert mark_all_read(user) == 1
        assert unread_count(user) == 0


def test_notify_ignores_blank_user_and_bad_type(app):
    with app.app_context():
        user = make_customer(email="blank@example.com")
        from app.services.notifications import notify

        assert notify(None, "No recipient") is None
        created = notify(user.id, "Weird type", type="unknown")
        assert created.type == "system"


def test_checkout_notifies_customer_and_seller(client, app):
    csrf_off(client)
    with app.app_context():
        seller = User(email="notify-seller@example.com", role="seller")
        seller.set_password("password123")
        db.session.add(seller)
        db.session.commit()
        product = make_product(slug="checkout-notify")
        product.seller_id = seller.id
        db.session.commit()
        seller_id = seller.id

        buyer = make_customer(email="checkout-buyer@example.com")
        buyer_id = buyer.id
        product_id = product.id

    client.post("/auth/login", data={"email": "checkout-buyer@example.com", "password": "password123"})
    client.post(f"/cart/add/{product_id}", data={"quantity": "1"})
    assert client.post(
        "/checkout",
        data={
            "customer_name": "Notify Buyer", "phone": "01234567890",
            "address": "12 Main Street", "email": "checkout-buyer@example.com",
            "payment_method": "cod",
        },
    ).status_code == 302

    with app.app_context():
        buyer_notes = db.session.query(Notification).filter_by(user_id=buyer_id).all()
        seller_notes = db.session.query(Notification).filter_by(user_id=seller_id).all()
        assert len(buyer_notes) == 1
        assert buyer_notes[0].type == "order"
        assert len(seller_notes) == 1
        assert seller_notes[0].type == "order"


def test_notification_page_requires_login(client):
    response = client.get("/notifications")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_notification_page_lists_and_marks_read(client, app):
    csrf_off(client)
    with app.app_context():
        user = make_customer(email="page@example.com")
        user_id = user.id
        from app.services.notifications import notify

        note = notify(user.id, "Your order shipped", type="order", link="/orders/FB-PAGE")
        note_id = note.id

    client.post("/auth/login", data={"email": "page@example.com", "password": "password123"})
    page = client.get("/notifications").get_data(as_text=True)
    assert "Your order shipped" in page

    response = client.post(f"/notifications/{note_id}/read")
    assert response.status_code == 302
    with app.app_context():
        assert db.session.get(Notification, note_id).is_read is True
        assert db.session.get(User, user_id) is not None


def test_notification_page_mark_all_read(client, app):
    csrf_off(client)
    with app.app_context():
        user = make_customer(email="all@example.com")
        user_id = user.id
        from app.services.notifications import notify

        notify(user.id, "One")
        notify(user.id, "Two")

    client.post("/auth/login", data={"email": "all@example.com", "password": "password123"})
    assert client.post("/notifications/read-all").status_code == 302
    with app.app_context():
        assert db.session.query(Notification).filter_by(user_id=user_id, is_read=False).count() == 0


def test_user_notification_is_scoped_to_owner(client, app):
    csrf_off(client)
    with app.app_context():
        owner = make_customer(email="owner@example.com")
        make_customer(email="other@example.com")
        from app.services.notifications import notify

        note_id = notify(owner.id, "Owner only").id

    client.post("/auth/login", data={"email": "other@example.com", "password": "password123"})
    assert client.post(f"/notifications/{note_id}/read").status_code == 404


def test_rider_delivered_notifies_customer(client, app):
    csrf_off(client)
    with app.app_context():
        customer = make_customer(email="deliver-notify@example.com")
        rider = User(email="deliver-rider@example.com", role="rider")
        rider.set_password("password123")
        rider.rider_profile = RiderProfile(full_name="Rider", phone="01234567890", availability_status="available")
        db.session.add(rider)
        db.session.commit()

        order = Order(
            order_number="FB-NOTIFY-DEL", user_id=customer.id, rider_id=rider.id,
            customer_name="Deliver Me", phone="01234567890", address="12 Main Street",
            total=Decimal("10.00"), status="confirmed", delivery_status="out_for_delivery",
        )
        db.session.add(order)
        db.session.commit()
        customer_id, order_id = customer.id, order.id

    rider_client = app.test_client()
    csrf_off(rider_client)
    rider_client.post("/auth/login", data={"email": "deliver-rider@example.com", "password": "password123"})
    assert rider_client.post(
        f"/rider/deliveries/{order_id}/status",
        data={"delivery_status": "delivered", "delivery_note": "Left at the door"},
    ).status_code == 302

    with app.app_context():
        notes = db.session.query(Notification).filter_by(user_id=customer_id).all()
        assert any("delivered" in note.message.lower() for note in notes)


def test_api_lists_and_marks_notifications(client, app):
    csrf_off(client)
    with app.app_context():
        user = make_customer(email="api-notify@example.com")
        from app.services.notifications import notify

        note = notify(user.id, "API notification", type="order", link="/orders/FB-API")
        note_id = note.id

    assert client.get("/api/v1/notifications").status_code == 401

    client.post("/auth/login", data={"email": "api-notify@example.com", "password": "password123"})
    response = client.get("/api/v1/notifications")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["unread"] == 1
    assert body["data"]["notifications"][0]["message"] == "API notification"

    assert client.post(f"/api/v1/notifications/{note_id}/read").status_code == 200
    assert client.get("/api/v1/notifications").get_json()["data"]["unread"] == 0

    assert client.post("/api/v1/notifications/read-all").status_code == 200