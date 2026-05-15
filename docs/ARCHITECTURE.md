# Architecture — OncoTriage AI

## System Design

```
┌─────────────────────────────────────────────────────────┐
│  PATIENT INPUT                                          │
│  Free text OR structured form (fallback)                │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  LAYER 1: LLM-based NLU      │  Claude (claude-sonnet-4-6)
        │  app/core/nlu.py             │  Structured JSON extraction
        │                              │  Graceful fallback if unavailable
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  LAYER 2: CTCAE Grading      │  Deterministic
        │  app/core/ctcae_engine.py    │  NCI CTCAE v5.0 thresholds
        │                              │  10 symptom domains
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  LAYER 3: Triage Engine      │  Deterministic
        │  app/core/triage_engine.py   │  NCCN guideline rules
        │                              │  Red-flag combination logic
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  Explainer                   │  Auditable
        │  app/core/explainer.py       │  Step-by-step reasoning trace
        │                              │  Citations per finding
        └──────────────┬───────────────┘
                       │
                       ▼
        ┌──────────────────────────────┐
        │  OUTPUT: 4-tier triage       │
        │  🔴 EMERGENCY                 │
        │  🟠 URGENT                    │
        │  🟡 ROUTINE                   │
        │  🟢 SELF-CARE                 │
        │  + Reasoning trace            │
        │  + CTCAE grade summary        │
        │  + Citations                  │
        └──────────────────────────────┘
```

## Data Flow

1. **Patient** opens `localhost:8000` → enters free text or selects structured symptoms
2. **Frontend** (`app.js`) calls `GET /api/intake/session` → gets anonymous `session_id`
3. **Frontend** calls `POST /api/triage/assess` with payload
4. **`routes_triage.py`** orchestrates:
   - Builds `PatientContext` from payload
   - Calls `nlu.py` if free text present (LLM layer)
   - Calls `ctcae_engine.grade_all()` (deterministic grading)
   - Calls `triage_engine.evaluate_symptoms()` (rule-based decisions)
   - Calls `explainer.build_reasoning_trace()` (step-by-step output)
   - Saves to SQLite via `database.save_triage_result()`
5. **Frontend** renders color-coded triage card + reasoning

## File Structure

```
oncotriage/
├── pyproject.toml              # uv/PEP 517 project definition
├── .env.example                # Environment variable template
├── oncotriage.db               # SQLite database (auto-created on first run)
├── app/
│   ├── main.py                 # FastAPI app, lifespan, routing
│   ├── config.py               # Pydantic settings (reads .env)
│   ├── models/
│   │   ├── patient.py          # PatientContext (anonymous, no PHI)
│   │   ├── symptom.py          # Symptom, SymptomIntakeRequest, enums
│   │   └── triage.py           # TriageResult, TriageLevel, ReasoningStep
│   ├── core/
│   │   ├── nlu.py              # Claude API — symptom extraction
│   │   ├── ctcae_engine.py     # CTCAE v5.0 grading logic
│   │   ├── triage_engine.py    # NCCN-based triage rules
│   │   └── explainer.py        # Reasoning trace generator
│   ├── data/
│   │   ├── ctcae_v5.json       # CTCAE criteria KB (10 symptoms, 5 grades each)
│   │   ├── nccn_rules.json     # Triage rules with citations
│   │   └── red_flags.json      # Critical symptom combinations
│   ├── db/
│   │   ├── schema.sql          # DDL (SQLite, Postgres-portable)
│   │   └── database.py         # aiosqlite CRUD layer
│   ├── api/
│   │   ├── routes_intake.py    # /api/intake — session, symptom list
│   │   ├── routes_triage.py    # /api/triage/assess — main endpoint
│   │   └── routes_dashboard.py # /api/dashboard — clinician view
│   └── static/
│       ├── index.html          # Patient intake page
│       ├── dashboard.html      # Clinician dashboard
│       ├── styles.css          # Medical-grade UI
│       └── app.js              # Frontend logic (no framework)
├── tests/
│   ├── test_ctcae_engine.py    # CTCAE grading unit tests
│   ├── test_triage_engine.py   # 15 clinical vignette integration tests
│   └── clinical_vignettes.json # Test cases with expected outcomes
└── docs/
    ├── CLINICAL_FOUNDATION.md  # Evidence base, citations
    └── ARCHITECTURE.md         # This file
```

