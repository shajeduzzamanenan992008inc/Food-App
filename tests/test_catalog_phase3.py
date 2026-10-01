from decimal import Decimal
from io import BytesIO

from app.extensions import db
from app.models import (
    AdminProfile, Category, Product, ProductTranslation, ProductVariant,
    SellerProfile, User,
)


def create_seller_and_product(app, *, locale="en_US", translations=()):
    seller = User(email="phase3-seller@example.com", role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name="Phase 3 Store", contact_name="Store Owner", phone="01234567890",
        approval_status="approved",
    )
    category = Category(name="Phase Three", slug="phase-three", is_active=True)
    product = Product(
        seller=seller,
        category=category,
        name="Roasted chickpeas",
        slug="roasted-chickpeas",
        description="A crunchy original description.",
        price=Decimal("8.50"),
        stock_quantity=4,
        original_locale=locale,
        moderation_status="approved",
        is_available=True,
    )
    for translation in translations:
        product.translations.append(translation)
    with app.app_context():
        db.session.add_all([seller, category, product])
        db.session.commit()
        return seller.id, product.id


def test_seller_product_upload_is_submitted_for_admin_review(client, app, monkeypatch):
    client.application.config["WTF_CSRF_ENABLED"] = False
    seller = User(email="submit-seller@example.com", role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name="Submit Store", contact_name="Store Owner", phone="01234567890",
        approval_status="approved",
    )
    category = Category(name="Fresh goods", slug="fresh-goods", is_active=True)
    with app.app_context():
        db.session.add_all([seller, category])
        db.session.commit()
        seller_id = seller.id
        category_id = category.id
    assert client.post(
        "/auth/login", data={"email": "submit-seller@example.com", "password": "password123"}
    ).status_code == 302

    scanned_url = "https://cdn.example.test/products/phase3-clean.png"
    monkeypatch.setattr("app.routes.seller.store_catalog_image", lambda upload: scanned_url)
    response = client.post(
        "/seller/products/new",
        data={
            "name": "Fresh mango",
            "slug": "fresh-mango",
            "category_id": str(category_id),
            "original_locale": "bn_BD",
            "price": "12.50",
            "discount_price": "",
            "stock_quantity": "9",
            "description": "মিষ্টি আম",
            "translation_name_en_US": "Sweet mango",
            "translation_description_en_US": "A ripe, sweet mango.",
            "image_file": (BytesIO(b"image-test"), "fresh.png"),
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 302
    with app.app_context():
        product = db.session.query(Product).filter_by(slug="fresh-mango").one()
        assert product.seller_id == seller_id
        assert product.image == scanned_url
        assert product.stock_quantity == 9
        assert product.moderation_status == "pending"
        assert product.is_available is False
        assert product.translations[0].locale == "en_US"
        assert product.translations[0].name == "Sweet mango"


def test_admin_approval_publishes_listing_and_missing_translation_shows_source_language(client, app, login_admin):
    client.application.config["WTF_CSRF_ENABLED"] = False
    seller = User(email="review-seller@example.com", role="seller")
    seller.set_password("password123")
    seller.seller_profile = SellerProfile(
        store_name="Review Store", contact_name="Store Owner", phone="01234567890",
        approval_status="approved",
    )
    admin = User(email="review-admin@example.com", role="admin")
    admin.set_password("password123")
    admin.admin_profile = AdminProfile(full_name="Review Admin")
    category = Category(name="Review foods", slug="review-foods", is_active=True)
    product = Product(
        seller=seller, category=category, name="Mango", slug="review-mango",
        description="Sweet fruit", price=Decimal("20.00"), stock_quantity=3,
        original_locale="bn_BD", moderation_status="pending", is_available=False,
    )
    with app.app_context():
        db.session.add_all([seller, admin, category, product])
        db.session.commit()
        product_id = product.id

    admin_client = app.test_client()
    assert login_admin(admin_client, "review-admin@example.com").status_code == 302
    assert admin_client.post(
        f"/admin/products/{product_id}/review", data={"decision": "approved", "review_note": "Ready"}
    ).status_code == 302
    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product.moderation_status == "approved"
        assert product.is_available is True

    fallback = client.get("/food/review-mango")
    assert fallback.status_code == 200
    assert b"Mango" in fallback.data
    assert "Original language: বাংলা".encode() in fallback.data


def test_product_translation_search_and_partial_translation_fallback(client, app):
    translation = ProductTranslation(locale="ar", name="حمص", description="")
    _seller_id, product_id = create_seller_and_product(app, translations=(translation,))
    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product.localized_name("ar") == "حمص"
        assert product.localized_description("ar") == "A crunchy original description."
        assert product.needs_original_language_label("ar", "name") is False
        assert product.needs_original_language_label("ar", "description") is True

    assert client.post("/language", data={"locale": "ar", "next": "/food/roasted-chickpeas"}).status_code == 302
    page = client.get("/food/roasted-chickpeas")
    assert page.status_code == 200
    assert "حمص".encode() in page.data
    assert "اللغة الأصلية: English (US)".encode() in page.data
    search = client.get("/search?q=%D8%AD%D9%85%D8%B5")
    assert "حمص".encode() in search.data


def test_seller_variant_stock_changes_are_owner_scoped(client, app):
    client.application.config["WTF_CSRF_ENABLED"] = False
    seller_id, product_id = create_seller_and_product(app)
    with app.app_context():
        product = db.session.get(Product, product_id)
        seller_email = db.session.get(User, seller_id).email
        assert product.available_stock == 4

    assert client.post("/auth/login", data={"email": seller_email, "password": "password123"}).status_code == 302
    assert client.post(
        f"/seller/products/{product_id}/variants",
        data={"sku": "CHICKPEA-250", "option_name": "Pack", "option_value": "250 g", "stock_quantity": "6", "price": "9.00"},
    ).status_code == 302
    with app.app_context():
        product = db.session.get(Product, product_id)
        variant = product.variants[0]
        variant_id = variant.id
        assert product.available_stock == 6

    assert client.post(
        f"/seller/products/{product_id}/variants/{variant_id}/stock", data={"stock_quantity": "11"}
    ).status_code == 302
    with app.app_context():
        assert db.session.get(Product, product_id).available_stock == 11

    assert client.post(
        f"/seller/products/{product_id}/variants/{variant_id}/toggle"
    ).status_code == 302
    with app.app_context():
        product = db.session.get(Product, product_id)
        assert product.variants[0].is_active is False
        assert product.available_stock == 4
