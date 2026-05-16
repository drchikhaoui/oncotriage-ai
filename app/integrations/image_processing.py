"""
Image preprocessing utilities (EXIF stripping, resizing, thumbnail generation).
Extracted from the legacy gemini_vision module.
"""
import base64
import io
import logging

import pillow_heif
from PIL import Image, ImageOps

from app.config import settings

pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)


def preprocess_image(raw_bytes: bytes, filename: str = "") -> tuple[bytes, str]:
    """
    Validate, orient, strip EXIF, resize, and re-encode image.
    Returns (jpeg_bytes, mime_type).
    Raises ValueError on invalid input.
    """
    if len(raw_bytes) > settings.vision_max_image_bytes:
        raise ValueError(f"Image exceeds {settings.vision_max_image_bytes // (1024*1024)} MB limit")

    try:
        img = Image.open(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError(f"Cannot read image: {exc}") from exc

    # Apply EXIF orientation then discard all metadata
    img = ImageOps.exif_transpose(img)

    # Flatten alpha channel
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize longest edge to max
    w, h = img.size
    max_edge = settings.vision_max_edge_px
    if max(w, h) > max_edge:
        ratio = max_edge / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # Re-encode as JPEG, no EXIF
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=settings.vision_jpeg_quality, optimize=True)
    jpeg_bytes = buf.getvalue()

    return jpeg_bytes, "image/jpeg"


def make_thumbnail(jpeg_bytes: bytes, max_size: int = 400) -> str:
    """Create a base64 data URL thumbnail (ephemeral — never stored)."""
    img = Image.open(io.BytesIO(jpeg_bytes))
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"
