import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from app import create_app
from app.config import TestingConfig
from app.extensions import db
from app.models import AuditEvent, User


def csrf_off(client):
    client.application.config["WTF_CSRF_ENABLED"] = False


@pytest.fixture()
def file_app(tmp_path):
    """An app that uses a real on-disk SQLite file for backup/restore checks."""
    config = type(
        "FileConfig",
        (TestingConfig,),
        {
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path / 'app.db'}",
            "ADMIN_EMAIL": None,
        },
    )
    app = create_app(config)
    with app.app_context():
        db.drop_all()
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def test_login_writes_an_audit_event(client, app):
    csrf_off(client)
    user = User(email="audit@example.com", role="customer")
    user.set_password("password123")
    with app.app_context():
        db.session.add(user)
        db.session.commit()
    assert client.post(
        "/auth/login", data={"email": "audit@example.com", "password": "password123"}
    ).status_code == 302
    with app.app_context():
        event = db.session.query(AuditEvent).filter_by(action="auth.login").one()
        assert event.actor_email == "audit@example.com"
        assert event.actor_role == "customer"
        assert event.ip_hash and len(event.ip_hash) == 64
        assert "127.0.0.1" not in event.ip_hash


def test_failed_admin_code_writes_a_denial_event(client, app):
    csrf_off(client)
    admin = User(email="audit-admin@example.com", role="admin")
    admin.set_password("unused-password")
    with app.app_context():
        db.session.add(admin)
        db.session.commit()
    client.application.config.update(
        BREVO_API_KEY="test-key", MAIL_DEFAULT_SENDER="noreply@example.com"
    )
    with patch("app.routes.auth.queue_admin_login_code"):
        client.post("/admin/login", data={"email": "audit-admin@example.com"})
    client.post("/auth/verify-admin-login", data={"code": "000000"})
    with app.app_context():
        event = db.session.query(AuditEvent).filter_by(action="auth.admin_login_denied").one()
        assert event.target_id == "audit-admin@example.com"


def test_backup_and_restore_round_trip(file_app, tmp_path):
    from app.services.backup import backup_database, database_size_bytes, restore_database

    with file_app.app_context():
        user = User(email="backup@example.com", role="customer")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        assert database_size_bytes() > 0

        backup_path = tmp_path / "backup.sqlite3"
        backup_database(backup_path)
        assert backup_path.exists()

        db.session.delete(user)
        db.session.commit()
        assert db.session.query(User).filter_by(email="backup@example.com").count() == 0

        restore_database(backup_path)
        assert db.session.query(User).filter_by(email="backup@example.com").count() == 1


def test_restore_rejects_an_invalid_backup(file_app, tmp_path):
    from app.services.backup import restore_database

    bad = tmp_path / "not-a-database.sqlite3"
    bad.write_bytes(b"this is not a sqlite database")
    with file_app.app_context():
        with pytest.raises(RuntimeError):
            restore_database(bad)


def test_database_ceiling_is_enforced(file_app):
    from app.services.backup import assert_within_ceiling

    with file_app.app_context():
        user = User(email="ceiling@example.com", role="customer")
        user.set_password("password123")
        db.session.add(user)
        db.session.commit()
        file_app.config["MAX_DATABASE_BYTES"] = 400 * 1024 * 1024
        assert assert_within_ceiling() > 0
        file_app.config["MAX_DATABASE_BYTES"] = 1
        with pytest.raises(RuntimeError):
            assert_within_ceiling()


def test_production_readiness_reviews_configuration(app):
    from app.services.review import production_readiness

    with app.app_context():
        app.config.update(
            SECRET_KEY="short", SESSION_COOKIE_SECURE=False, PUBLIC_BASE_URL="",
            BREVO_API_KEY=None, MAIL_DEFAULT_SENDER=None,
            SQLALCHEMY_DATABASE_URI="sqlite:///:memory:", ADMIN_EMAIL=None,
            INVOICE_FONT_PATH="", CATALOG_MEDIA_BUCKET=None,
            CATALOG_MEDIA_PUBLIC_BASE_URL="", CATALOG_VIRUS_SCANNER="definitely-not-installed",
        )
        ok, issues = production_readiness(app.config)
        assert ok is False
        assert any("SECRET_KEY" in issue for issue in issues)
        assert any("PostgreSQL" in issue for issue in issues)

        app.config.update(
            SECRET_KEY="x" * 40, SESSION_COOKIE_SECURE=True,
            PUBLIC_BASE_URL="https://nexhaat.example", BREVO_API_KEY="key",
            MAIL_DEFAULT_SENDER="noreply@nexhaat.example",
            SQLALCHEMY_DATABASE_URI="postgresql+psycopg://user:pass@host/nexhaat",
            ADMIN_EMAIL="admin@nexhaat.example", INVOICE_FONT_PATH=str(Path(__file__)),
            CATALOG_MEDIA_BUCKET="media",
            CATALOG_MEDIA_PUBLIC_BASE_URL="https://cdn.nexhaat.example",
            CATALOG_VIRUS_SCANNER=sys.executable,
        )
        ok, issues = production_readiness(app.config)
        assert ok is True
        assert issues == []
