"""
Seed the database with realistic demo triage sessions for dashboard preview.
Run: uv run python scripts/seed_demo_data.py
"""
import asyncio
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.costars_engine import grade_all
from app.core.explainer import build_reasoning_trace
from app.core.triage_engine import evaluate_symptoms
from app.db.database import init_db, save_triage_result
from app.models.patient import PatientContext, TreatmentModality
from app.models.symptom import CTCAEGrade, Symptom, SymptomName

DEMO_CASES = [
    # ── Emergency cases ──────────────────────────────────────────────────────
    {
        "symptoms": [Symptom(name=SymptomName.FEVER, temperature_celsius=38.7, duration_hours=2)],
        "cancer_type": "AML",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": 6,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.FEVER, temperature_celsius=38.1, duration_hours=1.5)],
        "cancer_type": "Breast",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": 10,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.DYSPNEA, at_rest=True, onset="sudden")],
        "cancer_type": "Lung (NSCLC)",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.PAIN, pain_nrs=10, severity_descriptor="severe")],
        "cancer_type": "Bone metastasis (Prostate)",
        "modalities": [TreatmentModality.HORMONAL],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.FEVER, temperature_celsius=38.4, duration_hours=3)],
        "cancer_type": "DLBCL",
        "modalities": [TreatmentModality.CAR_T],
        "chemo_days_ago": 15,
        "thrombocytopenia": False,
    },
    # ── irAE emergency cases ─────────────────────────────────────────────────
    {
        "symptoms": [Symptom(name=SymptomName.DIARRHEA, ctcae_grade=CTCAEGrade.GRADE_4, severity_descriptor="severe",
                             descriptors=["rectal bleeding", "abdominal distension"])],
        "cancer_type": "Urothelial",
        "modalities": [TreatmentModality.IMMUNOTHERAPY],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_3, severity_descriptor="severe",
                             descriptors=["blistering", "mucous membrane involvement"])],
        "cancer_type": "Renal Cell Carcinoma",
        "modalities": [TreatmentModality.IMMUNOTHERAPY],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.PAIN, severity_descriptor="moderate",
                             descriptors=["chest pain", "palpitations", "racing heart"])],
        "cancer_type": "Lymphoma",
        "modalities": [TreatmentModality.IMMUNOTHERAPY],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    # ── Urgent cases ─────────────────────────────────────────────────────────
    {
        "symptoms": [Symptom(name=SymptomName.VOMITING, episodes_per_24h=7, severity_descriptor="severe")],
        "cancer_type": "Colorectal",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": 3,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.BLEEDING, ctcae_grade=CTCAEGrade.GRADE_1, severity_descriptor="mild",
                             descriptors=["petechiae", "bruising"])],
        "cancer_type": "AML",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": None,
        "thrombocytopenia": True,
    },
    {
        "symptoms": [Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=8, severity_descriptor="severe")],
        "cancer_type": "Colon",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": 14,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.MUCOSITIS, ctcae_grade=CTCAEGrade.GRADE_3, severity_descriptor="severe",
                             descriptors=["unable to swallow"])],
        "cancer_type": "Head and Neck",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO, TreatmentModality.RADIATION],
        "chemo_days_ago": 5,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5, severity_descriptor="moderate")],
        "cancer_type": "NSCLC",
        "modalities": [TreatmentModality.IMMUNOTHERAPY],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.DYSPNEA, severity_descriptor="mild", at_rest=False,
                             descriptors=["dry cough", "exertional", "new onset"])],
        "cancer_type": "Melanoma",
        "modalities": [TreatmentModality.IMMUNOTHERAPY],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.PAIN, pain_nrs=8, uncontrolled=True, severity_descriptor="severe",
                             descriptors=["bone pain", "hip", "not responding to opioids"])],
        "cancer_type": "Breast (bone mets)",
        "modalities": [TreatmentModality.HORMONAL],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.ANXIETY, ctcae_grade=CTCAEGrade.GRADE_3, severity_descriptor="severe",
                             descriptors=["panic attacks", "unable to function"])],
        "cancer_type": "Lung",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": None,
        "thrombocytopenia": False,
    },
    # ── Routine cases ─────────────────────────────────────────────────────────
    {
        "symptoms": [Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_2, severity_descriptor="moderate")],
        "cancer_type": "Breast",
        "modalities": [],
        "chemo_days_ago": 90,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.PERIPHERAL_NEUROPATHY, ctcae_grade=CTCAEGrade.GRADE_2,
                             severity_descriptor="moderate", descriptors=["numbness", "hands and feet"])],
        "cancer_type": "Ovarian",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": 7,
        "thrombocytopenia": False,
    },
    # ── Self-care cases ───────────────────────────────────────────────────────
    {
        "symptoms": [Symptom(name=SymptomName.NAUSEA, ctcae_grade=CTCAEGrade.GRADE_1, severity_descriptor="mild")],
        "cancer_type": "Lymphoma",
        "modalities": [TreatmentModality.CYTOTOXIC_CHEMO],
        "chemo_days_ago": 7,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.XEROSTOMIA, ctcae_grade=CTCAEGrade.GRADE_1, severity_descriptor="mild",
                             descriptors=["dry mouth", "needs liquids with meals"])],
        "cancer_type": "Head and Neck",
        "modalities": [TreatmentModality.RADIATION],
        "chemo_days_ago": 30,
        "thrombocytopenia": False,
    },
    {
        "symptoms": [Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_1, severity_descriptor="mild")],
        "cancer_type": "Breast",
        "modalities": [],
        "chemo_days_ago": 180,
        "thrombocytopenia": False,
    },
]


async def seed():
    await init_db()
    print("Seeding demo triage data...")
    total = len(DEMO_CASES)
    for i, case in enumerate(DEMO_CASES):
        chemo_date = (date.today() - timedelta(days=case["chemo_days_ago"])) if case["chemo_days_ago"] else None
        patient = PatientContext(
            session_id=str(uuid.uuid4()),
            cancer_type=case["cancer_type"],
            treatment_modalities=case["modalities"],
            last_chemo_date=chemo_date,
            thrombocytopenia_history=case["thrombocytopenia"],
        )
        graded = grade_all(case["symptoms"])
        level, rules = evaluate_symptoms(graded, patient)
        result = build_reasoning_trace(
            triage_level=level,
            fired_rules=rules,
            graded_symptoms=graded,
            patient=patient,
            session_id=patient.session_id,
            llm_used=False,
        )
        modalities_str = [m.value for m in case["modalities"]]
        await save_triage_result(result, {
            "cancer_type": patient.cancer_type,
            "treatment_modalities": modalities_str,
            "days_since_chemo": patient.days_since_chemo,
            "thrombocytopenia_history": patient.thrombocytopenia_history,
        })
        irae_flag = " [irAE]" if getattr(result, "irae_suspected", False) else ""
        print(f"  [{i+1:2d}/{total}] {level.value:12s} — {case['cancer_type']}{irae_flag}")

    print(f"\nDone. Seeded {total} cases. Visit http://localhost:8001/dashboard")


if __name__ == "__main__":
    asyncio.run(seed())
