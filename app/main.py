import logging
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

from fastapi import Cookie, Depends, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.deps import require_clinician
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_intake import router as intake_router
from app.api.routes_triage import router as triage_router
from app.api.routes_visual_triage import router as visual_triage_router
from app.config import settings
from app.core.i18n import get_dir, get_locale_data
from app.db.database import init_db

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="OncoTriage AI",
    description=(
        "AI-powered oncology symptom triage prototype — COSTaRS v2020 + NCCN guidelines. "
        "NOT a medical device. Portfolio prototype only."
    ),
    version="3.1.0",
    lifespan=lifespan,
    docs_url="/docs" if settings.app_env != "production" else None,
    redoc_url=None,
)

app.include_router(intake_router)
app.include_router(triage_router)
app.include_router(dashboard_router)
app.include_router(visual_triage_router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ── Security headers middleware ────────────────────────────────────────────────
from fastapi import Request as _Request  # noqa: E402


@app.middleware("http")
async def security_headers(request: _Request, call_next):
    response = await call_next(request)
    if not request.url.path.startswith(("/docs", "/redoc", "/openapi.json")):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self' data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self';"
        )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
    if settings.app_env == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# ── Helpers ────────────────────────────────────────────────────────────────────
def _get_lang(lang_cookie: str | None) -> str:
    return lang_cookie if lang_cookie in ("en", "fr", "ar") else "en"


# ── Routes ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def welcome(request: Request, lang: str | None = None, oncotriage_lang: str | None = Cookie(default=None)):
    effective_lang = lang or _get_lang(oncotriage_lang)
    if effective_lang not in ("en", "fr", "ar"):
        effective_lang = "en"
    i18n = get_locale_data(effective_lang)
    return templates.TemplateResponse(
        request=request,
        name="welcome.html",
        context={"lang": effective_lang, "dir": get_dir(effective_lang), "i18n": i18n},
    )


@app.get("/intake", response_class=HTMLResponse, include_in_schema=False)
async def intake(request: Request, lang: str | None = None, oncotriage_lang: str | None = Cookie(default=None)):
    effective_lang = lang or _get_lang(oncotriage_lang)
    i18n = get_locale_data(effective_lang)
    return templates.TemplateResponse(
        request=request,
        name="intake.html",
        context={"lang": effective_lang, "dir": get_dir(effective_lang), "i18n": i18n},
    )


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(
    request: Request,
    oncotriage_lang: str | None = Cookie(default=None),
    _: str = Depends(require_clinician),
):
    lang = _get_lang(oncotriage_lang)
    i18n = get_locale_data(lang)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"lang": lang, "dir": get_dir(lang), "i18n": i18n},
    )


@app.get("/about", response_class=HTMLResponse, include_in_schema=False)
async def about(request: Request, lang: str | None = None, oncotriage_lang: str | None = Cookie(default=None)):
    lang = lang if lang in ("en", "fr", "ar") else _get_lang(oncotriage_lang)
    i18n = get_locale_data(lang)
    return templates.TemplateResponse(
        request=request,
        name="about.html",
        context={"lang": lang, "dir": get_dir(lang), "i18n": i18n},
    )


@app.get("/set-lang/{lang}", include_in_schema=False)
async def set_language(lang: str, request: Request):
    if lang not in ("en", "fr", "ar"):
        lang = "en"
    referer = request.headers.get("referer", "/")
    parsed = urlparse(referer)
    if parsed.netloc and parsed.netloc != request.url.netloc:
        referer = "/"
    response = RedirectResponse(url=referer)
    response.set_cookie(
        "oncotriage_lang",
        lang,
        max_age=31536000,
        httponly=True,
        samesite="lax",
        secure=settings.app_env == "production",
    )
    return response


@app.get("/health")
async def health():
    db_ok = await _check_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": "OncoTriage AI",
        "version": app.version,
        "env": settings.app_env,
        "checks": {"database": db_ok},
    }


async def _check_db() -> bool:
    import aiosqlite
    from app.db.database import DB_PATH
    try:
        async with aiosqlite.connect(DB_PATH) as conn:
            await conn.execute("SELECT 1")
        return True
    except Exception as exc:
        logger.error("DB health check failed: %s", exc)
        return False


# ── Custom error handlers ──────────────────────────────────────────────────────
@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    lang = _get_lang(request.cookies.get("oncotriage_lang"))
    i18n = get_locale_data(lang)
    return templates.TemplateResponse(
        request=request,
        name="errors/404.html",
        context={"lang": lang, "dir": get_dir(lang), "i18n": i18n},
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    lang = _get_lang(request.cookies.get("oncotriage_lang"))
    i18n = get_locale_data(lang)
    return templates.TemplateResponse(
        request=request,
        name="errors/500.html",
        context={"lang": lang, "dir": get_dir(lang), "i18n": i18n},
        status_code=500,
    )
