"""Groq vision provider (free tier — llama-3.2-90b-vision-preview)."""
from app.config import settings

from .base import VisionProvider, VisionResponse
from ._openai_compat import openai_compat_call

_BASE_URL = "https://api.groq.com/openai/v1"


class GroqProvider(VisionProvider):
    name = "Groq"

    @property
    def model(self) -> str:
        return settings.groq_vision_model

    def is_available(self) -> bool:
        return bool(settings.groq_api_key)

    async def call(self, jpeg_bytes: bytes, prompt: str) -> VisionResponse:
        return await openai_compat_call(
            base_url=_BASE_URL,
            api_key=settings.groq_api_key,
            model=self.model,
            provider_name=self.name,
            jpeg_bytes=jpeg_bytes,
            prompt=prompt,
        )
