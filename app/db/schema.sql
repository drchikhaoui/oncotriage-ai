-- OncoTriage schema v2 — COSTaRS v2020 + irAE support
-- No PHI stored: session_id is anonymous UUID, no patient names/DOB/MRN

CREATE TABLE IF NOT EXISTS triage_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    triage_level TEXT NOT NULL CHECK (triage_level IN ('EMERGENCY','URGENT','ROUTINE','SELF_CARE')),
    llm_used INTEGER NOT NULL DEFAULT 0,
    irae_suspected INTEGER NOT NULL DEFAULT 0,
    cancer_type TEXT,
    treatment_modalities TEXT,
    days_since_chemo INTEGER,
    thrombocytopenia_history INTEGER NOT NULL DEFAULT 0,
    -- Visual triage fields (no image bytes ever stored)
    is_visual INTEGER NOT NULL DEFAULT 0,
    visual_ae_type TEXT,
    visual_ctcae_grade INTEGER CHECK (visual_ctcae_grade BETWEEN 1 AND 4),
    visual_confidence TEXT CHECK (visual_confidence IN ('low','moderate','high'))
);

CREATE TABLE IF NOT EXISTS triage_symptoms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES triage_sessions(session_id) ON DELETE CASCADE,
    symptom_name TEXT NOT NULL,
    ctcae_grade INTEGER CHECK (ctcae_grade BETWEEN 1 AND 5),
    severity TEXT,
    ctcae_description TEXT
);

CREATE TABLE IF NOT EXISTS triage_rules_fired (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES triage_sessions(session_id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    rule_name TEXT NOT NULL,
    reasoning TEXT NOT NULL,
    citation TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_created ON triage_sessions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_level ON triage_sessions(triage_level);
CREATE INDEX IF NOT EXISTS idx_symptoms_session ON triage_symptoms(session_id);
