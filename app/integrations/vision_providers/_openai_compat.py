"""
Shared helper for OpenAI-compatible vision endpoints.
Used by Groq, OpenRouter, and HuggingFace providers.
"""
import base64
import json
import logging
import time

import httpx

from .base import (
    ProviderUnavailableError,
    RateLimitError,
    VisionResponse,
    parse_retry_after,
    strip_markdown_fences,
)
from .prompts import SYSTEM_PROMPT

logger = logging.getLogger(__name__)


async def openai_compat_call(
    *,
    base_url: str,
    api_key: str,
    model: str,
    provider_name: str,
    jpeg_bytes: bytes,
    prompt: str,
    extra_headers: dict | None = None,
    timeout: float = 60.0,
) -> VisionResponse:
    """
    POST to an OpenAI-compatible chat completions endpoint with a vision message.
    Image is sent as a base64 data URL in the message content.
    """
    b64 = base64.b64encode(jpeg_bytes).decode()
    image_url = f"data:image/jpeg;base64,{b64}"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            },
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0.1,
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        **(extra_headers or {}),
    }

    t0 = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                json=payload,
                headers=headers,
            )
    except httpx.TimeoutException as exc:
        raise ProviderUnavailableError(f"{provider_name} request timed out") from exc
    except httpx.ConnectError as exc:
        raise ProviderUnavailableError(f"{provider_name} connection failed: {exc}") from exc

    latency = int((time.monotonic() - t0) * 1000)

    if resp.status_code == 429:
        retry_after = parse_retry_after(resp.text)
        if not retry_after:
            try:
                retry_after = int(resp.headers.get("retry-after", 0)) or None
            except (ValueError, TypeError):
                retry_after = None
        logger.warning("%s rate limited: %s", provider_name, resp.text[:200])
        raise RateLimitError(
            f"{provider_name} rate limited",
            retry_after_seconds=retry_after,
        )

    if resp.status_code in (503, 502, 504):
        raise ProviderUnavailableError(f"{provider_name} returned {resp.status_code}")

    if resp.status_code != 200:
        raise RuntimeError(f"{provider_name} HTTP {resp.status_code}: {resp.text[:300]}")

    try:
        body = resp.json()
    except Exception as exc:
        raise RuntimeError(f"{provider_name} returned non-JSON: {resp.text[:200]}") from exc

    # Handle HuggingFace "model loading" response
    if "estimated_time" in body and "error" in body:
        raise ProviderUnavailableError(
            f"{provider_name} model loading (est. {body.get('estimated_time', '?')}s)"
        )

    try:
        raw_text = body["choices"][0]["message"]["content"]
    except (KeyError, IndexError) as exc:
        raise RuntimeError(f"{provider_name} unexpected response shape: {body}") from exc

    raw_text = strip_markdown_fences(raw_text)
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{provider_name} returned invalid JSON: {exc}") from exc

    return VisionResponse(
        assessment_dict=data,
        provider_used=provider_name,
        model_used=model,
        latency_ms=latency,
    )
