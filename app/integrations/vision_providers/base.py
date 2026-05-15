"""Abstract base for vision providers."""
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class VisionResponse:
    assessment_dict: dict
    provider_used: str
    model_used: str
    latency_ms: int


class RateLimitError(Exception):
    def __init__(self, message: str, retry_after_seconds: int | None = None):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderUnavailableError(Exception):
    pass


class AllProvidersFailedError(Exception):
    def __init__(self, message: str, errors: list[str] = field(default_factory=list)):
        super().__init__(message)
        self.errors = errors if isinstance(errors, list) else []


class VisionProvider(ABC):
    name: str
    model: str

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if the required API key env var is set."""
        ...

    @abstractmethod
    async def call(self, jpeg_bytes: bytes, prompt: str) -> VisionResponse:
        """
        Call the vision API and return a VisionResponse.

        Raises:
            RateLimitError: on 429 — caught by FallbackChain, next provider tried
            ProviderUnavailableError: on 503/connection — caught by FallbackChain
            RuntimeError: hard failure — propagated immediately (bad prompt, bad schema)
        """
        ...


def parse_retry_after(error_text: str) -> int | None:
    """Extract retry delay in seconds from a provider error message."""
    # Gemini: retryDelay: '60s'  or  retry_delay { seconds: 60 }
    m = re.search(r"retryDelay['\": ]+(\d+)s?", str(error_text), re.IGNORECASE)
    if m:
        return int(m.group(1))
    # Standard HTTP Retry-After header value (seconds)
    m = re.search(r"retry.after['\": ]+(\d+)", str(error_text), re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def strip_markdown_fences(text: str) -> str:
    """Remove ```json ... ``` wrappers that some models add despite being asked not to."""
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()
