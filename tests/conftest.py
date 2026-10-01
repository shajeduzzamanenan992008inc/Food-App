import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db


@pytest.fixture()
def app():
    app = create_app(TestingConfig)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture
def login_admin(monkeypatch):
    """Complete the Admin OTP flow with a deterministic test code."""
    monkeypatch.setattr("app.routes.auth.queue_admin_login_code", lambda *args, **kwargs: None)
    monkeypatch.setattr("app.routes.auth.secrets.randbelow", lambda _limit: 123456)

    def sign_in(client, email):
        client.application.config.update(
            WTF_CSRF_ENABLED=False,
            BREVO_API_KEY="test-key",
            MAIL_DEFAULT_SENDER="noreply@example.com",
        )
        response = client.post("/admin/login", data={"email": email})
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/auth/verify-admin-login")
        response = client.post("/auth/verify-admin-login", data={"code": "123456"})
        assert response.status_code == 302
        assert response.headers["Location"].endswith("/admin")
        return response

    return sign_in
