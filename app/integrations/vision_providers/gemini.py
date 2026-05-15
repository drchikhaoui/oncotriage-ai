"""Gemini vision provider (Google AI Studio free tier)."""
import logging
import re
import time

from google import genai
from google.genai import types

from app.config import settings
from app.models.visual_assessment import VisualAssessment

from .base import (
    ProviderUnavailableError,
    RateLimitError,
    VisionProvider,
    VisionResponse,
    parse_retry_after,
)
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        if not settings.google_ai_studio_api_key:
            raise ProviderUnavailableError("GOOGLE_AI_STUDIO_API_KEY is not set")
        _client = genai.Client(api_key=settings.google_ai_studio_api_key)
    return _client


def _parse_vision_response(raw_text: str) -> dict:
    """
    3-strategy parser for Gemini's response.
    Returns a validated VisualAssessment dict or raises ValueError.
    """
    # Strategy 1: direct parse + schema validation
    try:
        return VisualAssessment.model_validate_json(raw_text).model_dump()
    except Exception:
        pass

    # Strategy 2: strip markdown code fences (```json ... ```)
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw_text.strip(), flags=re.MULTILINE)
    try:
        return VisualAssessment.model_validate_json(cleaned).model_dump()
    except Exception:
        pass

    # Strategy 3: extract the first {...} block from arbitrary surrounding text
    match = re.search(r"\{.*\}", raw_text, re.DOTALL)
    if match:
        try:
            return VisualAssessment.model_validate_json(match.group(0)).model_dump()
        except Exception:
            pass

    raise ValueError(
        f"Could not parse response after 3 strategies (preview: {raw_text[:200]!r})"
    )


class GeminiProvider(VisionProvider):
    name = "Gemini"

    @property
    def model(self) -> str:
        return settings.vision_model

    def is_available(self) -> bool:
        return bool(settings.google_ai_studio_api_key)

    async def call(self, jpeg_bytes: bytes, prompt: str) -> VisionResponse:
        client = _get_client()
        image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
        system_part = types.Part(text=SYSTEM_PROMPT)

        for attempt in range(2):
            retry_suffix = (
                "\n\nCRITICAL: Return ONLY the JSON object matching the schema. "
                "No prose, no markdown, no code fences. Start with { and end with }."
                if attempt == 1
                else ""
            )
            text_part = types.Part(text=prompt + retry_suffix)

            t0 = time.monotonic()
            try:
                response = await client.aio.models.generate_content(
                    model=self.model,
                    contents=[
                        types.Content(
                            role="user",
                            parts=[system_part, image_part, text_part],
                        )
                    ],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                        response_schema=VisualAssessment,
                        temperature=0.1,
                        max_output_tokens=2048,
                    ),
                )
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "RESOURCE_EXHAUSTED" in err_str or "quota" in err_str.lower():
                    retry_after = parse_retry_after(err_str)
                    logger.warning("Gemini rate limit: %s", exc)
                    raise RateLimitError(
                        f"Gemini quota exceeded: {exc}", retry_after_seconds=retry_after
                    ) from exc
                if "503" in err_str or "unavailable" in err_str.lower():
                    raise ProviderUnavailableError(f"Gemini unavailable: {exc}") from exc
                raise RuntimeError(f"Gemini API error: {exc}") from exc

            latency = int((time.monotonic() - t0) * 1000)
            raw_text = response.text

            if not raw_text:
                if attempt == 0:
                    logger.warning("Gemini returned empty response, retrying...")
                    continue
                raise ProviderUnavailableError("Gemini returned empty response after retry")

            try:
                data = _parse_vision_response(raw_text)
                if attempt == 1:
                    logger.info("Gemini parse succeeded on retry (attempt 2)")
                return VisionResponse(
                    assessment_dict=data,
                    provider_used=self.name,
                    model_used=self.model,
                    latency_ms=latency,
                )
            except ValueError as exc:
                if attempt == 0:
                    logger.warning(
                        "Gemini parse failed on attempt 1, retrying with stricter prompt: %s", exc
                    )
                    continue
                logger.error(
                    "Gemini parse failed after retry: %s | raw: %.200s", exc, raw_text
                )
                raise ProviderUnavailableError(
                    f"Gemini returned unparseable response: {exc}"
                ) from exc
