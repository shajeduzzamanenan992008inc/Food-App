"""Fail-closed image intake: private quarantine, malware scan, validation, S3.

Cleaned images are uploaded to an S3-compatible store only after ClamAV scans
the quarantined source and Pillow decodes/re-encodes it without source metadata.
Rejected files remain outside the static tree and age out after the configured
quarantine retention window.
"""

from datetime import datetime, timedelta, timezone
from io import BytesIO
import hashlib
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid
import warnings

import boto3
from flask import current_app
from PIL import Image, UnidentifiedImageError
from urllib.parse import quote, urlsplit


class CatalogMediaError(ValueError):
    """The catalog image did not complete the safe storage pipeline."""


_FORMATS = {
    "JPEG": (".jpg", "image/jpeg"),
    "PNG": (".png", "image/png"),
    "WEBP": (".webp", "image/webp"),
}


def _private_quarantine_folder():
    folder = Path(current_app.config["CATALOG_QUARANTINE_FOLDER"]).expanduser().resolve()
    static_root = Path(current_app.static_folder).resolve()
    try:
        folder.relative_to(static_root)
    except ValueError:
        pass
    else:
        raise CatalogMediaError("Quarantine must stay outside public static storage.")

    folder.mkdir(parents=True, exist_ok=True)
    try:
        folder.chmod(0o700)
    except OSError:
        # Windows ACLs are inherited from the private instance directory.
        pass
    return folder


def _enforce_quarantine_limit(folder, incoming_bytes):
    now = datetime.now(timezone.utc).timestamp()
    retention = max(1, current_app.config["CATALOG_QUARANTINE_RETENTION_HOURS"]) * 3600
    total_bytes = 0
    for candidate in folder.iterdir():
        if candidate.is_symlink() or not candidate.is_file() or not candidate.name.startswith("catalog-"):
            continue
        try:
            stat = candidate.stat()
            if now - stat.st_mtime > retention:
                candidate.unlink()
            else:
                total_bytes += stat.st_size
        except OSError:
            continue
    if incoming_bytes + total_bytes > current_app.config["MAX_CATALOG_QUARANTINE_BYTES"]:
        raise CatalogMediaError("Private quarantine storage is full.")


def _write_quarantine_file(folder, contents, token):
    path = folder / f"catalog-{token}.quarantine"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as quarantined:
            quarantined.write(contents)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def _scan_quarantined_file(path):
    scanner = (current_app.config.get("CATALOG_VIRUS_SCANNER") or "").strip()
    scanner_path = shutil.which(scanner) if scanner and not Path(scanner).is_absolute() else scanner
    if not scanner_path or (Path(scanner_path).is_absolute() and not Path(scanner_path).is_file()):
        raise CatalogMediaError("Virus scanner is not available.")
    try:
        result = subprocess.run(
            [scanner_path, "--no-summary", str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=current_app.config["CATALOG_SCAN_TIMEOUT"],
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CatalogMediaError("Virus scan did not complete.") from error
    if result.returncode != 0:
        raise CatalogMediaError("The quarantined upload did not pass the malware scan.")


def _validate_and_sanitize_image(contents):
    max_pixels = current_app.config["MAX_CATALOG_IMAGE_PIXELS"]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents), formats=tuple(_FORMATS)) as source:
                image_format = source.format
                width, height = source.size
                if not width or not height or width * height > max_pixels:
                    raise CatalogMediaError("Image dimensions are outside the allowed range.")
                source.verify()

            with Image.open(BytesIO(contents), formats=tuple(_FORMATS)) as source:
                source.load()
                image_format = source.format
                suffix, content_type = _FORMATS[image_format]
                if image_format == "JPEG":
                    mode = "RGB"
                elif "A" in source.getbands() or "transparency" in source.info:
                    mode = "RGBA"
                elif source.mode in {"1", "L", "RGB"}:
                    mode = source.mode
                else:
                    mode = "RGB"

                sanitized = Image.new(mode, source.size)
                sanitized.paste(source.convert(mode))
                output = BytesIO()
                save_options = {"format": image_format}
                if image_format == "JPEG":
                    save_options.update(quality=88, optimize=True)
                elif image_format == "WEBP":
                    save_options.update(quality=88, method=4)
                else:
                    save_options.update(optimize=True)
                sanitized.save(output, **save_options)
                sanitized.close()
    except CatalogMediaError:
        raise
    except (UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning,
            OSError, ValueError) as error:
        raise CatalogMediaError("Upload must be a complete JPEG, PNG, or WEBP image.") from error

    cleaned = output.getvalue()
    if not cleaned or len(cleaned) > current_app.config["MAX_CATALOG_IMAGE_BYTES"]:
        raise CatalogMediaError("Sanitized image exceeds the allowed file size.")
    return cleaned, suffix, content_type


def _external_media_url(contents, token, suffix, content_type):
    bucket = (current_app.config.get("CATALOG_MEDIA_BUCKET") or "").strip()
    base_url = (current_app.config.get("CATALOG_MEDIA_PUBLIC_BASE_URL") or "").strip().rstrip("/")
    parsed = urlsplit(base_url)
    if (
        not bucket or not base_url or parsed.scheme not in {"http", "https"}
        or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment
        or any(ord(character) < 32 for character in base_url)
        or (current_app.config.get("ENVIRONMENT") == "production" and parsed.scheme != "https")
    ):
        raise CatalogMediaError("External catalog image storage is not configured safely.")

    prefix = (current_app.config.get("CATALOG_MEDIA_KEY_PREFIX") or "products").strip(" /")
    if not prefix or ".." in prefix.split("/") or not re.fullmatch(r"[A-Za-z0-9/_-]+", prefix):
        raise CatalogMediaError("External catalog image storage prefix is invalid.")
    key = f"{prefix}/{token}{suffix}"
    endpoint = current_app.config.get("CATALOG_MEDIA_ENDPOINT_URL") or None
    try:
        client = boto3.client(
            "s3",
            region_name=current_app.config["CATALOG_MEDIA_REGION"],
            endpoint_url=endpoint,
        )
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=contents,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
            Metadata={"scan": "clean", "sha256": hashlib.sha256(contents).hexdigest()},
        )
    except Exception as error:
        current_app.logger.warning("Clean catalog media upload failed for key %s.", key)
        raise CatalogMediaError("Approved external catalog storage is unavailable.") from error
    return f"{base_url}/{quote(key, safe='/')}"


def store_catalog_image(upload):
    """Scan, validate, sanitize, and store one uploaded catalog image."""
    if not upload or not upload.filename:
        return None

    token = uuid.uuid4().hex
    maximum = current_app.config["MAX_CATALOG_IMAGE_BYTES"]
    contents = upload.stream.read(maximum + 1)
    upload.stream.seek(0)
    if not contents or len(contents) > maximum:
        raise CatalogMediaError("Upload is empty or exceeds the allowed file size.")

    folder = _private_quarantine_folder()
    _enforce_quarantine_limit(folder, len(contents))
    quarantine_path = _write_quarantine_file(folder, contents, token)
    try:
        _scan_quarantined_file(quarantine_path)
        sanitized, suffix, content_type = _validate_and_sanitize_image(contents)
        public_url = _external_media_url(sanitized, token, suffix, content_type)
    except CatalogMediaError:
        current_app.logger.warning("Catalog upload %s was retained in private quarantine.", token)
        raise

    try:
        quarantine_path.unlink(missing_ok=True)
    except OSError:
        current_app.logger.warning("Clean catalog quarantine file %s could not be removed.", token)
    return public_url
