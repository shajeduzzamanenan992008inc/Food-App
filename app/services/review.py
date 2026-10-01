"""Production launch readiness checks used by the ``production-check`` CLI."""

import shutil
from pathlib import Path
from urllib.parse import urlsplit


def _scanner_available(config):
    scanner = (config.get("CATALOG_VIRUS_SCANNER") or "").strip()
    if not scanner:
        return False
    return shutil.which(scanner) is not None or Path(scanner).is_file()


def production_readiness(config):
    """Return (ok, issues) describing anything blocking a production launch."""
    issues = []

    secret = config.get("SECRET_KEY") or ""
    if secret == "dev-only-change-me" or len(secret) < 32:
        issues.append("SECRET_KEY must be a random value of at least 32 characters.")

    if not config.get("SESSION_COOKIE_SECURE"):
        issues.append("SESSION_COOKIE_SECURE must be enabled for HTTPS deployments.")

    parsed = urlsplit((config.get("PUBLIC_BASE_URL") or "").strip())
    if parsed.scheme != "https" or not parsed.hostname:
        issues.append("PUBLIC_BASE_URL must be a canonical HTTPS site URL.")

    if not (config.get("BREVO_API_KEY") and config.get("MAIL_DEFAULT_SENDER")):
        issues.append("Set BREVO_API_KEY and MAIL_DEFAULT_SENDER so transaction email can send.")

    if config.get("SQLALCHEMY_DATABASE_URI", "").startswith("sqlite"):
        issues.append("Use a managed PostgreSQL DATABASE_URL instead of SQLite in production.")

    if not (config.get("ADMIN_EMAIL") or "").strip():
        issues.append("Set ADMIN_EMAIL so the primary Admin account can be provisioned.")

    font_path = (config.get("INVOICE_FONT_PATH") or "").strip()
    if not font_path or not Path(font_path).is_file():
        issues.append("Set INVOICE_FONT_PATH to a Unicode font so invoices render non-Latin scripts.")

    if not (config.get("CATALOG_MEDIA_BUCKET") and config.get("CATALOG_MEDIA_PUBLIC_BASE_URL")):
        issues.append("Configure the catalog media bucket and public URL before enabling uploads.")

    if not _scanner_available(config):
        issues.append("Install the configured ClamAV scanner so catalog uploads can be scanned.")

    return (not issues), issues
