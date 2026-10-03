from decimal import Decimal

from sqlalchemy import select

from app.extensions import db
from app.models import Category, CustomerProfile, Product, User, WishlistItem


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


def make_customer(email="wish@example.com", name="Wish User"):
    user = User(email=email, role="customer")
    user.set_password("password123")
    user.customer_profile = CustomerProfile(full_name=name, phone="01234567890")
    db.session.add(user)
    db.session.commit()
    return user


def make_product(slug="wish-pizza"):
    category = db.session.scalar(select(Category).where(Category.slug == "pizza"))
    if category is None:
        category = Category(name="Pizza", slug="pizza", is_active=True)
        db.session.add(category)
        db.session.flush()
    product = Product(
        category=category, name="Wish Pizza", slug=slug,
        description="A pizza", price=Decimal("10.00"), is_available=True,
    )
    db.session.add(product)
    db.session.commit()
    return product


def login(client, email="wish@example.com"):
    client.post("/auth/login", data={"email": email, "password": "password123"})


def test_service_add_is_idempotent(app):
    with app.app_context():
        user = make_customer()
        product = make_product()
        from app.services.wishlist import add, count, has, products_for

        item, created = add(user, product)
        assert created is True
        assert has(user, product.id) is True

        again, created_again = add(user, product)
        assert created_again is False
        assert again.id == item.id
        assert count(user) == 1
        assert [p.id for p in products_for(user)] == [product.id]


def test_service_remove(app):
    with app.app_context():
        user = make_customer()
        product = make_product()
        from app.services.wishlist import add, count, remove

        add(user, product)
        assert remove(user, product.id) is True
        assert count(user) == 0
        assert remove(user, product.id) is False


def test_service_lists_saved_products(app):
    with app.app_context():
        user = make_customer()
        first = make_product(slug="first-wish")
        second = make_product(slug="second-wish")
        from app.services.wishlist import add, products_for

        add(user, first)
        add(user, second)
        slugs = {p.slug for p in products_for(user)}
        assert slugs == {"first-wish", "second-wish"}


def test_guest_is_redirected_from_wishlist_page(client):
    response = client.get("/wishlist")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_customer_can_add_and_remove_from_wishlist(client, app):
    csrf_off(client)
    with app.app_context():
        make_customer()
        product = make_product()
        product_id = product.id

    login(client)
    response = client.post(f"/wishlist/add/{product_id}")
    assert response.status_code == 302
    with app.app_context():
        assert db.session.query(WishlistItem).count() == 1

    page = client.get("/wishlist").get_data(as_text=True)
    assert "Wish Pizza" in page

    response = client.post(f"/wishlist/remove/{product_id}")
    assert response.status_code == 302
    with app.app_context():
        assert db.session.query(WishlistItem).count() == 0


def test_wishlist_page_shows_remove_control_for_saved_item(client, app):
    csrf_off(client)
    with app.app_context():
        make_customer()
        product = make_product(slug="saved-card")
        product_id = product.id

    login(client)
    client.post(f"/wishlist/add/{product_id}")
    page = client.get("/wishlist").get_data(as_text=True)
    assert f"/wishlist/remove/{product_id}" in page
    assert "wish-button--saved" in page


def test_product_page_toggles_save_state(client, app):
    csrf_off(client)
    with app.app_context():
        make_customer()
        product = make_product(slug="detail-save")
        product_id, product_slug = product.id, product.slug

    login(client)
    page = client.get(f"/food/{product_slug}").get_data(as_text=True)
    assert "Save to wishlist" in page

    client.post(f"/wishlist/add/{product_id}", data={"next": f"/food/{product_slug}"})
    page = client.get(f"/food/{product_slug}").get_data(as_text=True)
    assert "Saved" in page


def test_wishlist_add_ignores_external_next(client, app):
    csrf_off(client)
    with app.app_context():
        make_customer()
        product = make_product(slug="open-redirect")
        product_id = product.id

    login(client)
    response = client.post(
        f"/wishlist/add/{product_id}", data={"next": "https://evil.example/steal"}
    )
    assert response.status_code == 302
    assert "evil.example" not in response.headers["Location"]
    assert response.headers["Location"].endswith("/wishlist")


def test_wishlist_is_scoped_to_the_owner(client, app):
    csrf_off(client)
    with app.app_context():
        owner = make_customer(email="owner-wish@example.com")
        other = make_customer(email="other-wish@example.com")
        product = make_product(slug="scoped-wish")
        from app.services.wishlist import add

        add(owner, product)
        other_id = other.id

    login(client, "other-wish@example.com")
    page = client.get("/wishlist").get_data(as_text=True)
    assert "Wish Pizza" not in page
    with app.app_context():
        assert db.session.query(WishlistItem).filter_by(user_id=other_id).count() == 0


def test_api_wishlist_requires_customer_login(client, app):
    with app.app_context():
        product = make_product(slug="api-wish-auth")
        product_id = product.id

    assert client.get("/api/v1/wishlist").status_code == 401
    response = client.post("/api/v1/wishlist/items", json={"product_id": product_id})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_api_wishlist_add_list_remove(client, app):
    csrf_off(client)
    with app.app_context():
        make_customer(email="api-wish@example.com")
        product = make_product(slug="api-wish-item")
        product_id = product.id

    login(client, "api-wish@example.com")
    response = client.post("/api/v1/wishlist/items", json={"product_id": product_id})
    assert response.status_code == 201
    assert response.get_json()["data"]["saved"] is True

    listing = client.get("/api/v1/wishlist").get_json()
    assert listing["data"]["count"] == 1
    assert listing["data"]["products"][0]["slug"] == "api-wish-item"

    removed = client.delete(f"/api/v1/wishlist/items/{product_id}")
    assert removed.status_code == 200
    assert removed.get_json()["data"]["removed"] is True
    assert client.get("/api/v1/wishlist").get_json()["data"]["count"] == 0


def test_api_wishlist_rejects_unknown_product(client, app):
    csrf_off(client)
    with app.app_context():
        make_customer(email="api-missing@example.com")

    login(client, "api-missing@example.com")
    response = client.post("/api/v1/wishlist/items", json={"product_id": 999999})
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == "NOT_FOUND"