## Key Design Decisions

### Hybrid AI Architecture
The LLM (Claude) is used only for natural language understanding — converting free text to structured symptom objects. All clinical decisions are deterministic rule-based logic derived from guidelines. This ensures:
- **Auditability**: Every triage decision has a traceable rule ID and guideline citation
- **Reliability**: Works without LLM (fallback to structured form)
- **Regulatory viability**: Deterministic clinical logic is required for FDA SaMD submission

### HIPAA-by-Design
- No PHI fields in the database schema
- Raw free text is processed but never persisted
- Session IDs are UUIDs with no linking to identity
- LLM prompts contain only anonymized symptom descriptions

### Escalation Logic
The triage engine uses a priority ladder — each symptom evaluation can only escalate (never de-escalate) the triage level. The final level is always the highest triggered:
```
SELF_CARE < ROUTINE < URGENT < EMERGENCY
```

---

## Future Roadmap

### Sprint 2 — Wearable Integration
- **Empatica E4/E4 Connect**: REST API for EDA, BVP, temperature, accelerometer data
- **HealthKit** (iOS): Passive heart rate, SpO2, activity via Core Motion
- **Movesense**: ECG, IMU via Bluetooth SDK
- Wearable data used to: (1) detect resting tachycardia (HR >100 suggesting sepsis), (2) continuous temperature trending, (3) activity decline as fatigue proxy

### Sprint 3 — Localization
- Arabic (RTL layout, MSA medical terminology)
- French (tailored for North African and sub-Saharan Francophone oncology patients)
- i18n via `babel` or `gettext`

### Sprint 4 — Native iOS App
- SwiftUI frontend connecting to FastAPI backend (localhost or cloud)
- Local deterministic triage engine in Swift (offline capability)
- HealthKit integration for passive wearable data
- TrollStore for sideloading during development/pilot

### Sprint 5 — FDA SaMD Pathway
- Software as a Medical Device (SaMD) classification analysis
- Intended use: Clinical Decision Support Software (CDSS)
- Regulatory class: Likely Class II (510(k)) — Non-Significant Risk
- Pre-submission meeting with FDA CDRH
- Prospective validation study (IRB → 200+ patient pilot at oncology center)
- De-identification via HIPAA Safe Harbor or Expert Determination

### Sprint 6 — Cloud Deployment
- Docker containerization
- PostgreSQL migration (schema is already Postgres-portable)
- HIPAA-eligible cloud: AWS GovCloud / Azure Government / Google Cloud Healthcare API
- End-to-end encryption, access controls, audit logging

---

## API Reference

### POST /api/triage/assess
**Request body:** `SymptomIntakeRequest`
```json
{
  "session_id": "uuid",
  "free_text": "I have a fever of 38.7°C...",
  "structured_symptoms": [],
  "last_chemo_date": "2024-05-01",
  "thrombocytopenia_history": false,
  "cancer_type": "Breast",
  "treatment_status": "active_treatment",
  "current_medications": []
}
```

**Response:** `TriageResult`
```json
{
  "triage_level": "EMERGENCY",
  "emoji": "🔴",
  "action": "Call 911 or go to the nearest Emergency Department immediately.",
  "reasoning_steps": [...],
  "triggered_rules": ["FN-001"],
  "citations": ["NCCN v2.2024", "CTCAE v5.0"],
  "symptoms_graded": [...],
  "llm_used": true
}
```

### GET /api/dashboard/recent?level=EMERGENCY&limit=50
Returns recent triage sessions, filterable by level.

### GET /api/dashboard/stats
Returns aggregate counts by triage level.

---

*Built by an MD/MPH with expertise in oncology, cancer epidemiology, and wearable sensor research.*
