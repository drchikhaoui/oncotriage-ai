"""API routes for the visual triage module."""
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import settings
from app.core import visual_triage_engine
from app.core.i18n import get_dir, get_locale_data
from app.db.database import save_visual_triage_result
from app.integrations.vision_providers.base import AllProvidersFailedError, RateLimitError
from app.models.patient import PatientContext, TreatmentModality

router = APIRouter(prefix="/visual-triage", tags=["visual-triage"])
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/heic", "image/heif", "image/webp"}
ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".webp"}


@router.get("", response_class=HTMLResponse)
async def visual_triage_page(
    request: Request,
    lang: str | None = None,
    oncotriage_lang: str | None = Cookie(default=None),
):
    effective_lang = lang or oncotriage_lang or "en"
    if effective_lang not in ("en", "fr", "ar"):
        effective_lang = "en"

    i18n = get_locale_data(effective_lang)
    ae_types = visual_triage_engine._AE_MAP["ae_types"]

    return templates.TemplateResponse(
        request=request,
        name="visual_triage/visual_triage.html",
        context={
            "lang": effective_lang,
            "dir": get_dir(effective_lang),
            "i18n": i18n,
            "ae_types": ae_types,
        },
    )


@router.get("/ae-options")
async def get_ae_options(modalities: str = "") -> list[dict]:
    """Return AE types relevant to the given treatment modalities (comma-separated)."""
    modality_list = [m.strip() for m in modalities.split(",") if m.strip()] if modalities else []
    options = visual_triage_engine.get_available_aes(modality_list)
    return [
        {
            "id": ae["id"],
            "label": ae["label"],
            "description": ae["description"],
            "ctcae_term": ae["ctcae_term"],
        }
        for ae in options
    ]


@router.post("/analyze")
async def analyze_image(
    request: Request,
    image: UploadFile,
    suspected_ae: str = Form(...),
    treatment_modalities: str = Form("[]"),
    cancer_type: str = Form(""),
    last_chemo_date: str = Form(""),
    locale: str = Form("en"),
    session_id: str = Form(""),
    anatomical_location: str = Form(""),
):
    """
    Receive uploaded image, run visual triage pipeline, return VisualTriageResult.
    Image bytes are discarded after processing — never persisted.
    """
    # ── Validate upload ───────────────────────────────────────────────────────
    if image.content_type not in ALLOWED_CONTENT_TYPES:
        ext = Path(image.filename or "").suffix.lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {image.content_type}. Use JPEG, PNG, HEIC, or WebP.",
            )

    image_bytes = await image.read()
    if len(image_bytes) > settings.vision_max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Maximum size is {settings.vision_max_image_bytes // (1024*1024)} MB.",
        )

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file received.")

    # ── Build patient context ─────────────────────────────────────────────────
    try:
        modalities_list = json.loads(treatment_modalities)
    except (json.JSONDecodeError, ValueError):
        modalities_list = []

    parsed_modalities = []
    for m in modalities_list:
        try:
            parsed_modalities.append(TreatmentModality(m))
        except ValueError:
            pass

    from datetime import date
    parsed_chemo_date = None
    if last_chemo_date:
        try:
            parsed_chemo_date = date.fromisoformat(last_chemo_date)
        except ValueError:
            pass

    sid = session_id or str(uuid.uuid4())
    if locale not in ("en", "fr", "ar"):
        locale = "en"

    patient = PatientContext(
        session_id=sid,
        cancer_type=cancer_type or None,
        treatment_modalities=parsed_modalities,
        last_chemo_date=parsed_chemo_date,
        locale=locale,
    )

    # ── Run vision pipeline ───────────────────────────────────────────────────
    if settings.disable_vision:
        raise HTTPException(
            status_code=503,
            detail={
                "error": "vision_disabled",
                "message": "Visual triage is disabled on this server.",
                "retry_after": None,
                "providers_tried": [],
            },
        )

    try:
        result = await visual_triage_engine.analyze_image(
            image_bytes=image_bytes,
            filename=image.filename or "",
            suspected_ae=suspected_ae,
            patient=patient,
            session_id=sid,
            anatomical_location=anatomical_location,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except AllProvidersFailedError as exc:
        # Parse retry_after from the first RateLimitError if present
        retry_after = getattr(exc, "retry_after_seconds", None)
        raise HTTPException(
            status_code=503,
            detail={
                "error": "all_providers_failed",
                "message": "Vision analysis service is temporarily unavailable. Please try again shortly.",
                "retry_after": retry_after,
                "providers_tried": getattr(exc, "errors", []),
            },
        ) from exc

    # ── Persist (no image bytes) ───────────────────────────────────────────────
    await save_visual_triage_result(
        result,
        {
            "cancer_type": patient.cancer_type,
            "treatment_modalities": patient.treatment_modalities_str,
            "days_since_chemo": patient.days_since_chemo,
            "thrombocytopenia_history": False,
        },
    )

    return result.model_dump(mode="json")
