from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Cookie, FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_intake import router as intake_router
from app.api.routes_triage import router as triage_router
from app.api.routes_visual_triage import router as visual_triage_router
from app.core.i18n import get_dir, get_locale_data
from app.db.database import init_db

STATIC_DIR = Path(__file__).parent / "static"
TEMPLATES_DIR = Path(__file__).parent / "templates"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="OncoTriage AI",
    description="AI-powered oncology symptom triage — COSTaRS v2020 + NCCN guidelines",
    version="3.0.0",
    lifespan=lifespan,
)

app.include_router(intake_router)
app.include_router(triage_router)
app.include_router(dashboard_router)
app.include_router(visual_triage_router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _get_lang(lang_cookie: str | None) -> str:
    return lang_cookie if lang_cookie in ("en", "fr", "ar") else "en"


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def index(request: Request, lang: str | None = None, oncotriage_lang: str | None = Cookie(default=None)):
    effective_lang = lang or _get_lang(oncotriage_lang)
    i18n = get_locale_data(effective_lang)
    return templates.TemplateResponse(
        request=request,
        name="intake.html",
        context={"lang": effective_lang, "dir": get_dir(effective_lang), "i18n": i18n},
    )


@app.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard(request: Request, oncotriage_lang: str | None = Cookie(default=None)):
    lang = _get_lang(oncotriage_lang)
    i18n = get_locale_data(lang)
    return templates.TemplateResponse(
        request=request,
        name="dashboard.html",
        context={"lang": lang, "dir": get_dir(lang), "i18n": i18n},
    )


@app.get("/set-lang/{lang}", include_in_schema=False)
async def set_language(lang: str, request: Request):
    if lang not in ("en", "fr", "ar"):
        lang = "en"
    referer = request.headers.get("referer", "/")
    response = RedirectResponse(url=referer)
    response.set_cookie("oncotriage_lang", lang, max_age=31536000, httponly=True)
    return response


@app.get("/health")
async def health():
    return {"status": "ok", "service": "OncoTriage AI", "version": "2.0.0"}
