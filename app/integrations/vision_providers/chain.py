"""FallbackChain: tries each vision provider in order, skipping on rate-limit/unavailability."""
import logging

from app.config import settings

from .base import AllProvidersFailedError, ProviderUnavailableError, RateLimitError, VisionProvider, VisionResponse
from .gemini import GeminiProvider
from .groq import GroqProvider
from .huggingface import HuggingFaceProvider
from .openrouter import OpenRouterProvider

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, type[VisionProvider]] = {
    "gemini": GeminiProvider,
    "openrouter": OpenRouterProvider,
    "groq": GroqProvider,
    "huggingface": HuggingFaceProvider,
}


class FallbackChain:
    def __init__(self, providers: list[VisionProvider]):
        self.providers = [p for p in providers if p.is_available()]

    async def analyze(self, jpeg_bytes: bytes, prompt: str) -> VisionResponse:
        if not self.providers:
            raise AllProvidersFailedError(
                "No vision providers configured. Set at least one of: "
                "GOOGLE_AI_STUDIO_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, HUGGINGFACE_API_KEY"
            )

        errors: list[str] = []
        for provider in self.providers:
            try:
                logger.info("Trying vision provider: %s (%s)", provider.name, provider.model)
                result = await provider.call(jpeg_bytes, prompt)
                logger.info("Vision provider %s succeeded in %dms", provider.name, result.latency_ms)
                return result
            except (RateLimitError, ProviderUnavailableError) as exc:
                msg = f"{provider.name}: {exc}"
                errors.append(msg)
                logger.warning("Provider %s skipped — %s", provider.name, exc)
                continue
            # RuntimeError and others propagate immediately (bad image, bad schema)

        raise AllProvidersFailedError(
            f"All {len(self.providers)} vision provider(s) failed",
            errors=errors,
        )


def get_chain() -> FallbackChain:
    """Build the fallback chain from config. Called once per request."""
    providers: list[VisionProvider] = []
    for name in settings.vision_provider_chain:
        cls = _REGISTRY.get(name)
        if cls:
            providers.append(cls())
    return FallbackChain(providers)
