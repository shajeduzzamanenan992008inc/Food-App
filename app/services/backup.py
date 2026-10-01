"""Database size limits plus simple, verifiable backup and restore helpers."""

import shutil
import sqlite3
import subprocess
from pathlib import Path

from flask import current_app
from sqlalchemy import text

from ..extensions import db


def is_sqlite():
    return current_app.config.get("SQLALCHEMY_DATABASE_URI", "").startswith("sqlite")


def _sqlite_path():
    url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    if not url.startswith("sqlite") or "///" not in url:
        return None
    return Path(url.split("///", 1)[1])


def database_ceiling_bytes():
    return int(current_app.config.get("MAX_DATABASE_BYTES", 400 * 1024 * 1024))


def database_size_bytes():
    path = _sqlite_path()
    if path is not None:
        return path.stat().st_size if path.exists() else 0
    size = db.session.scalar(text("SELECT pg_database_size(current_database())"))
    return int(size or 0)


def assert_within_ceiling():
    """Raise when the database has grown past the configured ceiling."""
    size = database_size_bytes()
    ceiling = database_ceiling_bytes()
    if size > ceiling:
        raise RuntimeError(f"Database size {size} bytes exceeds the ceiling of {ceiling} bytes.")
    return size


def _verify_sqlite_file(path):
    path = Path(path)
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError("Backup file is missing or empty.")
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if not integrity or integrity[0] != "ok":
                raise RuntimeError("Backup failed the SQLite integrity check.")
            tables = {
                row[0]
                for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
            }
            if "users" not in tables:
                raise RuntimeError("Backup does not contain the expected application tables.")
        finally:
            connection.close()
    except sqlite3.DatabaseError as error:
        raise RuntimeError("Backup is not a readable SQLite database.") from error


def backup_database(destination):
    """Write a consistent backup and verify it before returning its path."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if is_sqlite():
        source = _sqlite_path()
        if source is None or not source.exists():
            raise RuntimeError("The SQLite database file does not exist yet.")
        target = sqlite3.connect(str(destination))
        try:
            source_connection = sqlite3.connect(str(source))
            try:
                source_connection.backup(target)
            finally:
                source_connection.close()
        finally:
            target.close()
        _verify_sqlite_file(destination)
    else:
        _pg_backup(destination)
    return destination


def restore_database(source):
    """Restore a verified backup over the live database."""
    source = Path(source)
    if not source.is_file():
        raise FileNotFoundError(f"Backup file not found: {source}")
    if is_sqlite():
        _verify_sqlite_file(source)
        target = _sqlite_path()
        if target is None:
            raise RuntimeError("SQLite restore target is not configured.")
        db.session.remove()
        db.engine.dispose()
        shutil.copyfile(source, target)
        _verify_sqlite_file(target)
    else:
        _pg_restore(source)
    return source


def _database_url_for_tools():
    url = current_app.config.get("SQLALCHEMY_DATABASE_URI", "")
    return url.replace("postgresql+psycopg://", "postgresql://", 1).replace(
        "postgres://", "postgresql://", 1
    )


def _pg_backup(destination):
    executable = shutil.which("pg_dump")
    if not executable:
        raise RuntimeError("pg_dump is not available in this runtime for PostgreSQL backups.")
    result = subprocess.run(
        [executable, "--no-owner", "--file", str(destination), _database_url_for_tools()],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("pg_dump failed; the backup was not written.")


def _pg_restore(source):
    executable = shutil.which("psql")
    if not executable:
        raise RuntimeError("psql is not available in this runtime for PostgreSQL restores.")
    result = subprocess.run(
        [executable, "-v", "ON_ERROR_STOP=1", "-f", str(source), _database_url_for_tools()],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError("psql restore failed; review the server logs and retry.")
