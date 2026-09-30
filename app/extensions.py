from sqlalchemy import event
from sqlalchemy.engine import Engine

from flask_wtf import CSRFProtect
from flask_babel import Babel
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy


csrf = CSRFProtect()
babel = Babel()
db = SQLAlchemy()
migrate = Migrate()


@event.listens_for(Engine, "connect")
def configure_sqlite_connection(connection, _record):
    """Keep SQLite foreign keys and lock waits enabled on every connection."""
    if connection.__class__.__module__.startswith("sqlite3"):
        cursor = connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()
