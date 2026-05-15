"""
Tests for the Gemini Vision client wrapper.
All Gemini API calls are mocked — no network required.
"""
import io
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from PIL import Image

from app.integrations.gemini_vision import (
    call_vision_api,
    make_thumbnail,
    preprocess_image,
)
from app.models.visual_assessment import VisualAssessment

FIXTURES = Path(__file__).parent / "fixtures"
IMAGES = FIXTURES / "images"
MOCKS = FIXTURES / "mock_responses"


def _load_mock(name: str) -> str:
    return (MOCKS / name).read_text()


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


# ─── Gemini API call ──────────────────────────────────────────────────────────

def _make_mock_response(json_text: str) -> MagicMock:
    mock = MagicMock()
    mock.text = json_text
    return mock


class TestCallVisionAPI:
    @pytest.mark.asyncio
    async def test_grade2_response_parsed_correctly(self):
        mock_response = _make_mock_response(_load_mock("gemini_grade2.json"))
        with patch("app.integrations.gemini_vision._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            raw = _read_image("papulopustular.jpg")
            jpeg, _ = preprocess_image(raw)
            result = await call_vision_api(
                jpeg_bytes=jpeg,
                suspected_ae="Acneiform Eruption",
                treatment_modality="targeted_therapy",
            )

        assert isinstance(result, VisualAssessment)
        assert result.image_quality.adequate is True
        assert result.ae_match is True
        assert result.ctcae_grade_visual is not None
        assert result.ctcae_grade_visual.grade == 2
        assert result.ctcae_grade_visual.confidence == "moderate"

    @pytest.mark.asyncio
    async def test_inadequate_image_parsed(self):
        mock_response = _make_mock_response(_load_mock("gemini_inadequate.json"))
        with patch("app.integrations.gemini_vision._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            raw = _read_image("blurry_photo.jpg")
            jpeg, _ = preprocess_image(raw)
            result = await call_vision_api(
                jpeg_bytes=jpeg,
                suspected_ae="Acneiform Eruption",
                treatment_modality="targeted_therapy",
            )

        assert result.image_quality.adequate is False
        assert result.image_quality.retake_recommended is True
        assert result.ctcae_grade_visual is None
        assert result.visual_findings is None
        assert "blurry" in result.image_quality.issues

    @pytest.mark.asyncio
    async def test_ae_no_match_parsed(self):
        mock_response = _make_mock_response(_load_mock("gemini_no_match.json"))
        with patch("app.integrations.gemini_vision._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            raw = _read_image("papulopustular.jpg")
            jpeg, _ = preprocess_image(raw)
            result = await call_vision_api(
                jpeg_bytes=jpeg,
                suspected_ae="Oral Mucositis",
                treatment_modality="cytotoxic_chemo",
            )

        assert result.ae_match is False
        assert result.visual_findings is None

    @pytest.mark.asyncio
    async def test_api_error_raises_runtime_error(self):
        with patch("app.integrations.gemini_vision._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(
                side_effect=Exception("API unavailable")
            )
            mock_get_client.return_value = mock_client

            raw = _read_image("papulopustular.jpg")
            jpeg, _ = preprocess_image(raw)
            with pytest.raises(RuntimeError, match="Vision API unavailable"):
                await call_vision_api(jpeg, "test", "test")

    @pytest.mark.asyncio
    async def test_invalid_json_raises_runtime_error(self):
        mock_response = _make_mock_response("this is not json at all {{{")
        with patch("app.integrations.gemini_vision._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            raw = _read_image("papulopustular.jpg")
            jpeg, _ = preprocess_image(raw)
            with pytest.raises(RuntimeError, match="invalid JSON"):
                await call_vision_api(jpeg, "test", "test")

    @pytest.mark.asyncio
    async def test_markdown_fenced_json_parsed(self):
        """Gemini sometimes wraps JSON in markdown code fences — must strip them."""
        fenced = "```json\n" + _load_mock("gemini_grade2.json") + "\n```"
        mock_response = _make_mock_response(fenced)
        with patch("app.integrations.gemini_vision._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            raw = _read_image("papulopustular.jpg")
            jpeg, _ = preprocess_image(raw)
            result = await call_vision_api(jpeg, "test", "test")

        assert result.ctcae_grade_visual.grade == 2

    @pytest.mark.asyncio
    async def test_empty_response_raises(self):
        mock_response = _make_mock_response("")
        with patch("app.integrations.gemini_vision._get_client") as mock_get_client:
            mock_client = MagicMock()
            mock_client.aio.models.generate_content = AsyncMock(return_value=mock_response)
            mock_get_client.return_value = mock_client

            raw = _read_image("papulopustular.jpg")
            jpeg, _ = preprocess_image(raw)
            with pytest.raises(RuntimeError, match="Empty response"):
                await call_vision_api(jpeg, "test", "test")
