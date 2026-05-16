"""
Tests for image preprocessing utilities.
All tests are pure — no network required.
"""
import io
from pathlib import Path

import pytest
from PIL import Image

from app.integrations.image_processing import (
    make_thumbnail,
    preprocess_image,
)

FIXTURES = Path(__file__).parent / "fixtures"
IMAGES = FIXTURES / "images"


def _read_image(name: str) -> bytes:
    return (IMAGES / name).read_bytes()


# ─── Image preprocessing ───────────────────────────────────────────────────────

class TestPreprocessImage:
    def test_jpeg_passthrough_returns_jpeg(self):
        raw = _read_image("papulopustular.jpg")
        out, mime = preprocess_image(raw)
        assert mime == "image/jpeg"
        assert len(out) > 0
        # Verify it's a valid JPEG
        img = Image.open(io.BytesIO(out))
        assert img.format == "JPEG"

    def test_output_has_no_exif(self):
        """After preprocessing, output image should have no EXIF metadata."""
        raw = _read_image("with_exif.jpg")
        out, _ = preprocess_image(raw)
        img = Image.open(io.BytesIO(out))
        # PIL should report no EXIF or empty EXIF
        exif_data = img.info.get("exif", b"")
        # After our processing, exif should be absent or minimal
        assert "TestCamera" not in str(exif_data)

    def test_rgba_converted_to_rgb(self):
        """Images with alpha channel must be flattened to RGB."""
        buf = io.BytesIO()
        img = Image.new("RGBA", (100, 100), (200, 100, 50, 128))
        img.save(buf, format="PNG")
        raw = buf.getvalue()
        out, mime = preprocess_image(raw, filename="test.png")
        result_img = Image.open(io.BytesIO(out))
        assert result_img.mode == "RGB"

    def test_large_image_resized(self):
        """Images with longest edge > 1568px must be resized."""
        buf = io.BytesIO()
        img = Image.new("RGB", (3000, 2000), (200, 200, 200))
        img.save(buf, format="JPEG")
        raw = buf.getvalue()
        out, _ = preprocess_image(raw)
        result_img = Image.open(io.BytesIO(out))
        assert max(result_img.size) <= 1568

    def test_small_image_not_upscaled(self):
        """Small images should not be upscaled."""
        buf = io.BytesIO()
        img = Image.new("RGB", (100, 100), (200, 200, 200))
        img.save(buf, format="JPEG")
        raw = buf.getvalue()
        out, _ = preprocess_image(raw)
        result_img = Image.open(io.BytesIO(out))
        assert result_img.size == (100, 100)

    def test_oversized_file_raises(self):
        """Files exceeding the byte limit must raise ValueError."""
        oversized = b"x" * (11 * 1024 * 1024)
        with pytest.raises(ValueError, match="exceeds"):
            preprocess_image(oversized)

    def test_invalid_bytes_raises(self):
        """Non-image bytes must raise ValueError."""
        with pytest.raises(ValueError, match="Cannot read image"):
            preprocess_image(b"not an image at all")

    def test_palette_image_converted(self):
        """Palette (P mode) images must be converted to RGB."""
        buf = io.BytesIO()
        img = Image.new("P", (100, 100))
        img.save(buf, format="PNG")
        raw = buf.getvalue()
        out, _ = preprocess_image(raw)
        result_img = Image.open(io.BytesIO(out))
        assert result_img.mode == "RGB"


class TestMakeThumbnail:
    def test_thumbnail_is_data_url(self):
        raw = _read_image("papulopustular.jpg")
        out, _ = preprocess_image(raw)
        thumb = make_thumbnail(out)
        assert thumb.startswith("data:image/jpeg;base64,")

    def test_thumbnail_dimensions_bounded(self):
        """Thumbnail must be at most 400px on longest edge."""
        buf = io.BytesIO()
        img = Image.new("RGB", (1000, 800), (200, 200, 200))
        img.save(buf, format="JPEG")
        thumb = make_thumbnail(buf.getvalue(), max_size=400)
        # Decode and check size
        b64 = thumb.split(",")[1]
        import base64
        decoded = base64.b64decode(b64)
        result = Image.open(io.BytesIO(decoded))
        assert max(result.size) <= 400
