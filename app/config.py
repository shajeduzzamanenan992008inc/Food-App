import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Config:
    APP_NAME = "NexHaat"
    BABEL_DEFAULT_LOCALE = "en_US"
    BABEL_DEFAULT_TIMEZONE = "Asia/Dhaka"
    BABEL_TRANSLATION_DIRECTORIES = "translations"
    ENVIRONMENT = os.getenv("APP_ENV", "development").lower()
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")
    _database_url = os.getenv("DATABASE_URL")
    if _database_url and _database_url.startswith("postgres://"):
        _database_url = _database_url.replace("postgres://", "postgresql+psycopg://", 1)
    if _database_url and _database_url.startswith("postgresql://"):
        _database_url = _database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    if _database_url and _database_url.startswith("sqlite:///"):
        _sqlite_path = Path(_database_url.removeprefix("sqlite:///"))
        if not _sqlite_path.is_absolute():
            _database_url = f"sqlite:///{(BASE_DIR / _sqlite_path).resolve()}"
    SQLALCHEMY_DATABASE_URI = _database_url or f"sqlite:///{BASE_DIR / 'instance' / 'food_ordering.sqlite3'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    if (_database_url or "").startswith("sqlite:") or not _database_url:
        SQLALCHEMY_ENGINE_OPTIONS["connect_args"] = {"timeout": 30}
    else:
        SQLALCHEMY_ENGINE_OPTIONS.update(pool_recycle=1800, pool_size=5, max_overflow=10)
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "freshbite_session"
    SESSION_REFRESH_EACH_REQUEST = False
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 12
    SESSION_COOKIE_SECURE = os.getenv(
        "SESSION_COOKIE_SECURE",
        "true" if ENVIRONMENT == "production" else "false",
    ).lower() == "true"
    WTF_CSRF_TIME_LIMIT = 3600
    MAIL_TIMEOUT = int(os.getenv("MAIL_TIMEOUT", "15"))
    BREVO_API_KEY = os.getenv("BREVO_API_KEY")
    _mail_sender = os.getenv("MAIL_DEFAULT_SENDER")
    MAIL_DEFAULT_SENDER = _mail_sender if _mail_sender and "@" in _mail_sender else None
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
    PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip().rstrip("/")
    MAX_CONTENT_LENGTH = 4 * 1024 * 1024
    MAX_IMAGE_UPLOAD_BYTES = 2 * 1024 * 1024
    MAX_SEARCH_LENGTH = 100
    CATALOG_PAGE_SIZE = 48
    MIN_PASSWORD_LENGTH = 12 if ENVIRONMENT == "production" else 8
    MAX_PASSWORD_LENGTH = 128
    UPLOAD_FOLDER = str(BASE_DIR / "app" / "static" / "uploads" / "profiles")
    BRANDING_UPLOAD_FOLDER = str(BASE_DIR / "app" / "static" / "uploads" / "branding")
    PREFERRED_URL_SCHEME = "https" if ENVIRONMENT == "production" else "http"


class TestingConfig(Config):
    TESTING = True
    ENVIRONMENT = "testing"
    MIN_PASSWORD_LENGTH = 8
    SECRET_KEY = "test-secret"
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    WTF_CSRF_ENABLED = False
    ASYNC_ORDER_EMAILS = False


def get_config():
    return TestingConfig if os.getenv("FLASK_TESTING") == "1" else Config
