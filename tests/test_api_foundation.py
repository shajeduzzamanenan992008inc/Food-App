import json
from decimal import Decimal
from unittest.mock import patch

from app.api.responses import (
    created_response,
    error_response,
    paginated_response,
    success_response,
)
from app.api.serializers import category_to_dict, product_to_dict
from app.extensions import db
from app.models import (
    AdminLoginChallenge, Category, CustomerProfile, Order, Product, ProductVariant,
    RegistrationChallenge, Review, SellerProfile, User,
)


def test_health_endpoints(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}

    response = client.get("/health/db")
    assert response.status_code == 200
    assert response.get_json() == {"status": "ok"}

    response = client.get("/api/v1/health")
    assert response.status_code == 200
    body = response.get_json()
    assert body == {"success": True, "data": {"status": "ok"}, "message": "Success"}


def test_csrf_token_endpoint(client):
    response = client.get("/api/v1/auth/csrf")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["csrf_token"]


def test_unknown_api_route_returns_json_404(client):
    response = client.get("/api/v1/does-not-exist")
    assert response.status_code == 404
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "NOT_FOUND"


def test_unknown_site_route_still_returns_html(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.get_json() is None
    assert b"<" in response.data


def test_api_method_not_allowed_is_json(client):
    response = client.post("/api/v1/health")
    assert response.status_code == 405
    body = response.get_json()
    assert body["success"] is False
    assert body["error"]["code"] == "METHOD_NOT_ALLOWED"


def test_api_error_does_not_leak_internals(client):
    response = client.get("/api/v1/does-not-exist")
    payload = json.dumps(response.get_json())
    assert "Traceback" not in payload
    assert "sqlite" not in payload.lower()
    assert "\\app\\" not in payload


def test_response_helpers_have_consistent_shape(app):
    with app.test_request_context("/"):
        body, status = success_response({"id": 1})
        assert status == 200
        assert json.loads(body.get_data()) == {"success": True, "data": {"id": 1}, "message": "Success"}

        body, status = created_response({"id": 2})
        assert status == 201

        body, status = error_response("VALIDATION_ERROR", "Invalid request", 422)
        payload = json.loads(body.get_data())
        assert status == 422
        assert payload == {"success": False, "error": {"code": "VALIDATION_ERROR", "message": "Invalid request"}}

        body, status = paginated_response([{"id": 1}], page=1, limit=20, total=1)
        payload = json.loads(body.get_data())
        assert payload["success"] is True
        assert payload["pagination"] == {"page": 1, "limit": 20, "total": 1}


def test_product_serializer_uses_fixed_precision_money(app):
    with app.app_context():
        category = Category(name="Pizza", slug="pizza", is_active=True)
        product = Product(
            category=category,
            name="Garden Pizza",
            slug="garden-pizza",
            description="Fresh basil and tomato",
            price=Decimal("12.50"),
            is_available=True,
        )
        db.session.add(product)
        db.session.commit()

        category_data = category_to_dict(category)
        assert category_data["slug"] == "pizza"

        data = product_to_dict(product)
        assert data["price"] == "12.50"
        assert data["display_price"] == "12.50"
        assert data["stock"] == 0
        assert data["category_id"] == category.id
        assert data["is_available"] is True


def test_api_catalog_search_filters_and_paginates(client, app):
    with app.app_context():
        category = Category(name="API Pantry", slug="api-pantry", is_active=True)
        products = [
            Product(
                category=category, name="Golden Kiwi", slug="api-golden-kiwi",
                description="Fresh fruit", price=Decimal("3.50"), stock_quantity=4,
                is_available=True, moderation_status="approved",
            ),
            Product(
                category=category, name="Green Kiwi", slug="api-green-kiwi",
                description="Tart fruit", price=Decimal("5.00"), stock_quantity=2,
                is_available=True, moderation_status="approved",
            ),
            Product(
                category=category, name="Hidden Kiwi", slug="api-hidden-kiwi",
                description="Pending listing", price=Decimal("1.00"), stock_quantity=1,
                is_available=False, moderation_status="pending",
            ),
        ]
        db.session.add_all([category, *products])
        db.session.commit()
        category_id = category.id
        visible_product_id = products[0].id

    categories = client.get("/api/v1/categories")
    assert categories.status_code == 200
    assert any(item["slug"] == "api-pantry" for item in categories.get_json()["data"])

    response = client.get(
        f"/api/v1/products?category_id={category_id}&min_price=3&max_price=5&sort=price_asc&limit=1"
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert [item["name"] for item in payload["data"]] == ["Golden Kiwi"]
    assert payload["pagination"] == {"page": 1, "limit": 1, "total": 2}

    detail = client.get(f"/api/v1/products/{visible_product_id}")
    assert detail.status_code == 200
    assert detail.get_json()["data"]["name"] == "Golden Kiwi"
    search = client.get("/api/v1/search?q=kiwi&sort=price_desc")
    assert [item["name"] for item in search.get_json()["data"][:2]] == ["Green Kiwi", "Golden Kiwi"]
    category_page = client.get("/api/v1/categories/api-pantry")
    assert category_page.status_code == 200
    assert category_page.get_json()["pagination"]["total"] == 2

    invalid = client.get("/api/v1/products?min_price=9&max_price=2")
    assert invalid.status_code == 422


def test_api_cart_checkout_orders_and_cancel_restore_inventory(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    customer = User(email="commerce-api@example.com", role="customer")
    customer.set_password("password123")
    customer.customer_profile = CustomerProfile(full_name="Commerce API", phone="01234567890")
    category = Category(name="API checkout", slug="api-checkout", is_active=True)
    product = Product(
        category=category,
        name="API oranges",
        slug="api-oranges",
        description="Fresh oranges",
        price=Decimal("4.25"),
        stock_quantity=3,
        is_available=True,
    )
    db.session.add_all([customer, category, product])
    db.session.commit()
    product_id = product.id

    assert client.post(
        "/api/v1/auth/login",
        json={"email": customer.email, "password": "password123"},
    ).status_code == 200
    added = client.post(
        "/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}
    )
    assert added.status_code == 201
    assert added.get_json()["data"]["total"] == "11.00"
    preview = client.post("/api/v1/checkout/preview", json={})
    assert preview.status_code == 200
    assert preview.get_json()["data"]["orders"][0]["total"] == "11.00"

    placed = client.post(
        "/api/v1/checkout",
        json={
            "customer_name": "Commerce API",
            "phone": "01234567890",
            "address": "12 Main Street",
            "payment_method": "cod",
        },
    )
    assert placed.status_code == 201
    order_number = placed.get_json()["data"]["orders"][0]["order_number"]
    assert client.get("/api/v1/orders").get_json()["data"][0]["order_number"] == order_number
    assert client.get(f"/api/v1/orders/{order_number}").status_code == 200
    with app.app_context():
        assert db.session.get(Product, product_id).stock_quantity == 1

    cancelled = client.post(f"/api/v1/orders/{order_number}/cancel")
    assert cancelled.status_code == 200
    assert cancelled.get_json()["data"]["status"] == "cancelled"
    with app.app_context():
        assert db.session.get(Product, product_id).stock_quantity == 3
        assert db.session.query(Order).one().status == "cancelled"


def test_api_seller_dashboard_and_orders_are_owner_scoped(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    seller = User(email="api-seller-orders@example.com", role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name="API Seller Store", contact_name="Seller Owner", phone="01234567890",
        approval_status="approved",
    )
    foreign_seller = User(email="api-foreign-seller@example.com", role="seller")
    foreign_seller.set_password("password123")
    foreign_seller.seller_profile = SellerProfile(
        store_name="Foreign Store", contact_name="Foreign Owner", phone="01987654321",
        approval_status="approved",
    )
    db.session.add_all([seller, foreign_seller])
    db.session.flush()
    own_order = Order(
        order_number="API-SELLER-OWN", seller_id=seller.id,
        customer_name="Buyer", phone="01234567890", address="Dhaka",
        total=Decimal("12.50"), status="pending",
    )
    foreign_order = Order(
        order_number="API-SELLER-OTHER", seller_id=foreign_seller.id,
        customer_name="Other Buyer", phone="01234567890", address="Dhaka",
        total=Decimal("15.00"), status="pending",
    )
    db.session.add_all([own_order, foreign_order])
    db.session.commit()

    assert client.post(
        "/api/v1/auth/login",
        json={"email": seller.email, "password": "password123"},
    ).status_code == 200
    dashboard = client.get("/api/v1/seller/dashboard")
    assert dashboard.status_code == 200
    assert dashboard.get_json()["data"]["pending_orders"] == 1
    orders = client.get("/api/v1/seller/orders")
    assert [order["order_number"] for order in orders.get_json()["data"]] == ["API-SELLER-OWN"]

    own_update = client.patch(
        f"/api/v1/seller/orders/{own_order.id}", json={"status": "confirmed"}
    )
    assert own_update.status_code == 200
    foreign_update = client.patch(
        f"/api/v1/seller/orders/{foreign_order.id}", json={"status": "confirmed"}
    )
    assert foreign_update.status_code == 404


def test_api_seller_product_crud_is_owner_scoped_and_requires_moderation(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    seller = User(email="api-product-seller@example.com", role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name="API Products", contact_name="Owner", phone="01234567890",
        approval_status="approved",
    )
    other_seller = User(email="api-product-other@example.com", role="seller")
    other_seller.set_password("password123")
    other_seller.seller_profile = SellerProfile(
        store_name="Other Products", contact_name="Other", phone="01987654321",
        approval_status="approved",
    )
    category = Category(name="API Seller Goods", slug="api-seller-goods", is_active=True)
    db.session.add_all([seller, other_seller, category])
    db.session.commit()
    category_id = category.id

    assert client.post(
        "/api/v1/auth/login",
        json={"email": seller.email, "password": "password123"},
    ).status_code == 200
    created = client.post(
        "/api/v1/seller/products",
        json={
            "name": "API seller apples",
            "description": "Crisp local apples.",
            "category_id": category_id,
            "price": "4.25",
            "stock_quantity": 9,
            "original_locale": "en_US",
        },
    )
    assert created.status_code == 201
    product_data = created.get_json()["data"]
    assert product_data["moderation_status"] == "pending"
    assert product_data["is_available"] is False
    product_id = product_data["id"]
    assert client.get("/api/v1/seller/products").get_json()["data"][0]["id"] == product_id

    assert client.patch(
        f"/api/v1/seller/products/{product_id}",
        json={
            "name": "Updated seller apples",
            "description": "Updated crisp local apples.",
            "category_id": category_id,
            "price": "4.50",
            "stock_quantity": 8,
            "original_locale": "en_US",
        },
    ).status_code == 200

    client.post(
        "/api/v1/auth/logout",
        json={},
    )
    assert client.post(
        "/api/v1/auth/login",
        json={"email": other_seller.email, "password": "password123"},
    ).status_code == 200
    assert client.patch(
        f"/api/v1/seller/products/{product_id}",
        json={
            "name": "Takeover",
            "description": "Should not be allowed.",
            "category_id": category_id,
            "price": "1.00",
            "stock_quantity": 1,
            "original_locale": "en_US",
        },
    ).status_code == 404


def test_api_registration_requires_otp_and_supports_session_auth(client, app):
    client.application.config.update(
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    with patch("app.routes.auth.secrets.randbelow", return_value=456789), patch(
        "app.routes.auth.queue_registration_code"
    ):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "email": "api-customer@example.com",
                "role": "customer",
                "full_name": "API Customer",
                "phone": "01234567890",
                "password": "password123",
            },
        )
        assert response.status_code == 202
        with app.app_context():
            assert db.session.query(User).filter_by(email="api-customer@example.com").first() is None
            challenge = db.session.query(RegistrationChallenge).one()
            assert challenge.code_hash != "456789"

        invalid = client.post("/api/v1/auth/register/verify", json={"code": "000000"})
        assert invalid.status_code == 400
        verified = client.post("/api/v1/auth/register/verify", json={"code": "456789"})
    assert verified.status_code == 201
    assert verified.get_json()["data"]["role"] == "customer"

    login = client.post(
        "/api/v1/auth/login",
        json={"email": "api-customer@example.com", "password": "password123"},
    )
    assert login.status_code == 200
    assert client.get("/api/v1/auth/me").get_json()["data"]["email"] == "api-customer@example.com"
    assert client.post("/api/v1/auth/logout").status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401


def test_api_registration_can_create_pending_seller(client, app):
    client.application.config.update(
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    with patch("app.routes.auth.secrets.randbelow", return_value=321654), patch(
        "app.routes.auth.queue_registration_code"
    ):
        started = client.post(
            "/api/v1/auth/register",
            json={
                "email": "api-seller@example.com",
                "role": "seller",
                "full_name": "API Seller",
                "phone": "01234567890",
                "store_name": "API Store",
                "password": "password123",
            },
        )
        assert started.status_code == 202
        created = client.post("/api/v1/auth/register/verify", json={"code": "321654"})
    assert created.status_code == 201
    with app.app_context():
        seller = db.session.query(User).filter_by(email="api-seller@example.com").one()
        assert seller.role == "seller"
        assert seller.seller_profile.approval_status == "pending"


def test_api_admin_signin_requires_one_time_email_code(client, app, monkeypatch):
    client.application.config.update(
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    admin = User(email="api-admin@example.com", role="admin")
    admin.set_password("admin-password")
    db.session.add(admin)
    db.session.commit()
    queued = []
    monkeypatch.setattr("app.routes.auth.secrets.randbelow", lambda _limit: 246810)
    monkeypatch.setattr(
        "app.routes.auth.queue_admin_login_code",
        lambda email, code, **_kwargs: queued.append((email, code)),
    )

    requested = client.post(
        "/api/v1/auth/admin/code", json={"email": "api-admin@example.com"}
    )
    assert requested.status_code == 202
    with app.app_context():
        challenge = db.session.query(AdminLoginChallenge).one()
        assert challenge.code_hash != "246810"
    assert queued == [("api-admin@example.com", "246810")]

    password_login = client.post(
        "/api/v1/auth/login",
        json={"email": "api-admin@example.com", "password": "admin-password"},
    )
    assert password_login.status_code == 401
    verified = client.post("/api/v1/auth/admin/verify", json={"code": "246810"})
    assert verified.status_code == 200
    assert verified.get_json()["data"]["role"] == "admin"
    replay = client.post("/api/v1/auth/admin/verify", json={"code": "246810"})
    assert replay.status_code == 400


def test_api_admin_can_manage_categories_users_and_moderate_reviews(client, app, monkeypatch):
    client.application.config.update(
        WTF_CSRF_ENABLED=False,
        BREVO_API_KEY="test-key",
        MAIL_DEFAULT_SENDER="noreply@example.com",
    )
    admin = User(email="api-ops-admin@example.com", role="admin")
    admin.set_password("admin-password")
    customer = User(email="api-ops-customer@example.com", role="customer")
    customer.set_password("password123")
    customer.customer_profile = CustomerProfile(full_name="Review Customer", phone="01234567890")
    category = Category(name="Moderation goods", slug="moderation-goods", is_active=True)
    product = Product(
        category=category, name="Review item", slug="moderation-review-item",
        description="Review target", price=Decimal("6.00"), is_available=True,
    )
    db.session.add_all([admin, customer, category, product])
    db.session.flush()
    review = Review(
        product_id=product.id, user_id=customer.id, rating=5,
        author_name="Review Customer", status="pending",
    )
    db.session.add(review)
    db.session.commit()
    review_id, customer_id = review.id, customer.id
    monkeypatch.setattr("app.routes.auth.secrets.randbelow", lambda _limit: 135790)
    monkeypatch.setattr("app.routes.auth.queue_admin_login_code", lambda *_args, **_kwargs: None)

    assert client.post(
        "/api/v1/auth/admin/code", json={"email": admin.email}
    ).status_code == 202
    assert client.post("/api/v1/auth/admin/verify", json={"code": "135790"}).status_code == 200
    created = client.post(
        "/api/v1/admin/categories", json={"name": "Garden", "slug": "api-garden"}
    )
    assert created.status_code == 201
    category_id = created.get_json()["data"]["id"]
    assert client.patch(
        f"/api/v1/admin/categories/{category_id}",
        json={"description": "Updated through API"},
    ).status_code == 200

    deactivated = client.patch(
        f"/api/v1/admin/users/{customer_id}", json={"is_active": False}
    )
    assert deactivated.status_code == 200
    assert deactivated.get_json()["data"]["is_active"] is False
    moderated = client.patch(
        f"/api/v1/admin/reviews/{review_id}",
        json={"status": "approved", "moderation_note": "Verified"},
    )
    assert moderated.status_code == 200
    assert moderated.get_json()["data"]["status"] == "approved"
    assert client.delete(f"/api/v1/admin/categories/{category_id}").status_code == 200
