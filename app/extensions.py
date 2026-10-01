from sqlalchemy import event
from sqlalchemy.engine import Engine

from flask_wtf import CSRFProtect
from flask_babel import Babel
from flask_login import LoginManager
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


csrf = CSRFProtect()
babel = Babel()
login_manager = LoginManager()
login_manager.login_view = "auth.login"
db = SQLAlchemy()
migrate = Migrate()


@login_manager.user_loader
def load_user(user_id):
    """Load only active accounts whose authentication version is current."""
    from flask import session

    from .models import User

    try:
        user = db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None
    if (
        not user
        or not user.is_active
        or user.auth_version != session.get("auth_version")
    ):
        return None
    return user


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(connection, _record):
    """Keep SQLite foreign keys and lock waits enabled on every connection."""
    if connection.__class__.__module__.startswith("sqlite3"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
