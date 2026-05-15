from datetime import date

from fastapi import APIRouter, HTTPException

from app.core.costars_engine import grade_all
from app.core.explainer import build_reasoning_trace
from app.core.nlu import extract_symptoms_from_text
from app.core.triage_engine import evaluate_symptoms
from app.db.database import save_triage_result
from app.models.patient import PatientContext, TreatmentLine, TreatmentModality
from app.models.symptom import Symptom, SymptomIntakeRequest
from app.models.triage import TriageResult

router = APIRouter(prefix="/api/triage", tags=["triage"])


def _parse_modalities(raw: list[str]) -> list[TreatmentModality]:
    result = []
    for m in raw:
        try:
            result.append(TreatmentModality(m))
        except ValueError:
            pass
    return result


def _parse_treatment_line(raw: str | None) -> TreatmentLine | None:
    if not raw:
        return None
    try:
        return TreatmentLine(raw)
    except ValueError:
        return None


@router.post("/assess", response_model=TriageResult)
async def assess_symptoms(payload: SymptomIntakeRequest) -> TriageResult:
    """
    Main triage endpoint. Accepts free text or structured symptoms.
    Returns 4-tier triage result with full reasoning trace.
    """
    last_chemo: date | None = None
    if payload.last_chemo_date:
        try:
            last_chemo = date.fromisoformat(payload.last_chemo_date)
        except ValueError:
            pass

    patient = PatientContext(
        session_id=payload.session_id,
        cancer_type=payload.cancer_type,
        treatment_modalities=_parse_modalities(payload.treatment_modalities),
        treatment_line=_parse_treatment_line(payload.treatment_line),
        last_chemo_date=last_chemo,
        thrombocytopenia_history=payload.thrombocytopenia_history,
        current_medications=payload.current_medications,
        locale=payload.locale,
    )

    symptoms: list[Symptom] = list(payload.structured_symptoms)
    llm_used = False

    # Layer 1: NLU extraction from free text
    if payload.free_text and not symptoms:
        extracted, llm_used = await extract_symptoms_from_text(payload.free_text)
        if extracted:
            symptoms = extracted

    if not symptoms:
        raise HTTPException(
            status_code=422,
            detail="No symptoms could be extracted. Please use the structured form or provide clearer symptom descriptions.",
        )

    # Layer 2: COSTaRS v2020 grading
    graded = grade_all(symptoms)

    # Layer 3: Regimen-aware triage decision (COSTaRS + irAE overlay)
    triage_level, fired_rules = evaluate_symptoms(graded, patient, payload.free_text)

    # Build explainable result
    result = build_reasoning_trace(
        triage_level=triage_level,
        fired_rules=fired_rules,
        graded_symptoms=graded,
        patient=patient,
        session_id=payload.session_id,
        llm_used=llm_used,
    )

    try:
        await save_triage_result(result, {
            "cancer_type": patient.cancer_type,
            "treatment_modalities": [m.value for m in patient.treatment_modalities],
            "days_since_chemo": patient.days_since_chemo,
            "thrombocytopenia_history": patient.thrombocytopenia_history,
            "irae_suspected": result.irae_suspected,
        })
    except Exception:
        pass

    return result
