# OncoTriage AI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/drchikhaoui/oncotriage-ai/actions/workflows/ci.yml/badge.svg)](https://github.com/drchikhaoui/oncotriage-ai/actions/workflows/ci.yml)
[![i18n](https://img.shields.io/badge/i18n-EN%20%7C%20FR%20%7C%20AR-green.svg)](#)

> **Live demo**: *(Railway URL — add after deploy)*
>
> **Status**: Portfolio prototype — NOT a medical device. Educational use only.

OncoTriage AI is an open-source oncology symptom triage prototype designed for under-served linguistic contexts (Arabic, French, English). It implements COSTaRS v2020 clinical decision logic with a privacy-first multimodal AI architecture, demonstrating production-grade engineering patterns in a healthcare context.

---

## Why this project exists

Mainstream oncology digital therapeutics (Resilience, Oleena, Outcomes4Me) are Anglophone-first and lack adaptation for Arabic-speaking populations, despite rising cancer incidence across the MENA region. This prototype demonstrates a culturally-aware, openly-published reference implementation of COSTaRS-based triage logic that researchers and clinicians can extend.

Built as a portfolio project by an MD/MPH candidate to demonstrate clinical informatics and hybrid AI system design.

---

## Engineering Highlights

- **Hybrid AI architecture**: Deterministic COSTaRS rules + Claude NLU + multimodal vision (Gemini / OpenRouter / Groq / Hugging Face)
- **Multi-provider vision fallback chain** with automatic retry, 3-strategy JSON normalization, and transparent provider attribution
- **Privacy by design**: Patient images processed in memory only — never written to disk, database, or logs. EXIF stripped before any external API call.
- **Full i18n with RTL** for Arabic, including patient-friendly clinical language adaptation (no clinical jargon exposed to patients)
- **338 tests** including 25 clinical vignettes covering emergency, urgent, routine, and self-care triage paths
- **Production patterns**: Pydantic v2 schemas, dependency injection, abstracted provider clients, GitHub Actions CI, Docker

---

## Clinical Foundation

This system implements logic from:

| Source | Usage |
|---|---|
| **COSTaRS v2020** (Stacey et al., University of Ottawa) | 17 symptom triage protocols — core decision engine |
| **NCI CTCAE v5.0** | Adverse event grading (Grades 1–4) |
| **NCCN Supportive Care Guidelines v2.2024** | Triage level thresholds |
| **ASCO 2021 irAE Management Guideline** (Schneider et al., JCO) | Immune checkpoint inhibitor toxicity overlay |
| **MASCC/ESMO EGFR Inhibitor Cutaneous Toxicity Recommendations 2018** | Papulopustular eruption management |
| **MASCC/ISOO Mucositis Guidelines** | Oral mucositis management |

COSTaRS content reproduced under CC BY-NC-ND 4.0 with attribution. Clinical content sections retain their original licenses.

---

## Architecture

Four-layer hybrid AI pipeline:

```
Patient input (free text or photo)
        │
        ▼
1. NLU Layer ────────── Anthropic Claude
   Free-text symptom extraction → structured symptoms
   Deterministic fallback when API unavailable
        │
        ▼
2. Clinical Rules ────── COSTaRS v2020 + NCCN + irAE overlay
   CTCAE grading → 4-tier triage (SELF_CARE / ROUTINE / URGENT / EMERGENCY)
   AE-specific guidance (EGFR, HFS, irAE, radiation, mucositis)
        │
        ▼
3. Vision Layer ─────── Multi-provider fallback chain
   Gemini → OpenRouter → Groq → Hugging Face
   CTCAE grading from clinical photos of 6 dermatologic AE categories
        │
        ▼
4. Enrichment ──────── OpenFDA · NCI Thesaurus · PubMed
   Real-world FAERS data, NCI terminology, primary literature citations
```

See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md) for full system design and [`docs/CLINICAL_FOUNDATION.md`](./docs/CLINICAL_FOUNDATION.md) for evidence-base detail.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.10+, FastAPI, Pydantic v2 |
| Frontend | Jinja2, Tailwind CSS, HTMX, Alpine.js (no React) |
| Database | SQLite (dev) / PostgreSQL (prod) |
| AI — NLU | Anthropic Claude (`claude-sonnet-4-6`) |
| AI — Vision | Gemini 2.5 Flash, OpenRouter, Groq, Hugging Face |
| Public APIs | OpenFDA FAERS, NCI Thesaurus EVS, PubMed E-utilities |
| Tests | pytest, 338 tests, 25 clinical vignettes |
| CI/CD | GitHub Actions, Docker, Railway |

---

## Quick Start

```bash
git clone https://github.com/drchikhaoui/oncotriage-ai.git
cd oncotriage-ai

# Install Python + Node dependencies
uv sync --extra dev
npm install && npm run build:css

# Configure environment
cp .env.example .env
# Edit .env — add at least one vision provider key for photo triage
# (GOOGLE_AI_STUDIO_API_KEY is free: https://aistudio.google.com/app/apikey)

# Start the server
uv run uvicorn app.main:app --reload --port 8001
```

| URL | Purpose |
|---|---|
| http://localhost:8001 | Patient symptom intake |
| http://localhost:8001/visual-triage | Photo-based AE grading |
| http://localhost:8001/dashboard | Clinician dashboard |
| http://localhost:8001/docs | FastAPI interactive API docs |

---

## Free Tier Setup

All vision providers have a free tier — no credit card required:

| Provider | Key env var | Free allowance | Get key |
|---|---|---|---|
| Google AI Studio | `GOOGLE_AI_STUDIO_API_KEY` | 1,500 req/day, 15 RPM | [aistudio.google.com](https://aistudio.google.com/app/apikey) |
| Groq | `GROQ_API_KEY` | Generous free tier | [console.groq.com](https://console.groq.com/keys) |
| OpenRouter | `OPENROUTER_API_KEY` | Free tier (gemini-2.5-flash:free) | [openrouter.ai/keys](https://openrouter.ai/keys) |
| Hugging Face | `HUGGINGFACE_API_KEY` | Free inference API | [hf.co/settings/tokens](https://huggingface.co/settings/tokens) |
| Anthropic | `ANTHROPIC_API_KEY` | Paid only | Leave blank — deterministic intake form works without it |

The provider chain is tried in order; any provider without a key is automatically skipped.

---

## Visual Triage Module

Patients photograph skin adverse events on their smartphone; the system returns a CTCAE v5.0 severity assessment and COSTaRS-based triage recommendation in seconds.

**Supported AE categories:**

| AE | Trigger modality | Patient label |
|---|---|---|
| Papulopustular eruption | Targeted therapy (EGFR-TKI) | Pimple-like bumps |
| Hand-foot syndrome | Cytotoxic chemotherapy | Red or painful palms / soles |
| Checkpoint inhibitor dermatitis | Immunotherapy | Spreading rash |
| Radiation dermatitis | Radiation therapy | Skin reaction in radiation area |
| Oral mucositis | Cytotoxic chemotherapy | Mouth sores |
| Not sure | Any / none | I'm not sure what this is |

**Privacy guarantees:**
- Image bytes never written to disk, database, or logs
- EXIF metadata stripped before any external API call
- Thumbnails are ephemeral data URLs — never persisted

---

## Run Tests

```bash
uv run pytest -v        # 338 tests with full output
uv run pytest -q        # summary only
make ci                 # lint (ruff) + tests — matches CI
```

The test suite includes 25 parametrized clinical vignettes covering all four triage levels, irAE escalation paths, and multi-provider vision fallback scenarios.

---

## Deployment

### Railway (one-click)

Set these environment variables in your Railway project:

```
ANTHROPIC_API_KEY=...           # optional — enables LLM symptom extraction
GOOGLE_AI_STUDIO_API_KEY=...    # primary vision provider
APP_ENV=production
DATABASE_URL=...                # Railway PostgreSQL URL (auto-provided)
```

The app runs via `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.

### Docker

```bash
docker build -t oncotriage .
docker run -p 8001:8001 --env-file .env oncotriage
```

---

## Disclaimer

**This is a portfolio prototype, NOT a medical device.** It has not been clinically validated, has no regulatory clearance (FDA, Health Canada, CE), and must not be used for actual patient care decisions. All clinical content is for educational demonstration of clinical informatics system design only.

---

## Acknowledgements

- **Dr. Dawn Stacey** and the COSTaRS team at the University of Ottawa for the open Pan-Canadian Oncology Symptom Triage and Remote Support Practice Guides
- **National Cancer Institute** for CTCAE v5.0, NCI Thesaurus, and PubMed E-utilities
- **U.S. FDA** for the OpenFDA FAERS public API
- This project was developed collaboratively with **Claude Code** (Anthropic) under author direction; clinical decisions, code review, and architecture choices were author-led

---

## License

MIT — see [LICENSE](./LICENSE).

COSTaRS clinical content is reproduced under CC BY-NC-ND 4.0; those sections retain their original license. See [`docs/CLINICAL_FOUNDATION.md`](./docs/CLINICAL_FOUNDATION.md) for attribution details.
