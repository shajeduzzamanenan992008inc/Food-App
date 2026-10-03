from decimal import Decimal

from app.extensions import db
from app.models import Category, CustomerProfile, Order, OrderItem, Product, Review, User


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


def make_customer(email="reviewer@example.com", name="Review Writer"):
    user = User(email=email, role="customer")
    user.set_password("password123")
    user.customer_profile = CustomerProfile(full_name=name, phone="01234567890")
    db.session.add(user)
    db.session.commit()
    return user


def make_product(slug="review-pizza"):
    category = Category(name="Pizza", slug="pizza", is_active=True)
    product = Product(
        category=category,
        name="Review Pizza",
        slug=slug,
        description="A testable pizza",
        price=Decimal("10.00"),
        is_available=True,
    )
    db.session.add(product)
    db.session.commit()
    return product


def make_order(user, product, status="delivered", number="RVW-1"):
    order = Order(
        order_number=number,
        user_id=user.id,
        customer_name="Review Writer",
        phone="01234567890",
        address="12 Test Street",
        total=Decimal("10.00"),
        status=status,
    )
    order.items.append(
        OrderItem(
            product_id=product.id,
            product_name=product.name,
            price=Decimal("10.00"),
            quantity=1,
            subtotal=Decimal("10.00"),
        )
    )
    db.session.add(order)
    db.session.commit()
    return order


def add_review(product, user, order, rating=5, comment="Body", status="pending", author="Review Writer"):
    review = Review(
        product_id=product.id,
        user_id=user.id,
        order_id=order.id,
        rating=rating,
        comment=comment,
        author_name=author,
        status=status,
    )
    db.session.add(review)
    db.session.commit()
    return review


def test_customer_reviews_a_delivered_purchase(client, app):
    csrf_off(client)
    with app.app_context():
        user = make_customer()
        product = make_product()
        make_order(user, product)
        product_id, product_slug = product.id, product.slug

    client.post("/auth/login", data={"email": "reviewer@example.com", "password": "password123"})
    response = client.post(
        f"/food/{product_slug}/reviews", data={"rating": "5", "comment": "Loved it"}
    )
    assert response.status_code == 302
    with app.app_context():
        review = db.session.query(Review).one()
        assert review.product_id == product_id
        assert review.rating == 5
        assert review.status == "pending"
        assert review.author_name == "Review Writer"
        assert review.comment == "Loved it"


def test_review_requires_a_delivered_order(client, app):
    csrf_off(client)
    with app.app_context():
        user = make_customer(email="pending@example.com")
        product = make_product(slug="pending-pizza")
        make_order(user, product, status="pending", number="RVW-2")
        product_slug = product.slug

    client.post("/auth/login", data={"email": "pending@example.com", "password": "password123"})
    response = client.post(
        f"/food/{product_slug}/reviews",
        data={"rating": "4", "comment": "Too soon"},
        follow_redirects=True,
    )
    assert b"after your order is delivered" in response.data
    with app.app_context():
        assert db.session.query(Review).count() == 0


def test_duplicate_review_is_rejected(client, app):
    csrf_off(client)
    with app.app_context():
        user = make_customer(email="dup@example.com")
        product = make_product(slug="dup-pizza")
        make_order(user, product, number="RVW-3")
        product_slug = product.slug

    client.post("/auth/login", data={"email": "dup@example.com", "password": "password123"})
    first = client.post(f"/food/{product_slug}/reviews", data={"rating": "5", "comment": "First"})
    assert first.status_code == 302
    client.post(f"/food/{product_slug}/reviews", data={"rating": "1", "comment": "Second"})
    with app.app_context():
        assert db.session.query(Review).count() == 1


def test_guest_cannot_submit_a_review(client, app):
    csrf_off(client)
    with app.app_context():
        user = make_customer(email="guest-target@example.com")
        product = make_product(slug="guest-pizza")
        make_order(user, product, number="RVW-4")
        product_slug = product.slug

    response = client.post(
        f"/food/{product_slug}/reviews", data={"rating": "5", "comment": "No login"}
    )
    assert response.status_code == 302
    with app.app_context():
        assert db.session.query(Review).count() == 0


