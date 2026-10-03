import json
from decimal import Decimal

from app.api.responses import (
    created_response,
    error_response,
    paginated_response,
    success_response,
)
from app.api.serializers import category_to_dict, product_to_dict
from app.extensions import db
from app.models import Category, Product


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
