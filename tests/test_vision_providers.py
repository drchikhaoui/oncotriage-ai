"""
Tests for the multi-provider vision abstraction and fallback chain.
All external API calls are mocked (no network, no API keys required).
"""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.integrations.vision_providers.base import (
    AllProvidersFailedError,
    ProviderUnavailableError,
    RateLimitError,
    VisionResponse,
    parse_retry_after,
    strip_markdown_fences,
)
from app.integrations.vision_providers.chain import FallbackChain


# ─── Base utilities ────────────────────────────────────────────────────────────

class TestParseRetryAfter:
    def test_gemini_retrydelay_seconds(self):
        err = "RESOURCE_EXHAUSTED retryDelay: '60s'"
        assert parse_retry_after(err) == 60

    def test_numeric_retry_after(self):
        err = "Retry-After: 30"
        assert parse_retry_after(err) == 30

    def test_no_match_returns_none(self):
        assert parse_retry_after("Generic quota error") is None


class TestStripMarkdownFences:
    def test_strips_json_fence(self):
        fenced = "```json\n{\"key\": \"val\"}\n```"
        result = strip_markdown_fences(fenced)
        assert result == '{"key": "val"}'

    def test_strips_plain_fence(self):
        fenced = "```\n{\"key\": \"val\"}\n```"
        result = strip_markdown_fences(fenced)
        assert result.startswith("{")

    def test_passthrough_plain_json(self):
        plain = '{"key": "val"}'
        assert strip_markdown_fences(plain) == plain


# ─── FallbackChain ────────────────────────────────────────────────────────────

def _make_good_response(provider: str = "MockProvider") -> VisionResponse:
    return VisionResponse(
        assessment_dict={"image_quality": {"adequate": True, "issues": [], "retake_recommended": False},
                         "ae_match": True, "ae_match_explanation": "ok", "caveats": []},
        provider_used=provider,
        model_used="test-model",
        latency_ms=50,
    )


def _make_provider(name: str, response=None, raises=None, available: bool = True):
    """Build a mock VisionProvider."""
    p = MagicMock()
    p.name = name
    p.model = "test-model"
    p.is_available.return_value = available
    if raises:
        p.call = AsyncMock(side_effect=raises)
    else:
        p.call = AsyncMock(return_value=response or _make_good_response(name))
    return p


class TestFallbackChain:
    @pytest.mark.asyncio
    async def test_first_provider_success(self):
        p1 = _make_provider("A")
        p2 = _make_provider("B")
        chain = FallbackChain([p1, p2])
        result = await chain.analyze(b"img", "prompt")
        assert result.provider_used == "A"
        p2.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_falls_back_on_rate_limit(self):
        p1 = _make_provider("A", raises=RateLimitError("429", retry_after_seconds=60))
        p2 = _make_provider("B")
        chain = FallbackChain([p1, p2])
        result = await chain.analyze(b"img", "prompt")
        assert result.provider_used == "B"

    @pytest.mark.asyncio
    async def test_falls_back_on_unavailable(self):
        p1 = _make_provider("A", raises=ProviderUnavailableError("503"))
        p2 = _make_provider("B")
        chain = FallbackChain([p1, p2])
        result = await chain.analyze(b"img", "prompt")
        assert result.provider_used == "B"

    @pytest.mark.asyncio
    async def test_all_providers_fail_raises(self):
        p1 = _make_provider("A", raises=RateLimitError("429"))
        p2 = _make_provider("B", raises=ProviderUnavailableError("503"))
        chain = FallbackChain([p1, p2])
        with pytest.raises(AllProvidersFailedError):
            await chain.analyze(b"img", "prompt")

    @pytest.mark.asyncio
    async def test_runtime_error_propagates_immediately(self):
        """RuntimeError (bad schema, bad image) must not fall through to next provider."""
        p1 = _make_provider("A", raises=RuntimeError("invalid JSON"))
        p2 = _make_provider("B")
        chain = FallbackChain([p1, p2])
        with pytest.raises(RuntimeError, match="invalid JSON"):
            await chain.analyze(b"img", "prompt")
        p2.call.assert_not_called()

    @pytest.mark.asyncio
    async def test_unavailable_providers_skipped(self):
        p1 = _make_provider("A", available=False)
        p2 = _make_provider("B", available=True)
        chain = FallbackChain([p1, p2])
        result = await chain.analyze(b"img", "prompt")
        assert result.provider_used == "B"

    @pytest.mark.asyncio
    async def test_no_providers_raises(self):
        chain = FallbackChain([])
        with pytest.raises(AllProvidersFailedError):
            await chain.analyze(b"img", "prompt")

    @pytest.mark.asyncio
    async def test_three_provider_chain_tries_all_on_failure(self):
        p1 = _make_provider("A", raises=RateLimitError("429"))
        p2 = _make_provider("B", raises=ProviderUnavailableError("503"))
        p3 = _make_provider("C")
        chain = FallbackChain([p1, p2, p3])
        result = await chain.analyze(b"img", "prompt")
        assert result.provider_used == "C"

    def test_chain_excludes_unavailable_at_build_time(self):
        p1 = _make_provider("A", available=False)
        p2 = _make_provider("B", available=True)
        chain = FallbackChain([p1, p2])
        assert len(chain.providers) == 1
        assert chain.providers[0].name == "B"