def test_approved_review_appears_on_product_page(client, app):
    with app.app_context():
        product = make_product(slug="public-pizza")
        user = make_customer(email="public@example.com")
        order = make_order(user, product, number="RVW-5")
        add_review(
            product, user, order, rating=4, comment="Great crust",
            status="approved", author="Public Fan",
        )
        product_slug = product.slug

    page = client.get(f"/food/{product_slug}").get_data(as_text=True)
    assert "Public Fan" in page
    assert "Great crust" in page


def test_pending_review_is_hidden_until_moderated(client, app):
    with app.app_context():
        product = make_product(slug="hidden-pizza")
        user = make_customer(email="hidden@example.com")
        order = make_order(user, product, number="RVW-6")
        add_review(
            product, user, order, rating=3, comment="Awaiting",
            status="pending", author="Hidden Fan",
        )
        product_slug = product.slug

    page = client.get(f"/food/{product_slug}").get_data(as_text=True)
    assert "Hidden Fan" not in page
    assert "Awaiting" not in page


def test_admin_moderates_a_review(client, app, login_admin):
    csrf_off(client)
    with app.app_context():
        admin = User(email="review-admin@example.com", role="admin")
        admin.set_password("unused-password")
        product = make_product(slug="mod-pizza")
        user = make_customer(email="mod@example.com")
        order = make_order(user, product, number="RVW-7")
        review = add_review(product, user, order, rating=5, comment="Moderate me", author="Mod Fan")
        db.session.add(admin)
        db.session.commit()
        review_id = review.id

    assert login_admin(client, "review-admin@example.com").status_code == 302
    response = client.post(
        f"/admin/reviews/{review_id}/moderate", data={"decision": "approved"}
    )
    assert response.status_code == 302
    with app.app_context():
        stored = db.session.get(Review, review_id)
        assert stored.status == "approved"
        assert stored.moderated_at is not None


def test_admin_cannot_moderate_an_already_reviewed_entry(client, app, login_admin):
    csrf_off(client)
    with app.app_context():
        admin = User(email="review-admin2@example.com", role="admin")
        admin.set_password("unused-password")
        product = make_product(slug="mod2-pizza")
        user = make_customer(email="mod2@example.com")
        order = make_order(user, product, number="RVW-8")
        review = add_review(product, user, order, status="approved", author="Done Fan")
        db.session.add(admin)
        db.session.commit()
        review_id = review.id

    login_admin(client, "review-admin2@example.com")
    assert client.post(
        f"/admin/reviews/{review_id}/moderate", data={"decision": "rejected"}
    ).status_code == 404


def test_api_lists_approved_reviews(client, app):
    with app.app_context():
        product = make_product(slug="api-pizza")
        user = make_customer(email="api@example.com")
        order = make_order(user, product, number="RVW-9")
        add_review(
            product, user, order, rating=5, comment="API good",
            status="approved", author="Api Fan",
        )
        product_id = product.id

    response = client.get(f"/api/v1/products/{product_id}/reviews")
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["summary"] == {"count": 1, "average": 5.0}
    assert body["data"]["reviews"][0]["comment"] == "API good"


def test_api_review_requires_customer_login(client, app):
    with app.app_context():
        product = make_product(slug="api-auth-pizza")
        product_id = product.id

    response = client.post(f"/api/v1/products/{product_id}/reviews", json={"rating": 5})
    assert response.status_code == 401
    assert response.get_json()["error"]["code"] == "UNAUTHENTICATED"


def test_api_review_rejects_ineligible_purchase(client, app):
    csrf_off(client)
    with app.app_context():
        make_customer(email="api-ineligible@example.com")
        product = make_product(slug="api-ineligible-pizza")
        product_id = product.id

    client.post(
        "/auth/login", data={"email": "api-ineligible@example.com", "password": "password123"}
    )
    response = client.post(
        f"/api/v1/products/{product_id}/reviews", json={"rating": 5, "comment": "no order"}
    )
    assert response.status_code == 422
    assert response.get_json()["error"]["code"] == "REVIEW_NOT_ALLOWED"
