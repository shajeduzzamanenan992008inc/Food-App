from decimal import Decimal

from app.extensions import db
from app.models import Category, Product, SellerProfile, User


def add_catalog():
    category = Category(name="Pizza", slug="pizza", is_active=True)
    inactive = Category(name="Hidden", slug="hidden", is_active=False)
    db.session.add_all([category, inactive])
    db.session.flush()
    db.session.add_all(
        [
            Product(
                category=category,
                name="Garden Pizza",
                slug="garden-pizza",
                description="Fresh basil and tomato",
                price=Decimal("12.50"),
                is_available=True,
            ),
            Product(
                category=category,
                name="Unavailable Pizza",
                slug="unavailable-pizza",
                description="Not currently available",
                price=Decimal("10.00"),
                is_available=False,
            ),
            Product(
                category=inactive,
                name="Hidden Pizza",
                slug="hidden-pizza",
                description="Hidden",
                price=Decimal("10.00"),
                is_available=True,
            ),
        ]
    )
    db.session.commit()


def test_catalog_filters_inactive_and_unavailable(client, app):
    add_catalog()
    response = client.get("/menu")
    assert b"Garden Pizza" in response.data
    assert b"Unavailable Pizza" not in response.data
    assert b"Hidden Pizza" not in response.data


def test_product_detail_category_and_search(client, app):
    add_catalog()
    assert client.get("/food/garden-pizza").status_code == 200
    assert client.get("/category/pizza").status_code == 200
    response = client.get("/search?q=basil")
    assert b"Garden Pizza" in response.data
    assert client.get("/food/unavailable-pizza").status_code == 404


def test_missing_catalog_resources_return_404(client):
    assert client.get("/food/nope").status_code == 404
    assert client.get("/category/nope").status_code == 404


def test_slugs_are_unique(app):
    first = Category(name="First", slug="same")
    second = Category(name="Second", slug="same")
    with app.app_context():
        db.session.add_all([first, second])
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()
            assert True
        else:
            assert False, "duplicate category slugs must be rejected"


def test_seller_cannot_read_or_change_another_sellers_product(client, app):
    with app.app_context():
        category = Category(name="Seller scoped", slug="seller-scoped", is_active=True)
        seller_a = User(email="seller-a@example.com", role="seller")
        seller_a.set_password("password123")
        seller_a.seller_profile = SellerProfile(
            store_name="Seller A", contact_name="Owner A", phone="01234567890", approval_status="approved"
        )
        seller_b = User(email="seller-b@example.com", role="seller")
        seller_b.set_password("password123")
        seller_b.seller_profile = SellerProfile(
            store_name="Seller B", contact_name="Owner B", phone="01987654321", approval_status="approved"
        )
        db.session.add_all([category, seller_a, seller_b])
        db.session.flush()
        product = Product(
            seller_id=seller_b.id,
            category_id=category.id,
            name="Private seller product",
            slug="private-seller-product",
            description="Belongs to a different seller",
            price=Decimal("9.50"),
            stock_quantity=5,
        )
        db.session.add(product)
        db.session.commit()
        product_id = product.id

    assert client.post("/auth/login", data={"email": "seller-a@example.com", "password": "password123"}).status_code == 302
    assert client.get(f"/seller/products/{product_id}/edit").status_code == 404
    assert client.get(f"/seller/products/{product_id}/variants").status_code == 404
    assert client.post(f"/seller/products/{product_id}/archive").status_code == 404
    assert client.post(
        f"/seller/products/{product_id}/variants",
        data={"sku": "TAKEOVER", "option_name": "Size", "option_value": "Large", "stock_quantity": "50"},
    ).status_code == 404

    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product.is_available is True
        assert product.stock_quantity == 5
        assert product.moderation_status == "approved"
        assert product.variants == []