# ─── Provider availability ─────────────────────────────────────────────────────

class TestProviderAvailability:
    def test_gemini_unavailable_without_key(self):
        from app.integrations.vision_providers.gemini import GeminiProvider
        with patch("app.integrations.vision_providers.gemini.settings") as mock_s:
            mock_s.google_ai_studio_api_key = ""
            p = GeminiProvider()
            assert p.is_available() is False

    def test_gemini_available_with_key(self):
        from app.integrations.vision_providers.gemini import GeminiProvider
        with patch("app.integrations.vision_providers.gemini.settings") as mock_s:
            mock_s.google_ai_studio_api_key = "AIzaFakeKey"
            p = GeminiProvider()
            assert p.is_available() is True

    def test_groq_unavailable_without_key(self):
        from app.integrations.vision_providers.groq import GroqProvider
        with patch("app.integrations.vision_providers.groq.settings") as mock_s:
            mock_s.groq_api_key = ""
            p = GroqProvider()
            assert p.is_available() is False

    def test_openrouter_unavailable_without_key(self):
        from app.integrations.vision_providers.openrouter import OpenRouterProvider
        with patch("app.integrations.vision_providers.openrouter.settings") as mock_s:
            mock_s.openrouter_api_key = ""
            p = OpenRouterProvider()
            assert p.is_available() is False

    def test_huggingface_unavailable_without_key(self):
        from app.integrations.vision_providers.huggingface import HuggingFaceProvider
        with patch("app.integrations.vision_providers.huggingface.settings") as mock_s:
            mock_s.huggingface_api_key = ""
            p = HuggingFaceProvider()
            assert p.is_available() is False


# ─── get_chain() respects config ───────────────────────────────────────────────

class TestGetChain:
    def test_only_configured_providers_included(self):
        from app.integrations.vision_providers.chain import get_chain
        with patch("app.integrations.vision_providers.chain.settings") as mock_s:
            mock_s.vision_provider_chain = ["gemini", "groq"]
            mock_s.google_ai_studio_api_key = "key"
            mock_s.groq_api_key = ""  # not set → skipped
            mock_s.vision_model = "gemini-2.5-flash"
            chain = get_chain()
        # Only gemini should be in the chain
        names = [p.name for p in chain.providers]
        assert "Gemini" in names
        assert "Groq" not in names

    def test_empty_chain_when_no_keys(self):
        from app.integrations.vision_providers.chain import get_chain
        with patch("app.integrations.vision_providers.chain.settings") as mock_chain_s, \
             patch("app.integrations.vision_providers.gemini.settings") as mock_gem_s, \
             patch("app.integrations.vision_providers.groq.settings") as mock_groq_s, \
             patch("app.integrations.vision_providers.openrouter.settings") as mock_or_s, \
             patch("app.integrations.vision_providers.huggingface.settings") as mock_hf_s:
            mock_chain_s.vision_provider_chain = ["gemini", "groq", "openrouter", "huggingface"]
            mock_gem_s.google_ai_studio_api_key = ""
            mock_groq_s.groq_api_key = ""
            mock_or_s.openrouter_api_key = ""
            mock_hf_s.huggingface_api_key = ""
            chain = get_chain()
        assert len(chain.providers) == 0


