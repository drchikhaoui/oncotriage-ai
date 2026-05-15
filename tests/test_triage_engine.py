"""
Clinical vignette tests — validates triage decisions against expected outcomes.
Each test uses deterministic rules only (no LLM dependency).
"""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from app.core.costars_engine import grade_all
from app.core.triage_engine import evaluate_symptoms
from app.models.patient import PatientContext, TreatmentModality
from app.models.symptom import CTCAEGrade, Symptom, SymptomName
from app.models.triage import TriageLevel

VIGNETTES_PATH = Path(__file__).parent / "clinical_vignettes.json"
with open(VIGNETTES_PATH) as f:
    VIGNETTES = json.load(f)


def build_patient(v_input: dict) -> PatientContext:
    offset = v_input.get("last_chemo_date_offset_days")
    last_chemo = date.today() - timedelta(days=offset) if offset is not None else None

    modalities = []
    for m in v_input.get("treatment_modalities", []):
        try:
            modalities.append(TreatmentModality(m))
        except ValueError:
            pass

    return PatientContext(
        session_id="test-session",
        cancer_type=v_input.get("cancer_type"),
        treatment_modalities=modalities,
        last_chemo_date=last_chemo,
        thrombocytopenia_history=v_input.get("thrombocytopenia_history", False),
        locale=v_input.get("locale", "en"),
    )


def build_symptoms(symptom_dicts: list[dict]) -> list[Symptom]:
    symptoms = []
    for d in symptom_dicts:
        d = dict(d)
        name_raw = d.pop("name", "other")
        try:
            name = SymptomName(name_raw)
        except ValueError:
            name = SymptomName.OTHER
        grade_val = d.pop("ctcae_grade", None)
        ctcae_grade = CTCAEGrade(grade_val) if grade_val else None
        symptoms.append(Symptom(name=name, ctcae_grade=ctcae_grade, **d))
    return symptoms


def run_vignette(vignette: dict) -> tuple[TriageLevel, list[str]]:
    inp = {k: v for k, v in vignette["input"].items()}
    symptom_dicts = [dict(s) for s in inp.pop("structured_symptoms")]
    patient = build_patient(inp)
    symptoms = build_symptoms(symptom_dicts)
    graded = grade_all(symptoms)
    level, rules = evaluate_symptoms(graded, patient)
    return level, [r["id"] for r in rules]


@pytest.mark.parametrize("vignette", VIGNETTES, ids=[v["id"] for v in VIGNETTES])
def test_vignette_triage_level(vignette):
    """Each vignette must produce the expected triage level."""
    level, rule_ids = run_vignette(vignette)
    expected = TriageLevel(vignette["expected_triage_level"])
    assert level == expected, (
        f"[{vignette['id']}] {vignette['name']}\n"
        f"  Expected: {expected}\n"
        f"  Got:      {level}\n"
        f"  Rules fired: {rule_ids}\n"
        f"  Rationale: {vignette['rationale']}"
    )


@pytest.mark.parametrize("vignette", VIGNETTES, ids=[v["id"] for v in VIGNETTES])
def test_vignette_rules_fired(vignette):
    """At least one of the expected rules must fire for each vignette."""
    level, rule_ids = run_vignette(vignette)
    expected_rules = vignette.get("expected_rules", [])
    if not expected_rules:
        return
    matched = any(r in rule_ids for r in expected_rules)
    assert matched, (
        f"[{vignette['id']}] Expected one of {expected_rules} to fire, got {rule_ids}"
    )


class TestFebrileNeutropenia:
    def test_38_3c_cytotoxic_is_emergency(self):
        patient = PatientContext(
            session_id="t1",
            treatment_modalities=[TreatmentModality.CYTOTOXIC_CHEMO],
            last_chemo_date=date.today() - timedelta(days=7),
        )
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.3)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.EMERGENCY

    def test_38_3c_no_chemo_is_not_fn(self):
        patient = PatientContext(session_id="t2")
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.3)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level != TriageLevel.EMERGENCY

    def test_14_day_boundary_included(self):
        patient = PatientContext(
            session_id="t3",
            treatment_modalities=[TreatmentModality.CYTOTOXIC_CHEMO],
            last_chemo_date=date.today() - timedelta(days=14),
        )
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.EMERGENCY

    def test_15_days_post_chemo_not_fn(self):
        patient = PatientContext(
            session_id="t4",
            treatment_modalities=[TreatmentModality.CYTOTOXIC_CHEMO],
            last_chemo_date=date.today() - timedelta(days=15),
        )
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level != TriageLevel.EMERGENCY

    def test_legacy_mode_no_modalities_triggers_fn(self):
        """Backward compat: if no modalities but last_chemo_date set, FN should fire."""
        patient = PatientContext(
            session_id="t-legacy",
            last_chemo_date=date.today() - timedelta(days=7),
        )
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.EMERGENCY


