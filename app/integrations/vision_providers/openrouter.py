"""OpenRouter vision provider (free aggregator — google/gemini-2.5-flash:free etc.)."""
from app.config import settings

from .base import VisionProvider, VisionResponse
from ._openai_compat import openai_compat_call

_BASE_URL = "https://openrouter.ai/api/v1"


class OpenRouterProvider(VisionProvider):
    name = "OpenRouter"

    @property
    def model(self) -> str:
        return settings.openrouter_vision_model

    def is_available(self) -> bool:
        return bool(settings.openrouter_api_key)

    async def call(self, jpeg_bytes: bytes, prompt: str) -> VisionResponse:
        return await openai_compat_call(
            base_url=_BASE_URL,
            api_key=settings.openrouter_api_key,
            model=self.model,
            provider_name=self.name,
            jpeg_bytes=jpeg_bytes,
            prompt=prompt,
            extra_headers={
                "HTTP-Referer": "https://oncotriage.app",
                "X-Title": "OncoTriage AI",
            },
        )