# ─── OpenAI-compatible helper ──────────────────────────────────────────────────

class TestOpenAICompatCall:
    @pytest.mark.asyncio
    async def test_successful_response_parsed(self):
        """A 200 response with valid JSON in choices[0].message.content is returned."""
        import respx
        import httpx as _httpx

        good_json = json.dumps({
            "image_quality": {"adequate": True, "issues": [], "retake_recommended": False},
            "ae_match": True, "ae_match_explanation": "ok", "caveats": [],
        })
        mock_body = {"choices": [{"message": {"content": good_json}}]}

        with respx.mock:
            respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
                return_value=_httpx.Response(200, json=mock_body)
            )
            from app.integrations.vision_providers._openai_compat import openai_compat_call
            result = await openai_compat_call(
                base_url="https://api.groq.com/openai/v1",
                api_key="test",
                model="llama-test",
                provider_name="Groq",
                jpeg_bytes=b"fake",
                prompt="test prompt",
            )
        assert result.provider_used == "Groq"
        assert result.assessment_dict["ae_match"] is True

    @pytest.mark.asyncio
    async def test_429_raises_rate_limit_error(self):
        import respx
        import httpx as _httpx

        with respx.mock:
            respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
                return_value=_httpx.Response(429, text="rate limit exceeded")
            )
            from app.integrations.vision_providers._openai_compat import openai_compat_call
            with pytest.raises(RateLimitError):
                await openai_compat_call(
                    base_url="https://api.groq.com/openai/v1",
                    api_key="test",
                    model="llama-test",
                    provider_name="Groq",
                    jpeg_bytes=b"fake",
                    prompt="test",
                )

    @pytest.mark.asyncio
    async def test_503_raises_provider_unavailable(self):
        import respx
        import httpx as _httpx

        with respx.mock:
            respx.post("https://api.groq.com/openai/v1/chat/completions").mock(
                return_value=_httpx.Response(503, text="service unavailable")
            )
            from app.integrations.vision_providers._openai_compat import openai_compat_call
            with pytest.raises(ProviderUnavailableError):
                await openai_compat_call(
                    base_url="https://api.groq.com/openai/v1",
                    api_key="test",
                    model="llama-test",
                    provider_name="Groq",
                    jpeg_bytes=b"fake",
                    prompt="test",
                )

    @pytest.mark.asyncio
    async def test_markdown_fenced_response_parsed(self):
        """Providers that wrap JSON in markdown fences are handled."""
        import respx
        import httpx as _httpx

        inner = '{"image_quality":{"adequate":true,"issues":[],"retake_recommended":false},"ae_match":true,"ae_match_explanation":"ok","caveats":[]}'
        fenced = f"```json\n{inner}\n```"
        mock_body = {"choices": [{"message": {"content": fenced}}]}

        with respx.mock:
            respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
                return_value=_httpx.Response(200, json=mock_body)
            )
            from app.integrations.vision_providers._openai_compat import openai_compat_call
            result = await openai_compat_call(
                base_url="https://openrouter.ai/api/v1",
                api_key="test",
                model="google/gemini-2.5-flash:free",
                provider_name="OpenRouter",
                jpeg_bytes=b"fake",
                prompt="test",
            )
        assert result.assessment_dict["ae_match"] is True


# ─── Gemini defensive parsing ──────────────────────────────────────────────────

_VALID_ASSESSMENT = {
    "image_quality": {"adequate": True, "issues": [], "retake_recommended": False},
    "ae_match": True,
    "ae_match_explanation": "Pimple-like lesions visible on face",
    "caveats": [],
}


