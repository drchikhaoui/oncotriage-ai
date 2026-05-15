import json
from pathlib import Path
from typing import TYPE_CHECKING

import aiosqlite

from app.models.triage import TriageResult

if TYPE_CHECKING:
    from app.models.visual_assessment import VisualTriageResult

DB_PATH = Path(__file__).resolve().parent.parent.parent / "oncotriage.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "schema.sql"


async def init_db() -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA_PATH.read_text())
        # Idempotent migrations for schema upgrades
        for col, definition in [
            ("irae_suspected", "INTEGER NOT NULL DEFAULT 0"),
            ("treatment_modalities", "TEXT"),
            ("is_visual", "INTEGER NOT NULL DEFAULT 0"),
            ("visual_ae_type", "TEXT"),
            ("visual_ctcae_grade", "INTEGER"),
            ("visual_confidence", "TEXT"),
        ]:
            try:
                await db.execute(f"ALTER TABLE triage_sessions ADD COLUMN {col} {definition}")
            except Exception:
                pass
        await db.commit()


async def save_triage_result(result: TriageResult, patient_context: dict) -> None:
    modalities = patient_context.get("treatment_modalities", [])
    modalities_str = json.dumps(modalities) if modalities else None

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO triage_sessions
               (session_id, triage_level, llm_used, irae_suspected, cancer_type,
                treatment_modalities, days_since_chemo, thrombocytopenia_history)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.session_id,
                result.triage_level.value,
                int(result.llm_used),
                int(getattr(result, "irae_suspected", False)),
                patient_context.get("cancer_type"),
                modalities_str,
                patient_context.get("days_since_chemo"),
                int(patient_context.get("thrombocytopenia_history", False)),
            ),
        )
        for gs in result.symptoms_graded:
            await db.execute(
                """INSERT INTO triage_symptoms
                   (session_id, symptom_name, ctcae_grade, severity, ctcae_description)
                   VALUES (?, ?, ?, ?, ?)""",
                (result.session_id, gs["symptom"], gs["ctcae_grade"],
                 gs.get("severity"), gs.get("ctcae_description")),
            )
        for step in result.reasoning_steps:
            if step.source:
                await db.execute(
                    """INSERT INTO triage_rules_fired
                       (session_id, rule_id, rule_name, reasoning, citation)
                       VALUES (?, ?, ?, ?, ?)""",
                    (result.session_id, f"STEP-{step.step}", f"Step {step.step}",
                     step.finding, step.source),
                )
        await db.commit()


async def save_visual_triage_result(result: "VisualTriageResult", patient_context: dict) -> None:
    """Persist visual triage session. Image bytes are NEVER passed here."""
    modalities = patient_context.get("treatment_modalities", [])
    modalities_str = json.dumps(modalities) if modalities else None
    level = result.triage_level.value if result.triage_level else "ROUTINE"
    visual_grade = (
        result.assessment.ctcae_grade_visual.grade
        if result.assessment.ctcae_grade_visual
        else None
    )
    visual_confidence = (
        result.assessment.ctcae_grade_visual.confidence
        if result.assessment.ctcae_grade_visual
        else None
    )

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """INSERT OR REPLACE INTO triage_sessions
               (session_id, triage_level, llm_used, irae_suspected, cancer_type,
                treatment_modalities, days_since_chemo, thrombocytopenia_history,
                is_visual, visual_ae_type, visual_ctcae_grade, visual_confidence)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                result.session_id,
                level,
                0,
                int(result.irae_suspected),
                patient_context.get("cancer_type"),
                modalities_str,
                patient_context.get("days_since_chemo"),
                int(patient_context.get("thrombocytopenia_history", False)),
                1,
                result.suspected_ae,
                visual_grade,
                visual_confidence,
            ),
        )
        for gs in result.graded_symptoms:
            await db.execute(
                """INSERT INTO triage_symptoms
                   (session_id, symptom_name, ctcae_grade, severity, ctcae_description)
                   VALUES (?, ?, ?, ?, ?)""",
                (result.session_id, gs["symptom"], gs["ctcae_grade"],
                 gs.get("severity"), gs.get("ctcae_description")),
            )
        for rule in result.triage_rules:
            await db.execute(
                """INSERT INTO triage_rules_fired
                   (session_id, rule_id, rule_name, reasoning, citation)
                   VALUES (?, ?, ?, ?, ?)""",
                (result.session_id, rule.get("id", "VIS-RULE"),
                 rule.get("name", "Visual Triage Rule"),
                 rule.get("reasoning", ""), rule.get("citation", "")),
            )
        await db.commit()


async def get_recent_triages(limit: int = 50, level_filter: str | None = None) -> list[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        if level_filter:
            cursor = await db.execute(
                "SELECT * FROM triage_sessions WHERE triage_level = ? ORDER BY created_at DESC LIMIT ?",
                (level_filter, limit),
            )
        else:
            cursor = await db.execute(
                "SELECT * FROM triage_sessions ORDER BY created_at DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]


async def get_triage_detail(session_id: str) -> dict | None:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM triage_sessions WHERE session_id = ?", (session_id,)
        )
        session = await cursor.fetchone()
        if not session:
            return None
        cursor = await db.execute(
            "SELECT * FROM triage_symptoms WHERE session_id = ?", (session_id,)
        )
        symptoms = await cursor.fetchall()
        cursor = await db.execute(
            "SELECT * FROM triage_rules_fired WHERE session_id = ?", (session_id,)
        )
        rules = await cursor.fetchall()
        return {
            "session": dict(session),
            "symptoms": [dict(s) for s in symptoms],
            "rules": [dict(r) for r in rules],
        }
