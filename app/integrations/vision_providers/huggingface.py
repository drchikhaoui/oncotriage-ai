"""HuggingFace Inference API vision provider (free serverless tier)."""
from app.config import settings

from .base import VisionProvider, VisionResponse
from ._openai_compat import openai_compat_call


class HuggingFaceProvider(VisionProvider):
    name = "HuggingFace"

    @property
    def model(self) -> str:
        return settings.huggingface_vision_model

    @property
    def _base_url(self) -> str:
        model_id = self.model.replace("/", "%2F")
        return f"https://api-inference.huggingface.co/models/{model_id}/v1"

    def is_available(self) -> bool:
        return bool(settings.huggingface_api_key)

    async def call(self, jpeg_bytes: bytes, prompt: str) -> VisionResponse:
        return await openai_compat_call(
            base_url=self._base_url,
            api_key=settings.huggingface_api_key,
            model=self.model,
            provider_name=self.name,
            jpeg_bytes=jpeg_bytes,
            prompt=prompt,
            timeout=90.0,  # HF cold starts can take up to ~30s
        )
