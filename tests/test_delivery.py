from decimal import Decimal
from io import BytesIO
import struct
import zlib

from app.extensions import db
from app.models import Order, RiderProfile, User


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


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


def make_admin(email):
    admin = User(email=email, role="admin")
    admin.set_password("unused-password")
    db.session.add(admin)
    db.session.commit()
    return email


def make_order(number="FB-DEL-1"):
    order = Order(
        order_number=number, customer_name="Delivery User", phone="01234567890",
        email="delivery@example.com", address="12 Main Street", total=Decimal("12.50"),
        status="pending",
    )
    db.session.add(order)
    db.session.commit()
    return order.id


def make_rider(email, name="Rider One"):
    rider = User(email=email, role="rider")
    rider.set_password("password123")
    rider.rider_profile = RiderProfile(full_name=name, phone="01234567890", availability_status="available")
    db.session.add(rider)
    db.session.commit()
    return rider.id


def test_admin_assigns_rider_and_rider_completes_delivery(client, app, login_admin, tmp_path):
    csrf_off(client)
    client.application.config["PROOF_OF_DELIVERY_FOLDER"] = str(tmp_path)
    with app.app_context():
        make_admin("flow-admin@example.com")
        order_id = make_order()
        rider_id = make_rider("flow-rider@example.com")

    admin_client = app.test_client()
    assert login_admin(admin_client, "flow-admin@example.com").status_code == 302
    assert admin_client.post(
        f"/admin/orders/{order_id}/assign", data={"rider_id": str(rider_id)}
    ).status_code == 302

    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.rider_id == rider_id
        assert order.delivery_status == "assigned"
        assert order.assigned_at is not None

    rider_client = app.test_client()
    assert rider_client.post(
        "/auth/login", data={"email": "flow-rider@example.com", "password": "password123"}
    ).status_code == 302
    assert rider_client.get("/rider/dashboard").status_code == 200

    assert rider_client.post(
        f"/rider/deliveries/{order_id}/status", data={"delivery_status": "picked_up"}
    ).status_code == 302
    assert rider_client.post(
        f"/rider/deliveries/{order_id}/status", data={"delivery_status": "out_for_delivery"}
    ).status_code == 302

    # Delivering without a photo or note is refused.
    assert rider_client.post(
        f"/rider/deliveries/{order_id}/status", data={"delivery_status": "delivered"}
    ).status_code == 302
    with app.app_context():
        assert db.session.get(Order, order_id).delivery_status == "out_for_delivery"

    response = rider_client.post(
        f"/rider/deliveries/{order_id}/status",
        data={
            "delivery_status": "delivered",
            "delivery_note": "Left at the door",
            "proof": (BytesIO(tiny_png()), "pod.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.delivery_status == "delivered"
        assert order.delivery_proof == f"pod-{order_id}.png"
        assert order.delivered_at is not None
        assert order.status == "delivered"


def test_delivery_updates_reject_unauthorized_and_invalid_transitions(client, app, login_admin):
    csrf_off(client)
    with app.app_context():
        make_admin("guard-admin@example.com")
        order_id = make_order("FB-DEL-2")
        rider_id = make_rider("guard-rider@example.com", name="Guard Rider")
        make_rider("other-rider@example.com", name="Other Rider")

    admin_client = app.test_client()
    assert login_admin(admin_client, "guard-admin@example.com").status_code == 302
    assert admin_client.post(
        f"/admin/orders/{order_id}/assign", data={"rider_id": str(rider_id)}
    ).status_code == 302

    # A different rider cannot touch an order that is not assigned to them.
    other_client = app.test_client()
    other_client.post("/auth/login", data={"email": "other-rider@example.com", "password": "password123"})
    assert other_client.post(
        f"/rider/deliveries/{order_id}/status", data={"delivery_status": "picked_up"}
    ).status_code == 404

    # An invalid transition (assigned straight to delivered) is refused.
    rider_client = app.test_client()
    rider_client.post("/auth/login", data={"email": "guard-rider@example.com", "password": "password123"})
    assert rider_client.post(
        f"/rider/deliveries/{order_id}/status",
        data={"delivery_status": "delivered", "delivery_note": "Skipped steps"},
    ).status_code == 302
    with app.app_context():
        order = db.session.get(Order, order_id)
        assert order.delivery_status == "assigned"
        assert order.delivered_at is None
