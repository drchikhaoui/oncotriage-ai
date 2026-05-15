# OncoTriage AI

AI-powered oncology symptom triage — CTCAE v5.0 + NCCN guidelines + visual AE grading.

## Quick Start

```bash
cd ~/oncotriage

# Install dependencies
uv sync --extra dev

# Copy and configure environment
cp .env.example .env
# Edit .env — add ANTHROPIC_API_KEY (optional) and GOOGLE_AI_STUDIO_API_KEY (for photo triage)

# Start the server
uv run uvicorn app.main:app --reload
```

Open http://localhost:8000 — patient symptom intake  
Open http://localhost:8000/visual-triage — photo-based AE grading  
Open http://localhost:8000/dashboard — clinician dashboard  
Open http://localhost:8000/docs — FastAPI interactive API docs

## Run Tests

```bash
uv run pytest -v       # 251 tests
uv run pytest -q       # summary only
```

## Architecture

Four-layer hybrid AI:

1. **LLM (Claude)** — natural language symptom extraction from free text
2. **CTCAE Engine** — deterministic NCI CTCAE v5.0 grading
3. **Triage Engine** — NCCN guideline-based 4-tier decision (SELF_CARE → ROUTINE → URGENT → EMERGENCY)
4. **Vision Engine** — Gemini 2.0 Flash CTCAE grading from clinical photographs (Sprint 3)

See `docs/ARCHITECTURE.md` and `docs/CLINICAL_FOUNDATION.md` for full documentation.

## Visual Triage Module (Sprint 3)

Patients photograph skin adverse events on their smartphone; the system returns a CTCAE v5.0 grade and COSTaRS-based triage recommendation in seconds.

**Supported AE types:**

| AE | Trigger modality | IDs |
|---|---|---|
| EGFR-TKI papulopustular eruption | Targeted therapy | `papulopustular_eruption` |
| Hand-foot syndrome | Cytotoxic chemo | `hand_foot_syndrome` |
| Checkpoint inhibitor dermatitis | Immunotherapy | `checkpoint_dermatitis` |
| Radiation dermatitis | Radiation | `radiation_dermatitis` |
| Oral mucositis | Cytotoxic chemo | `oral_mucositis` |

**Privacy guarantees:**
- Image bytes are **never written to disk, database, or logs**
- EXIF metadata stripped before any external API call
- Thumbnails are ephemeral base64 data URLs (response only, never persisted)

**Required environment variable:**
```
GOOGLE_AI_STUDIO_API_KEY=...   # free tier: 1,500 requests/day
```

Get a free key at [Google AI Studio](https://aistudio.google.com/apikey).

## Public API Attribution

- **[OpenFDA FAERS](https://open.fda.gov/apis/drug/event/)** — FDA adverse event reporting system (no auth required)
- **[NCI Thesaurus EVS REST API](https://api-evsrest.nci.nih.gov/)** — NCI controlled vocabulary (pre-seeded local cache)
- **[PubMed E-utilities](https://www.ncbi.nlm.nih.gov/books/NBK25500/)** — NCBI literature search (no auth required)

## Evidence Base

- NCI CTCAE v5.0 (2017)
- NCCN Clinical Practice Guidelines v2.2024
- ESMO Supportive Care Guidelines
- ASCO Clinical Practice Guidelines
- COSTaRS (Cancer Symptom Management Practices) v2020

**Disclaimer:** For clinical decision support only. Does not replace clinical judgment.

## Deployment (Railway)

Set these environment variables in your Railway project:

```
ANTHROPIC_API_KEY=...           # optional — enables LLM symptom extraction
GOOGLE_AI_STUDIO_API_KEY=...    # required for photo triage
APP_ENV=production
DISABLE_VISION=false
```

The application runs via `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
