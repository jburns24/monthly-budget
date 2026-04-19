"""Receipt image storage service.

Provides async save/load/delete operations and synchronous helpers for
MIME validation and image sanitization (EXIF stripping, resizing, re-encoding).

HEIC support is enabled via pillow_heif.register_heif_opener(), called once
at module import so every Pillow Image.open() call can decode HEIC/HEIF files.
"""

import io
import uuid
from pathlib import Path

import aiofiles
import magic
import pillow_heif
from PIL import Image

from app.config import settings

pillow_heif.register_heif_opener()

ACCEPTED_MIMES: frozenset[str] = frozenset(
    {
        "image/jpeg",
        "image/png",
        "image/webp",
        "image/heic",
        "image/heif",
    }
)

_MAX_DIMENSION = 3000
Image.MAX_IMAGE_PIXELS = 256_000_000


def validate_mime(raw: bytes) -> str:
    """Detect MIME type via magic bytes. Returns MIME string or raises ValueError.

    WebP detection is handled explicitly via the RIFF/WEBP signature because
    some libmagic versions report WebP as ``application/octet-stream``.
    """
    # WebP: RIFF????WEBP at bytes 0-11
    if len(raw) >= 12 and raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    mime: str = magic.from_buffer(raw, mime=True)
    if mime not in ACCEPTED_MIMES:
        raise ValueError(f"Unsupported MIME type: {mime!r}")
    return mime


def sanitize_image(raw: bytes) -> tuple[bytes, tuple[int, int]]:
    """Re-encode image to JPEG q=85, strip EXIF, resize to max 3000×3000.

    Raises PIL.Image.DecompressionBombError if the image exceeds MAX_IMAGE_PIXELS.

    Returns
    -------
    tuple[bytes, tuple[int, int]]
        ``(jpeg_bytes, (width, height))`` of the sanitized image.
    """
    base = Image.open(io.BytesIO(raw))
    base.load()
    img: Image.Image = base.convert("RGB") if base.mode != "RGB" else base

    if img.width > _MAX_DIMENSION or img.height > _MAX_DIMENSION:
        img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue(), img.size


async def save(family_id: uuid.UUID, data: bytes, suffix: str) -> Path:
    """Write image bytes to ``{receipt_storage_path}/{family_id}/{uuid}{suffix}``."""
    dir_path = settings.receipt_storage_path / str(family_id)
    dir_path.mkdir(parents=True, exist_ok=True)
    file_path = dir_path / f"{uuid.uuid4()}{suffix}"
    async with aiofiles.open(file_path, "wb") as f:
        await f.write(data)
    return file_path


async def load(path: Path) -> bytes:
    """Read image bytes from disk."""
    async with aiofiles.open(path, "rb") as f:
        return await f.read()


async def delete(path: Path) -> None:
    """Delete image file from disk. No-op if the file does not exist."""
    try:
        path.unlink()
    except FileNotFoundError:
        pass
