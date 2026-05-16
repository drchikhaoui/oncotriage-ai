"""API routes for the visual triage module."""
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Request, UploadFile
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


def _detect_image_format(b: bytes) -> str | None:
    """Magic-byte detection — does not trust client-supplied content-type."""
    if b[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if len(b) > 12 and b[4:12] in (
        b"ftypheic", b"ftypheix", b"ftyphevc",
        b"ftypheim", b"ftyphevm", b"ftypmif1",
    ):
        return "heic"
    return None


def _require_vision_enabled():
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
    ae_types = visual_triage_engine.get_all_aes()

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
        }
        for ae in options
    ]


@router.post("/analyze", dependencies=[Depends(_require_vision_enabled)])
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
    thrombocytopenia_history: str = Form("false"),
):
    """
    Receive uploaded image, run visual triage pipeline, return VisualTriageResult.
    Image bytes are discarded after processing — never persisted.
    """
    image_bytes = await image.read()
    if len(image_bytes) > settings.vision_max_image_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Image too large. Maximum size is {settings.vision_max_image_bytes // (1024*1024)} MB.",
        )

    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty image file received.")

    # ── Magic-byte image validation ───────────────────────────────────────────
    detected = _detect_image_format(image_bytes)
    if detected is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid image: not a supported format (JPEG/PNG/WebP/HEIC).",
        )

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
            "thrombocytopenia_history": thrombocytopenia_history.lower() == "true",
        },
    )

    return result.model_dump(mode="json")