class TestGeminiParseResponse:
    def test_valid_json_parses_directly(self):
        """Strategy 1: clean JSON is parsed and schema-validated."""
        from app.integrations.vision_providers.gemini import _parse_vision_response
        result = _parse_vision_response(json.dumps(_VALID_ASSESSMENT))
        assert result["ae_match"] is True

    def test_markdown_fenced_json_parsed(self):
        """Strategy 2: ```json ... ``` fences are stripped before parsing."""
        from app.integrations.vision_providers.gemini import _parse_vision_response
        inner = json.dumps({**_VALID_ASSESSMENT, "ae_match": False, "ae_match_explanation": "no match"})
        result = _parse_vision_response(f"```json\n{inner}\n```")
        assert result["ae_match"] is False

    def test_plain_fence_json_parsed(self):
        """Strategy 2 also handles plain ``` fences without 'json' tag."""
        from app.integrations.vision_providers.gemini import _parse_vision_response
        inner = json.dumps(_VALID_ASSESSMENT)
        result = _parse_vision_response(f"```\n{inner}\n```")
        assert result["ae_match"] is True

    def test_json_embedded_in_prose_parsed(self):
        """Strategy 3: extracts first {...} block from surrounding prose."""
        from app.integrations.vision_providers.gemini import _parse_vision_response
        inner = json.dumps(_VALID_ASSESSMENT)
        prose = f"Sure, here is my analysis:\n{inner}\nHope this helps!"
        result = _parse_vision_response(prose)
        assert result["ae_match"] is True

    def test_malformed_json_raises_value_error(self):
        """All 3 strategies fail → ValueError."""
        from app.integrations.vision_providers.gemini import _parse_vision_response
        with pytest.raises(ValueError, match="Could not parse"):
            _parse_vision_response("This is definitely not JSON at all!")

    def test_truncated_json_raises_value_error(self):
        """Truncated JSON mid-string → ValueError."""
        from app.integrations.vision_providers.gemini import _parse_vision_response
        truncated = '{"image_quality": {"adequate": true, "issues": [], "retake_rec'
        with pytest.raises(ValueError, match="Could not parse"):
            _parse_vision_response(truncated)

    @pytest.mark.asyncio
    async def test_parse_failure_retries_once_then_raises_provider_unavailable(self):
        """Persistent parse failure triggers 1 retry, then raises ProviderUnavailableError."""
        from app.integrations.vision_providers.gemini import GeminiProvider

        bad_response = MagicMock()
        bad_response.text = "Apologies, I cannot generate JSON for medical images."

        with patch("app.integrations.vision_providers.gemini.settings") as mock_s, \
             patch("app.integrations.vision_providers.gemini._get_client") as mock_get_client:
            mock_s.google_ai_studio_api_key = "fake-key"
            mock_s.vision_model = "gemini-2.5-flash"

            mock_aio = AsyncMock(return_value=bad_response)
            mock_get_client.return_value.aio.models.generate_content = mock_aio

            provider = GeminiProvider()
            with pytest.raises(ProviderUnavailableError, match="unparseable"):
                await provider.call(b"fake_image_bytes", "test prompt")

            assert mock_aio.call_count == 2, "Should have retried exactly once"

    @pytest.mark.asyncio
    async def test_parse_succeeds_on_retry(self):
        """If attempt 1 returns bad JSON but attempt 2 returns good JSON, succeeds."""
        from app.integrations.vision_providers.gemini import GeminiProvider

        bad_response = MagicMock()
        bad_response.text = "Here is the result: not valid json"

        good_response = MagicMock()
        good_response.text = json.dumps(_VALID_ASSESSMENT)

        with patch("app.integrations.vision_providers.gemini.settings") as mock_s, \
             patch("app.integrations.vision_providers.gemini._get_client") as mock_get_client:
            mock_s.google_ai_studio_api_key = "fake-key"
            mock_s.vision_model = "gemini-2.5-flash"

            mock_aio = AsyncMock(side_effect=[bad_response, good_response])
            mock_get_client.return_value.aio.models.generate_content = mock_aio

            provider = GeminiProvider()
            result = await provider.call(b"fake_image_bytes", "test prompt")

        assert result.provider_used == "Gemini"
        assert result.assessment_dict["ae_match"] is True
        assert mock_aio.call_count == 2
