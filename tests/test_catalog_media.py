from io import BytesIO
from pathlib import Path

from PIL import Image
import pytest
from werkzeug.datastructures import FileStorage

from app.services.catalog_media import CatalogMediaError, store_catalog_image


def raster_bytes(format_name="PNG"):
    image = Image.new("RGB", (4, 4), (42, 118, 201))
    output = BytesIO()
    image.save(output, format=format_name)
    return output.getvalue()


def test_catalog_upload_is_scanned_sanitized_then_removed_from_quarantine(app, tmp_path, monkeypatch):
    quarantine = tmp_path / "private-quarantine"
    app.config["CATALOG_QUARANTINE_FOLDER"] = str(quarantine)
    seen = {}

    def scan(path):
        seen["scan_path"] = Path(path)
        assert Path(path).read_bytes().startswith(b"\x89PNG\r\n\x1a\n")

    def upload(contents, token, suffix, content_type):
        seen.update(contents=contents, token=token, suffix=suffix, content_type=content_type)
        assert seen["scan_path"].exists()
        with Image.open(BytesIO(contents)) as sanitized:
            assert sanitized.format == "PNG"
            assert sanitized.info == {}
        return "https://cdn.example.test/products/clean.png"

    monkeypatch.setattr("app.services.catalog_media._scan_quarantined_file", scan)
    monkeypatch.setattr("app.services.catalog_media._external_media_url", upload)
    with app.app_context():
        result = store_catalog_image(FileStorage(BytesIO(raster_bytes()), filename="seller-upload.png"))

    assert result == "https://cdn.example.test/products/clean.png"
    assert seen["suffix"] == ".png"
    assert seen["content_type"] == "image/png"
    assert not seen["scan_path"].exists()
    assert not list(quarantine.glob("catalog-*.quarantine"))


def test_rejected_catalog_upload_stays_in_private_quarantine(app, tmp_path, monkeypatch):
    quarantine = tmp_path / "private-quarantine"
    app.config["CATALOG_QUARANTINE_FOLDER"] = str(quarantine)

    def reject(path):
        raise CatalogMediaError("infected test file")

    monkeypatch.setattr("app.services.catalog_media._scan_quarantined_file", reject)
    monkeypatch.setattr(
        "app.services.catalog_media._external_media_url",
        lambda *_args: pytest.fail("rejected input must never be uploaded"),
    )
    with app.app_context(), pytest.raises(CatalogMediaError):
        store_catalog_image(FileStorage(BytesIO(raster_bytes()), filename="bad.png"))

    quarantined = list(quarantine.glob("catalog-*.quarantine"))
    assert len(quarantined) == 1
    assert quarantined[0].read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert not str(quarantined[0]).startswith(str(Path(app.static_folder).resolve()))


def test_invalid_image_is_never_sent_to_external_storage(app, tmp_path, monkeypatch):
    quarantine = tmp_path / "private-quarantine"
    app.config["CATALOG_QUARANTINE_FOLDER"] = str(quarantine)
    monkeypatch.setattr("app.services.catalog_media._scan_quarantined_file", lambda _path: None)
    monkeypatch.setattr(
        "app.services.catalog_media._external_media_url",
        lambda *_args: pytest.fail("invalid raster data must never be uploaded"),
    )
    with app.app_context(), pytest.raises(CatalogMediaError):
        store_catalog_image(FileStorage(BytesIO(b"not an image"), filename="bad.png"))

    assert len(list(quarantine.glob("catalog-*.quarantine"))) == 1


def test_external_storage_must_be_configured_before_clean_image_is_published(app, tmp_path, monkeypatch):
    app.config["CATALOG_QUARANTINE_FOLDER"] = str(tmp_path / "private-quarantine")
    app.config["CATALOG_MEDIA_BUCKET"] = None
    app.config["CATALOG_MEDIA_PUBLIC_BASE_URL"] = ""
    monkeypatch.setattr("app.services.catalog_media._scan_quarantined_file", lambda _path: None)
    with app.app_context(), pytest.raises(CatalogMediaError):
        store_catalog_image(FileStorage(BytesIO(raster_bytes()), filename="food.png"))

    assert len(list((tmp_path / "private-quarantine").glob("catalog-*.quarantine"))) == 1
