from pathlib import Path
import logging
import secrets
import zipfile
from urllib.parse import urlsplit

import click

from flask import Flask, g, render_template, session
from flask_babel import get_locale
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import inspect, text

from .config import get_config
from .extensions import babel, csrf, db, login_manager, migrate
from .i18n import SUPPORTED_LOCALES, get_request_locale


def create_app(config_object=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(config_object or get_config())
    if app.config.get("ENVIRONMENT") == "production":
        secret = app.config.get("SECRET_KEY") or ""
        if secret == "dev-only-change-me" or len(secret) < 32:
            raise RuntimeError("Set a random SECRET_KEY of at least 32 characters before starting in production.")
        # Trust only proxy-provided client and scheme headers. X-Host remains
        # untrusted so a client cannot poison externally generated host URLs.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    Path(app.instance_path).mkdir(parents=True, exist_ok=True)

    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    csrf.init_app(app)
    babel.init_app(app, locale_selector=get_request_locale)

    from .models import AdminProfile, AppSetting, CustomerProfile, User  # noqa: F401
    from .routes.auth import admin_login, auth_bp
    from .routes.main import main_bp
    from .routes.orders import orders_bp
    from .routes.portals import admin_bp, customer_bp, rider_bp
    from .routes.seller import seller_bp
    from .security import current_session_user

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(seller_bp)
    app.register_blueprint(customer_bp)
    app.register_blueprint(rider_bp)
    app.register_blueprint(admin_bp)
    # Keep the former URL as the dedicated Admin OTP login entry point.
    app.add_url_rule("/admin/login", endpoint="auth.admin_login", view_func=admin_login, methods=["GET", "POST"])
    app.register_blueprint(orders_bp)

    @app.before_request
    def reject_revoked_sessions():
        g.current_user = None
        if session.get("user_id") is not None:
            user = current_session_user()
            if user is None:
                session.clear()
            else:
                session["role"] = user.role
                g.current_user = user

    @app.context_processor
    def branding():
        setting = db.session.get(AppSetting, 1)
        logo_path = setting.logo_path if setting and setting.logo_path else "logo.svg"
        if logo_path.lower().endswith(".svg"):
            logo_path = "logo.svg"
        return {
            "app_name": setting.app_name if setting else app.config["APP_NAME"],
            "app_logo": logo_path,
            "min_password_length": app.config["MIN_PASSWORD_LENGTH"],
            "max_password_length": app.config["MAX_PASSWORD_LENGTH"],
            "current_locale": str(get_locale() or app.config["BABEL_DEFAULT_LOCALE"]).replace("-", "_"),
            "supported_locales": SUPPORTED_LOCALES,
        }

    @app.after_request
    def security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        image_sources = ["'self'", "data:", "https://images.unsplash.com"]
        media_origin = urlsplit(app.config.get("CATALOG_MEDIA_PUBLIC_BASE_URL", ""))
        if (
            media_origin.scheme in {"http", "https"}
            and media_origin.hostname
            and not media_origin.username
            and not media_origin.password
        ):
            image_sources.append(f"{media_origin.scheme}://{media_origin.netloc}")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; base-uri 'self'; object-src 'none'; frame-ancestors 'none'; "
            f"form-action 'self'; img-src {' '.join(image_sources)}; "
            "style-src 'self' https://cdn.jsdelivr.net; script-src 'self'; "
            "connect-src 'self'",
        )
        if app.config.get("ENVIRONMENT") == "production" and request_is_secure():
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    @app.cli.command("seed-catalog")
    def seed_catalog():
        from .seed import seed_catalog_data

        created = seed_catalog_data()
        click.echo(f"Catalog seeded: {created} records created.")

    @app.cli.command("import-fdc")
    @click.option("--zip-path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option("--release", required=True, help="USDA FoodData Central release label, such as 2024-10-31.")
    @click.option("--max-db-mib", default=400, show_default=True, type=click.IntRange(min=1, max=400))
    @click.option("--batch-size", default=2000, show_default=True, type=click.IntRange(min=100, max=10000))
    def import_fdc(zip_path, release, max_db_mib, batch_size):
        """Import a USDA FoodData Central CSV archive within a strict DB size limit."""
        from .services.food_data_import import import_fdc_archive

        try:
            counts = import_fdc_archive(zip_path, release, max_db_mib * 1024 * 1024, batch_size)
        except (OSError, ValueError, RuntimeError, zipfile.BadZipFile) as error:
            raise click.ClickException(str(error)) from error
        click.echo("USDA FoodData Central import completed:")
        for table, count in counts.items():
            click.echo(f"  {table}: {count:,}")

    @app.cli.command("import-foodon")
    @click.option("--owl-path", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
    @click.option("--max-db-mib", default=400, show_default=True, type=click.IntRange(min=1, max=400))
    @click.option("--batch-size", default=2000, show_default=True, type=click.IntRange(min=100, max=10000))
    def import_foodon(owl_path, max_db_mib, batch_size):
        """Import FoodOn food-product taxonomy terms without inventing records."""
        from .services.food_data_import import import_foodon_ontology

        try:
            count = import_foodon_ontology(owl_path, max_db_mib * 1024 * 1024, batch_size)
        except (OSError, ValueError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"FoodOn categories imported: {count:,}")

    @app.cli.command("create-admin")
    @click.option("--email", prompt=True)
    @click.option("--name", prompt=True)
    def create_admin(email, name):
        from .models import AdminProfile, User

        if User.query.filter_by(email=email.lower().strip()).first():
            raise click.ClickException("An account with this email already exists.")
        user = User(email=email.lower().strip(), role="admin")
        # The shared User schema requires a hash; Admin sign-in never accepts it.
        user.set_password(secrets.token_urlsafe(48))
        user.admin_profile = AdminProfile(full_name=name.strip())
        db.session.add(user)
        db.session.commit()
        click.echo("Admin account created.")

    @app.cli.command("ensure-admin")
    def ensure_admin():
        """Create the configured bootstrap admin once, after migrations."""
        before = db.session.scalar(text("SELECT COUNT(*) FROM users")) if inspect(db.engine).has_table("users") else 0
        _bootstrap_admin(app)
        after = db.session.scalar(text("SELECT COUNT(*) FROM users")) if inspect(db.engine).has_table("users") else 0
        click.echo("Configured admin ensured." if after > before else "No new admin was needed.")

    @app.cli.command("retry-emails")
    def retry_emails():
        """Retry queued transactional emails that failed to deliver."""
        from .services.mail import retry_pending_emails

        delivered = retry_pending_emails()
        click.echo(f"Queued emails retried: {delivered} delivered.")

    @app.cli.command("db-size")
    def db_size():
        """Report the current database size against the configured ceiling."""
        from .services.backup import database_ceiling_bytes, database_size_bytes

        size = database_size_bytes()
        ceiling = database_ceiling_bytes()
        click.echo(
            f"Database size: {size / (1024 * 1024):.2f} MiB "
            f"(ceiling {ceiling / (1024 * 1024):.0f} MiB)."
        )

    @app.cli.command("backup-db")
    @click.option("--to", "destination", required=True, type=click.Path(dir_okay=False, path_type=Path))
    def backup_db(destination):
        """Write and verify a database backup."""
        from .services.backup import assert_within_ceiling, backup_database

        try:
            assert_within_ceiling()
            path = backup_database(destination)
        except (OSError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Backup verified and written to {path}.")

    @app.cli.command("restore-db")
    @click.option("--from", "source", required=True, type=click.Path(exists=True, dir_okay=False, path_type=Path))
    def restore_db(source):
        """Restore a verified backup over the live database."""
        from .services.backup import restore_database

        try:
            restore_database(source)
        except (OSError, RuntimeError) as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Database restored from {source}.")

    @app.cli.command("production-check")
    def production_check():
        """Review production launch readiness and list anything still missing."""
        from .services.review import production_readiness

        ok, issues = production_readiness(app.config)
        if ok:
            click.echo("Production readiness review passed.")
            return
        click.echo("Production readiness review found open items:")
        for issue in issues:
            click.echo(f"  - {issue}")
        raise SystemExit(1)

    @app.errorhandler(404)
    def not_found(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    with app.app_context():
        # Local and test databases remain convenient. Production schema changes
        # are applied through Flask-Migrate before serving traffic.
        if app.testing or app.config.get("ENVIRONMENT") != "production":
            db.create_all()
            _ensure_legacy_local_columns()
            _bootstrap_admin(app)

    return app


def _ensure_legacy_local_columns():
    """Keep local databases from the prototype usable during migration setup."""
    profile_tables = ("customers", "admins")
    for table in profile_tables:
        columns = {column["name"] for column in inspect(db.engine).get_columns(table)}
        if "profile_image" not in columns:
            with db.engine.begin() as connection:
                connection.execute(text(f"ALTER TABLE {table} ADD COLUMN profile_image VARCHAR(255)"))
    user_columns = {column["name"] for column in inspect(db.engine).get_columns("users")}
    local_additions = {
        "auth_version": "INTEGER NOT NULL DEFAULT 0",
        "preferred_locale": "VARCHAR(12)",
        "password_reset_hash": "VARCHAR(64)",
        "password_reset_expires_at": "TIMESTAMP",
        "password_reset_sent_at": "TIMESTAMP",
        "password_reset_attempts": "INTEGER NOT NULL DEFAULT 0",
    }
    has_settings = inspect(db.engine).has_table("app_settings")
    with db.engine.begin() as connection:
        for column_name, column_type in local_additions.items():
            if column_name not in user_columns:
                connection.execute(
                    text(f"ALTER TABLE users ADD COLUMN {column_name} {column_type}")
                )
        if has_settings:
            connection.execute(
                text("UPDATE app_settings SET app_name = 'NexHaat' WHERE lower(trim(app_name)) = 'freshbite'")
            )


def _bootstrap_admin(app):
    """Create the configured OTP-only admin without changing existing accounts."""
    email = (app.config.get("ADMIN_EMAIL") or "").strip().lower()
    if not email or "@" not in email:
        return

    from .models import AdminProfile, User

    existing = User.query.filter_by(email=email).first()
    if existing:
        if existing.role != "admin":
            logging.getLogger(__name__).warning("Configured admin email belongs to a non-admin account; skipping bootstrap.")
        return

    admin = User(email=email, role="admin")
    # Keep the required shared-schema field populated with an unusable secret.
    admin.set_password(secrets.token_urlsafe(48))
    admin.admin_profile = AdminProfile(full_name="NexHaat Admin")
    db.session.add(admin)
    db.session.commit()


def request_is_secure():
    from flask import request

    return request.is_secure
