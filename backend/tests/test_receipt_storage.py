"""Tests for receipt_storage service.

Covers:
- MIME validation accepts image/* types, rejects non-image bytes
- sanitize_image re-encodes to JPEG, strips EXIF, resizes oversized images
- Decompression-bomb guard raises PIL error on giant images
- HEIC → JPEG conversion round-trip via pillow_heif
- Async save / load / delete file operations
"""

import io
import uuid
from pathlib import Path
from unittest.mock import patch

import pillow_heif
import pytest
from PIL import Image

from app.services.receipt_storage import delete, load, sanitize_image, save, validate_mime

pillow_heif.register_heif_opener()

# ---------------------------------------------------------------------------
# Image factories
# ---------------------------------------------------------------------------


def _make_jpeg(width: int = 100, height: int = 100, color: tuple = (200, 100, 50)) -> bytes:
    img = Image.new("RGB", (width, height), color=color)
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_png(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(50, 100, 200))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def _make_webp(width: int = 100, height: int = 100) -> bytes:
    img = Image.new("RGB", (width, height), color=(10, 20, 30))
    buf = io.BytesIO()
    img.save(buf, format="WEBP")
    return buf.getvalue()


def _make_heic(width: int = 64, height: int = 64) -> bytes:
    img = Image.new("RGB", (width, height), color=(180, 90, 40))
    buf = io.BytesIO()
    img.save(buf, format="HEIF")
    return buf.getvalue()


def _make_jpeg_with_exif() -> bytes:
    """Return a JPEG with embedded EXIF GPS data."""
    img = Image.new("RGB", (100, 100), color=(10, 20, 30))
    buf = io.BytesIO()
    # Minimal EXIF blob: Exif\x00\x00 + TIFF header (little-endian, no IFD entries)
    exif_blob = b"Exif\x00\x00\x49\x49\x2a\x00\x08\x00\x00\x00\x00\x00"
    img.save(buf, format="JPEG", exif=exif_blob)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# validate_mime tests
# ---------------------------------------------------------------------------


def test_validate_mime_accepts_jpeg() -> None:
    assert validate_mime(_make_jpeg()) == "image/jpeg"


def test_validate_mime_accepts_png() -> None:
    assert validate_mime(_make_png()) == "image/png"


def test_validate_mime_accepts_webp() -> None:
    assert validate_mime(_make_webp()) == "image/webp"


def test_validate_mime_rejects_pdf() -> None:
    pdf_bytes = b"%PDF-1.4 fake pdf content"
    with pytest.raises(ValueError, match="Unsupported MIME type"):
        validate_mime(pdf_bytes)


def test_validate_mime_rejects_text() -> None:
    with pytest.raises(ValueError, match="Unsupported MIME type"):
        validate_mime(b"Hello, this is plain text not an image")


def test_validate_mime_rejects_empty_bytes() -> None:
    with pytest.raises(ValueError, match="Unsupported MIME type"):
        validate_mime(b"")


# ---------------------------------------------------------------------------
# sanitize_image tests
# ---------------------------------------------------------------------------


def test_sanitize_jpeg_returns_jpeg_bytes() -> None:
    raw = _make_jpeg()
    result, size = sanitize_image(raw)
    # Output is valid JPEG
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"
    assert size == img.size


def test_sanitize_png_converts_to_jpeg() -> None:
    raw = _make_png()
    result, _ = sanitize_image(raw)
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"


def test_sanitize_strips_exif_data() -> None:
    raw = _make_jpeg_with_exif()
    # Verify source has exif
    src = Image.open(io.BytesIO(raw))
    assert "exif" in src.info

    result, _ = sanitize_image(raw)
    out = Image.open(io.BytesIO(result))
    assert "exif" not in out.info


def test_sanitize_resizes_oversized_image() -> None:
    raw = _make_jpeg(width=4000, height=4000)
    result, (w, h) = sanitize_image(raw)
    assert w <= 3000
    assert h <= 3000


def test_sanitize_preserves_small_image_dimensions() -> None:
    raw = _make_jpeg(width=200, height=150)
    result, (w, h) = sanitize_image(raw)
    assert w == 200
    assert h == 150


def test_sanitize_decompression_bomb_is_rejected() -> None:
    """Images exceeding MAX_IMAGE_PIXELS raise PIL DecompressionBombError."""
    raw = _make_jpeg(100, 100)
    with patch("app.services.receipt_storage.Image.MAX_IMAGE_PIXELS", 1):
        with pytest.raises(Image.DecompressionBombError):
            sanitize_image(raw)


# ---------------------------------------------------------------------------
# HEIC → JPEG conversion
# ---------------------------------------------------------------------------


def test_sanitize_heic_converts_to_jpeg() -> None:
    """HEIC input is decoded via pillow_heif and re-encoded as JPEG."""
    raw = _make_heic()
    result, size = sanitize_image(raw)
    img = Image.open(io.BytesIO(result))
    assert img.format == "JPEG"
    assert size[0] > 0 and size[1] > 0


# ---------------------------------------------------------------------------
# Async save / load / delete tests
# ---------------------------------------------------------------------------


async def test_save_writes_file_to_disk(tmp_path: Path) -> None:
    family_id = uuid.uuid4()
    data = _make_jpeg()

    with patch("app.services.receipt_storage.settings") as mock_settings:
        mock_settings.receipt_storage_path = tmp_path
        path = await save(family_id, data, ".jpg")

    assert path.exists()
    assert path.read_bytes() == data
    assert path.suffix == ".jpg"
    assert str(family_id) in str(path)


async def test_save_creates_family_subdirectory(tmp_path: Path) -> None:
    family_id = uuid.uuid4()

    with patch("app.services.receipt_storage.settings") as mock_settings:
        mock_settings.receipt_storage_path = tmp_path
        path = await save(family_id, b"data", ".jpg")

    assert path.parent.name == str(family_id)


async def test_load_reads_file_from_disk(tmp_path: Path) -> None:
    data = b"test image data"
    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(data)

    result = await load(test_file)

    assert result == data


async def test_delete_removes_file_from_disk(tmp_path: Path) -> None:
    test_file = tmp_path / "test.jpg"
    test_file.write_bytes(b"data")
    assert test_file.exists()

    await delete(test_file)

    assert not test_file.exists()


async def test_delete_is_noop_for_missing_file(tmp_path: Path) -> None:
    """Deleting a nonexistent file should not raise."""
    missing = tmp_path / "nonexistent.jpg"
    await delete(missing)  # Should not raise
