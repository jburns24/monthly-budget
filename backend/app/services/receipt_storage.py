"""Receipt image preparation.

Images are never persisted: an upload is validated, sanitized and handed to the
model, and only the extracted result is saved. Synchronous helpers for
MIME validation and image sanitization (EXIF stripping, resizing, re-encoding).

HEIC support is enabled via pillow_heif.register_heif_opener(), called once
at module import so every Pillow Image.open() call can decode HEIC/HEIF files.
"""

import io

import magic
import pillow_heif
from PIL import Image

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
_MAX_INPUT_DIMENSION = 4000
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
    Raises ValueError if either input dimension exceeds ``_MAX_INPUT_DIMENSION``
    (4000px) — this guard fires *before* ``Image.load()`` so a crafted image
    with extreme aspect ratio (e.g. 4096×62499) cannot decode full pixels
    into memory even while remaining under the pixel-count cap.

    Returns
    -------
    tuple[bytes, tuple[int, int]]
        ``(jpeg_bytes, (width, height))`` of the sanitized image.
    """
    base = Image.open(io.BytesIO(raw))
    if base.width > _MAX_INPUT_DIMENSION or base.height > _MAX_INPUT_DIMENSION:
        raise ValueError(f"Image dimensions exceed limit: {base.size}")
    base.load()
    img: Image.Image = base.convert("RGB") if base.mode != "RGB" else base

    if img.width > _MAX_DIMENSION or img.height > _MAX_DIMENSION:
        img.thumbnail((_MAX_DIMENSION, _MAX_DIMENSION), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85, optimize=True)
    return out.getvalue(), img.size
