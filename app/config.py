from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    app_env: str = "development"
    log_level: str = "INFO"
    anthropic_api_key: str = ""
    database_url: str = f"sqlite+aiosqlite:///{BASE_DIR}/oncotriage.db"
    disable_llm: bool = False
    llm_model: str = "claude-sonnet-4-6"

    # Vision — Google AI Studio (free tier)
    google_ai_studio_api_key: str = ""
    vision_model: str = "gemini-2.5-flash"  # updated: broader free-tier in 2026
    vision_max_image_bytes: int = 10 * 1024 * 1024  # 10 MB
    vision_max_edge_px: int = 1568
    vision_jpeg_quality: int = 85
    disable_vision: bool = False

    # Vision provider fallback chain (skips providers without API keys)
    groq_api_key: str = ""
    groq_vision_model: str = "llama-3.2-90b-vision-preview"
    openrouter_api_key: str = ""
    openrouter_vision_model: str = "google/gemini-2.5-flash:free"
    huggingface_api_key: str = ""
    huggingface_vision_model: str = "meta-llama/Llama-3.2-11B-Vision-Instruct"
    vision_provider_chain: list[str] = ["gemini", "openrouter", "groq", "huggingface"]

    # Dashboard auth (HTTP Basic)
    clinician_user: str = "clinician"
    clinician_password: str = "change-me-in-production"

    # Privacy
    debug_retain_images: bool = False  # never True in production

settings = Settings()