class TestCarTCRS:
    def test_fever_day20_cart_is_emergency(self):
        patient = PatientContext(
            session_id="crt1",
            treatment_modalities=[TreatmentModality.CAR_T],
            last_chemo_date=date.today() - timedelta(days=20),
        )
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.2)
        graded = grade_all([s])
        level, rules = evaluate_symptoms(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert level == TriageLevel.EMERGENCY
        assert "FN-CAR-T" in rule_ids

    def test_fever_day31_cart_not_crs(self):
        """Day 31 post-CAR-T: 30-day window expired, normal FN logic applies."""
        patient = PatientContext(
            session_id="crt2",
            treatment_modalities=[TreatmentModality.CAR_T],
            last_chemo_date=date.today() - timedelta(days=31),
        )
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        graded = grade_all([s])
        level, rules = evaluate_symptoms(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "FN-CAR-T" not in rule_ids


class TestIrAE:
    def test_diarrhea_g2_immunotherapy_is_urgent(self):
        """Grade 2 diarrhea with immunotherapy must escalate to URGENT (irAE colitis)."""
        patient = PatientContext(
            session_id="irae1",
            treatment_modalities=[TreatmentModality.IMMUNOTHERAPY],
        )
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.URGENT

    def test_diarrhea_g2_no_immunotherapy_is_routine(self):
        """Grade 2 diarrhea without immunotherapy stays ROUTINE."""
        patient = PatientContext(session_id="irae2")
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.ROUTINE

    def test_any_dyspnea_immunotherapy_triggers_irae(self):
        """Any dyspnea with immunotherapy fires pneumonitis irAE rule."""
        patient = PatientContext(
            session_id="irae3",
            treatment_modalities=[TreatmentModality.IMMUNOTHERAPY],
        )
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="mild")
        graded = grade_all([s])
        level, rules = evaluate_symptoms(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "pneumonitis_any_grade_immunotherapy" in rule_ids
        assert level == TriageLevel.URGENT

    def test_skin_rash_g3_immunotherapy_is_emergency(self):
        """Grade 3 skin rash with immunotherapy = irAE dermatitis (SJS/TEN must be excluded = EMERGENCY)."""
        patient = PatientContext(
            session_id="irae4",
            treatment_modalities=[TreatmentModality.IMMUNOTHERAPY],
        )
        s = Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_3)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.EMERGENCY

    def test_no_irae_without_immunotherapy(self):
        """irAE engine must not fire without immunotherapy in treatment modalities."""
        from app.core.irae_engine import evaluate_irae
        patient = PatientContext(session_id="irae5")
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        graded = grade_all([s])
        irae_rules = evaluate_irae(graded, patient)
        assert irae_rules == []


class TestHighestLevelWins:
    def test_emergency_overrides_self_care(self):
        patient = PatientContext(
            session_id="t5",
            treatment_modalities=[TreatmentModality.CYTOTOXIC_CHEMO],
            last_chemo_date=date.today() - timedelta(days=8),
        )
        symptoms = [
            Symptom(name=SymptomName.FEVER, temperature_celsius=38.7),
            Symptom(name=SymptomName.NAUSEA, ctcae_grade=CTCAEGrade.GRADE_1),
            Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_1),
        ]
        graded = grade_all(symptoms)
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.EMERGENCY

    def test_urgent_overrides_routine(self):
        patient = PatientContext(session_id="t6")
        symptoms = [
            Symptom(name=SymptomName.VOMITING, episodes_per_24h=7),
            Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_3),
        ]
        graded = grade_all(symptoms)
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.URGENT


class TestDyspnea:
    def test_at_rest_is_emergency(self):
        patient = PatientContext(session_id="t7")
        s = Symptom(name=SymptomName.DYSPNEA, at_rest=True)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.EMERGENCY

    def test_moderate_dyspnea_is_urgent(self):
        patient = PatientContext(session_id="t8")
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="moderate")
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.URGENT


class TestPain:
    def test_grade4_pain_is_emergency(self):
        patient = PatientContext(session_id="p1")
        s = Symptom(name=SymptomName.PAIN, pain_nrs=10)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.EMERGENCY

    def test_grade3_pain_is_urgent_not_emergency(self):
        """Per NCCN Adult Cancer Pain: Grade 3 uncontrolled = URGENT, not EMERGENCY."""
        patient = PatientContext(session_id="p2")
        s = Symptom(name=SymptomName.PAIN, pain_nrs=8, uncontrolled=True)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.URGENT
        assert level != TriageLevel.EMERGENCY


class TestKeywordEscalation:
    def test_cant_breathe_escalates(self):
        from app.core.triage_engine import check_immediate_escalation_keywords
        found, kws = check_immediate_escalation_keywords("I can't breathe and feel very sick")
        assert found is True
        assert "can't breathe" in kws

    def test_normal_text_no_escalation(self):
        from app.core.triage_engine import check_immediate_escalation_keywords
        found, _ = check_immediate_escalation_keywords("I have mild nausea after chemo")
        assert found is False


class TestNewCOSTaRSSymptoms:
    def test_severe_anxiety_is_urgent(self):
        patient = PatientContext(session_id="new1")
        s = Symptom(name=SymptomName.ANXIETY, ctcae_grade=CTCAEGrade.GRADE_3)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.URGENT

    def test_severe_skin_rash_is_urgent(self):
        patient = PatientContext(session_id="new2")
        s = Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_3)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.URGENT

    def test_severe_anorexia_is_urgent(self):
        patient = PatientContext(session_id="new3")
        s = Symptom(name=SymptomName.ANOREXIA, ctcae_grade=CTCAEGrade.GRADE_3)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.URGENT

    def test_grade1_xerostomia_is_selfcare(self):
        patient = PatientContext(session_id="new4")
        s = Symptom(name=SymptomName.XEROSTOMIA, ctcae_grade=CTCAEGrade.GRADE_1)
        graded = grade_all([s])
        level, _ = evaluate_symptoms(graded, patient)
        assert level == TriageLevel.SELF_CARE
