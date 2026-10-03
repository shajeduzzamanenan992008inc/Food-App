"""Regression guards for the fixes in this change set.

Covers the seller/rider Account button (it used to send staff to the
customer-only /auth/account and fail with 403) and the seller product form
(auto slug, specific validation errors, no-category guard).
"""

from app.extensions import db
from app.models import Category, Product, RiderProfile, SellerProfile, User


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


def make_seller(email="acct-seller@example.com", approved=True):
    seller = User(email=email, role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name="Acct Store", contact_name="Owner", phone="01234567890",
        approval_status="approved" if approved else "pending",
    )
    db.session.add(seller)
    db.session.commit()
    return seller


def make_rider(email="acct-rider@example.com"):
    rider = User(email=email, role="rider")
    rider.set_password("password123")
    rider.rider_profile = RiderProfile(full_name="Rider One", phone="01234567890", availability_status="offline")
    db.session.add(rider)
    db.session.commit()
    return rider


def test_header_account_link_points_to_the_right_page_per_role(client, app):
    csrf_off(client)
    with app.app_context():
        make_seller()
        make_rider()
    for email, dashboard, expected in (
        ("acct-seller@example.com", "/seller/dashboard", "/seller/account"),
        ("acct-rider@example.com", "/rider/dashboard", "/rider/account"),
    ):
        client.post("/auth/logout")
        client.post("/auth/login", data={"email": email, "password": "password123"})
        page = client.get(dashboard).get_data(as_text=True)
        assert f'href="{expected}"' in page


def test_seller_account_page_loads_and_saves(client, app):
    csrf_off(client)
    with app.app_context():
        make_seller()
    client.post("/auth/login", data={"email": "acct-seller@example.com", "password": "password123"})

    response = client.get("/seller/account")
    assert response.status_code == 200
    assert b"Acct Store" in response.data

    response = client.post(
        "/seller/account",
        data={
            "store_name": "Renamed Store", "contact_name": "New Owner",
            "phone": "01999999999", "business_address": "12 Market Road",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        profile = db.session.query(SellerProfile).one()
        assert profile.store_name == "Renamed Store"
        assert profile.business_address == "12 Market Road"


def test_rider_account_page_loads_and_saves(client, app):
    csrf_off(client)
    with app.app_context():
        make_rider()
    client.post("/auth/login", data={"email": "acct-rider@example.com", "password": "password123"})

    response = client.get("/rider/account")
    assert response.status_code == 200

    response = client.post(
        "/rider/account",
        data={"full_name": "Rider Two", "phone": "01777777777", "availability_status": "available"},
    )
    assert response.status_code == 302
    with app.app_context():
        profile = db.session.query(RiderProfile).one()
        assert profile.full_name == "Rider Two"
        assert profile.availability_status == "available"


def test_staff_account_pages_reject_the_wrong_role(client, app):
    csrf_off(client)
    with app.app_context():
        make_seller()
    client.post("/auth/login", data={"email": "acct-seller@example.com", "password": "password123"})
    assert client.get("/rider/account").status_code == 403
    assert client.get("/auth/account").status_code == 403


def test_product_form_derives_slug_from_the_name(client, app):
    csrf_off(client)
    with app.app_context():
        make_seller(email="slug-seller@example.com")
        category = Category(name="Slug", slug="slug-cat", is_active=True)
        db.session.add(category)
        db.session.commit()
        category_id = category.id
    client.post("/auth/login", data={"email": "slug-seller@example.com", "password": "password123"})

    response = client.post(
        "/seller/products/new",
        data={
            "name": "Spicy Chicken Burger", "slug": "", "category_id": str(category_id),
            "original_locale": "en_US", "price": "9.99", "discount_price": "",
            "stock_quantity": "3", "description": "A spicy burger for the test suite.",
        },
    )
    assert response.status_code == 302
    with app.app_context():
        product = db.session.query(Product).one()
        assert product.slug == "spicy-chicken-burger"


def test_product_form_reports_the_specific_error(client, app):
    csrf_off(client)
    with app.app_context():
        make_seller(email="err-seller@example.com")
        category = Category(name="Err", slug="err-cat", is_active=True)
        db.session.add(category)
        db.session.commit()
        category_id = category.id
    client.post("/auth/login", data={"email": "err-seller@example.com", "password": "password123"})

    # A discount at or above the price is refused with the real reason.
    response = client.post(
        "/seller/products/new",
        data={
            "name": "Bad Discount", "slug": "bad-discount", "category_id": str(category_id),
            "original_locale": "en_US", "price": "10.00", "discount_price": "12.00",
            "stock_quantity": "1", "description": "Discount is higher than the price.",
        },
        follow_redirects=True,
    )
    assert response.status_code == 400
    assert b"Discount price must be lower than the regular price." in response.data
    with app.app_context():
        assert db.session.query(Product).count() == 0


def test_product_form_disables_submit_without_categories(client, app):
    csrf_off(client)
    with app.app_context():
        make_seller(email="nocat-seller@example.com")
    client.post("/auth/login", data={"email": "nocat-seller@example.com", "password": "password123"})
    page = client.get("/seller/products/new").get_data(as_text=True)
    assert "Ask an Admin to create a category first." in page
    assert 'type="submit" disabled' in page