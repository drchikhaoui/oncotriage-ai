"""
Google Gemini Vision client for CTCAE dermatologic AE grading.
Uses google-genai SDK with Gemini 2.0 Flash (free tier).
"""
import base64
import io
import json
import logging

import pillow_heif
from google import genai
from google.genai import types
from PIL import Image, ImageOps

from app.config import settings
from app.models.visual_assessment import VisualAssessment

pillow_heif.register_heif_opener()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an oncology nursing assistant trained in CTCAE v5.0 grading
of dermatologic adverse events. You assess clinical photographs to support care-team
decision-making. You are NOT providing a medical diagnosis — you are extracting
visual features to support CTCAE severity grading by a clinician.

Strict rules:
- If the image is unclear, poorly lit, or out of focus: set image_quality.adequate=false
  and DO NOT attempt to grade (ctcae_grade_visual=null, visual_findings=null)
- If the image shows something outside the requested AE category: set ae_match=false
  and explain in ae_match_explanation
- Always include caveats and confidence level
- Never provide treatment recommendations — only describe visual features
- Return ONLY valid JSON matching the provided schema — no markdown, no commentary
"""

USER_PROMPT_TEMPLATE = """Suspected AE: {suspected_ae}
Patient treatment modality: {treatment_modality}
Recent treatment dates context: {recent_treatment_dates}
Response language: {language}

Assess this photograph and return STRICT JSON with exactly this structure:

{{
  "image_quality": {{
    "adequate": true,
    "issues": [],
    "retake_recommended": false
  }},
  "ae_match": true,
  "ae_match_explanation": "describe what you see",
  "visual_findings": {{
    "body_surface_area_percent_estimate": 15,
    "distribution": "regional",
    "primary_morphology": ["papules", "pustules"],
    "secondary_features": [],
    "anatomical_site": "face and upper chest"
  }},
  "ctcae_grade_visual": {{
    "grade": 2,
    "ctcae_descriptor": "direct quote from CTCAE v5.0 matching this grade",
    "confidence": "moderate"
  }},
  "caveats": ["list any clinical caveats"],
  "language": "{language}"
}}

IMPORTANT: If image_quality.adequate is false OR ae_match is false,
set visual_findings=null and ctcae_grade_visual=null.
"""

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        api_key = settings.google_ai_studio_api_key
        if not api_key:
            raise ValueError("GOOGLE_AI_STUDIO_API_KEY is not set")
        _client = genai.Client(api_key=api_key)
    return _client


def preprocess_image(raw_bytes: bytes, filename: str = "") -> tuple[bytes, str]:
    """
    Validate, orient, strip EXIF, resize, and re-encode image.
    Returns (jpeg_bytes, mime_type).
    Raises ValueError on invalid input.
    """
    if len(raw_bytes) > settings.vision_max_image_bytes:
        raise ValueError(f"Image exceeds {settings.vision_max_image_bytes // (1024*1024)} MB limit")

    try:
        img = Image.open(io.BytesIO(raw_bytes))
    except Exception as exc:
        raise ValueError(f"Cannot read image: {exc}") from exc

    # Apply EXIF orientation then discard all metadata
    img = ImageOps.exif_transpose(img)

    # Flatten alpha channel
    if img.mode in ("RGBA", "LA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        if img.mode in ("RGBA", "LA"):
            bg.paste(img, mask=img.split()[-1])
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")

    # Resize longest edge to max
    w, h = img.size
    max_edge = settings.vision_max_edge_px
    if max(w, h) > max_edge:
        ratio = max_edge / max(w, h)
        img = img.resize((int(w * ratio), int(h * ratio)), Image.LANCZOS)

    # Re-encode as JPEG, no EXIF
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=settings.vision_jpeg_quality, optimize=True)
    jpeg_bytes = buf.getvalue()

    return jpeg_bytes, "image/jpeg"


def make_thumbnail(jpeg_bytes: bytes, max_size: int = 400) -> str:
    """Create a base64 data URL thumbnail (ephemeral — never stored)."""
    img = Image.open(io.BytesIO(jpeg_bytes))
    img.thumbnail((max_size, max_size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=60)
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/jpeg;base64,{b64}"


async def call_vision_api(
    jpeg_bytes: bytes,
    suspected_ae: str,
    treatment_modality: str,
    recent_treatment_dates: str = "not specified",
    language: str = "en",
) -> VisualAssessment:
    """
    Call Gemini vision API and parse the structured assessment.
    Raises RuntimeError on API failure or unparseable response.
    """
    if settings.disable_vision:
        raise RuntimeError("Vision module is disabled (DISABLE_VISION=true)")

    client = _get_client()
    prompt = USER_PROMPT_TEMPLATE.format(
        suspected_ae=suspected_ae,
        treatment_modality=treatment_modality,
        recent_treatment_dates=recent_treatment_dates,
        language=language,
    )

    image_part = types.Part.from_bytes(data=jpeg_bytes, mime_type="image/jpeg")
    text_part = types.Part(text=prompt)
    system_part = types.Part(text=SYSTEM_PROMPT)

    try:
        response = await client.aio.models.generate_content(
            model=settings.vision_model,
            contents=[
                types.Content(role="user", parts=[system_part, image_part, text_part])
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.1,
                max_output_tokens=1024,
            ),
        )
    except Exception as exc:
        logger.error("Gemini API error: %s", exc)
        raise RuntimeError(f"Vision API unavailable: {exc}") from exc

    raw_text = response.text
    if not raw_text:
        raise RuntimeError("Empty response from vision model")

    # Strip markdown fences if present
    raw_text = raw_text.strip()
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]

    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Vision model returned invalid JSON: {exc}") from exc

    try:
        return VisualAssessment.model_validate(data)
    except Exception as exc:
        raise RuntimeError(f"Vision response failed schema validation: {exc}") from exc
