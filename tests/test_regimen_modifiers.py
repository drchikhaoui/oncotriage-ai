"""
Regimen modifier tests — validates treatment-modality-specific triage escalations.
Covers: CAR-T CRS window, SCT GvHD escalation, immunotherapy irAE overlay,
targeted/hormonal/radiation baseline behaviour, and legacy mode backward compat.
"""
from datetime import date, timedelta

from app.core.costars_engine import grade_all
from app.core.triage_engine import evaluate_symptoms
from app.models.patient import PatientContext, TreatmentModality
from app.models.symptom import CTCAEGrade, Symptom, SymptomName
from app.models.triage import TriageLevel


def _patient(
    modalities: list[TreatmentModality] | None = None,
    days_since_chemo: int | None = None,
    thrombocytopenia: bool = False,
    cancer_type: str | None = None,
) -> PatientContext:
    last_chemo = date.today() - timedelta(days=days_since_chemo) if days_since_chemo is not None else None
    return PatientContext(
        session_id="regimen-test",
        treatment_modalities=modalities or [],
        last_chemo_date=last_chemo,
        thrombocytopenia_history=thrombocytopenia,
        cancer_type=cancer_type,
    )


# ─── CAR-T / CRS ───────────────────────────────────────────────────────────────

class TestCarTCRSWindow:
    def test_day1_fever_is_emergency(self):
        """Day 1 post-infusion: any fever = CRS risk."""
        patient = _patient([TreatmentModality.CAR_T], days_since_chemo=1)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.1)
        level, rules = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY
        assert any(r["id"] == "FN-CAR-T" for r in rules)

    def test_day30_fever_is_emergency(self):
        """Day 30 is the last day of the 30-day window — still EMERGENCY."""
        patient = _patient([TreatmentModality.CAR_T], days_since_chemo=30)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.3)
        level, rules = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY
        assert any(r["id"] == "FN-CAR-T" for r in rules)

    def test_day31_fever_not_crs(self):
        """Day 31: 30-day window expired; CAR-T specific rule should NOT fire."""
        patient = _patient([TreatmentModality.CAR_T], days_since_chemo=31)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        _, rules = evaluate_symptoms(grade_all([s]), patient)
        assert not any(r["id"] == "FN-CAR-T" for r in rules)

    def test_sct_day20_fever_is_emergency(self):
        """SCT also has the 30-day CRS window."""
        patient = _patient([TreatmentModality.STEM_CELL_TRANSPLANT], days_since_chemo=20)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.4)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY

    def test_cart_no_fever_no_crs_rule(self):
        """CAR-T patient without fever — CRS rule must not fire."""
        patient = _patient([TreatmentModality.CAR_T], days_since_chemo=10)
        s = Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_2)
        _, rules = evaluate_symptoms(grade_all([s]), patient)
        assert not any(r["id"] == "FN-CAR-T" for r in rules)


# ─── Cytotoxic FN Window ────────────────────────────────────────────────────────

class TestCytotoxicFNWindow:
    def test_day14_is_inside_window(self):
        patient = _patient([TreatmentModality.CYTOTOXIC_CHEMO], days_since_chemo=14)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.3)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY

    def test_day15_is_outside_window(self):
        patient = _patient([TreatmentModality.CYTOTOXIC_CHEMO], days_since_chemo=15)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.3)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level != TriageLevel.EMERGENCY

    def test_sustained_low_fever_day10(self):
        """38.0°C sustained ≥1h within 14 days = alternate FN criterion."""
        patient = _patient([TreatmentModality.CYTOTOXIC_CHEMO], days_since_chemo=10)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.1, duration_hours=1.5)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY

    def test_radiation_only_no_fn_rule(self):
        """Radiation-only patients: fever does not trigger the chemo-specific FN rule."""
        patient = _patient([TreatmentModality.RADIATION], days_since_chemo=5)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        _, rules = evaluate_symptoms(grade_all([s]), patient)
        fn_rules = [r["id"] for r in rules if r["id"].startswith("FN")]
        # Radiation alone should not fire cytotoxic FN rule
        assert "FN-001" not in fn_rules
        assert "FN-002" not in fn_rules


# ─── Legacy Mode ───────────────────────────────────────────────────────────────

class TestLegacyMode:
    def test_no_modalities_with_chemo_date_triggers_fn(self):
        """Backward compat: empty treatment_modalities + last_chemo_date → assume cytotoxic."""
        patient = _patient(modalities=[], days_since_chemo=7)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY

    def test_no_modalities_no_chemo_date_no_fn(self):
        """No context at all: fever alone without chemo context should NOT be EMERGENCY FN."""
        patient = _patient(modalities=[], days_since_chemo=None)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level != TriageLevel.EMERGENCY


# ─── Immunotherapy irAE Overlay ─────────────────────────────────────────────────

class TestImmunotherapyOverlay:
    def test_g2_diarrhea_immunotherapy_escalates_to_urgent(self):
        """Immunotherapy escalates Grade 2 diarrhea from ROUTINE → URGENT."""
        imm = _patient([TreatmentModality.IMMUNOTHERAPY])
        base = _patient([])
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        level_imm, _ = evaluate_symptoms(grade_all([s]), imm)
        level_base, _ = evaluate_symptoms(grade_all([s]), base)
        assert level_imm == TriageLevel.URGENT
        assert level_base == TriageLevel.ROUTINE

    def test_g4_diarrhea_immunotherapy_is_emergency(self):
        """Grade 4 colitis irAE is life-threatening = EMERGENCY."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        s = Symptom(name=SymptomName.DIARRHEA, ctcae_grade=CTCAEGrade.GRADE_4)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY

    def test_dyspnea_immunotherapy_triggers_pneumonitis(self):
        """Any dyspnea in immunotherapy patient fires pneumonitis irAE rule."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="mild")
        level, rules = evaluate_symptoms(grade_all([s]), patient)
        rule_ids = [r["id"] for r in rules]
        assert "pneumonitis_any_grade_immunotherapy" in rule_ids
        assert level == TriageLevel.URGENT

    def test_rest_dyspnea_immunotherapy_is_emergency(self):
        """At-rest dyspnea + immunotherapy = EMERGENCY (pneumonitis_severe irAE)."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        s = Symptom(name=SymptomName.DYSPNEA, at_rest=True)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY

    def test_g2_skin_rash_immunotherapy_is_urgent(self):
        """Grade 2 rash + immunotherapy = irAE dermatitis URGENT."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        s = Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_2)
        level, rules = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.URGENT
        assert any(r["id"] == "irae_dermatitis_g2" for r in rules)

    def test_g3_skin_rash_immunotherapy_is_emergency(self):
        """Grade 3 rash + immunotherapy = EMERGENCY (SJS/TEN exclusion)."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        s = Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_3)
        level, _ = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY

    def test_chest_pain_palpitations_immunotherapy_is_emergency(self):
        """Chest pain + palpitations + immunotherapy = myocarditis irAE EMERGENCY."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        s = Symptom(
            name=SymptomName.PAIN,
            severity_descriptor="moderate",
            descriptors=["chest pain", "palpitations"],
        )
        level, rules = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.EMERGENCY
        assert any(r["id"] == "myocarditis_any_grade" for r in rules)

    def test_irae_rules_have_irae_flag(self):
        """All fired irAE rules must have irae=True."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        _, rules = evaluate_symptoms(grade_all([s]), patient)
        irae_rules = [r for r in rules if r.get("irae")]
        assert len(irae_rules) > 0

    def test_no_irae_rules_without_immunotherapy(self):
        """irAE engine must be gated on immunotherapy modality."""
        patient = _patient([TreatmentModality.CYTOTOXIC_CHEMO])
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        _, rules = evaluate_symptoms(grade_all([s]), patient)
        irae_rules = [r for r in rules if r.get("irae")]
        assert irae_rules == []


# ─── Targeted Therapy ──────────────────────────────────────────────────────────

class TestTargetedTherapy:
    def test_fever_targeted_no_fn_window(self):
        """Targeted therapy only: fever does not trigger cytotoxic FN rule."""
        patient = _patient([TreatmentModality.TARGETED_THERAPY], days_since_chemo=5)
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.5)
        _, rules = evaluate_symptoms(grade_all([s]), patient)
        fn_rules = [r["id"] for r in rules if r["id"].startswith("FN-00")]
        assert fn_rules == []

    def test_severe_diarrhea_targeted_no_imt_escalation(self):
        """Targeted therapy diarrhea: standard grading applies, no irAE escalation."""
        patient = _patient([TreatmentModality.TARGETED_THERAPY])
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        level, rules = evaluate_symptoms(grade_all([s]), patient)
        assert level == TriageLevel.ROUTINE
        irae_rules = [r for r in rules if r.get("irae")]
        assert irae_rules == []


# ─── Combination Modalities ─────────────────────────────────────────────────────

class TestCombinationModalities:
    def test_cytotoxic_plus_immunotherapy_fn_and_irae(self):
        """Combination chemo+immunotherapy: FN window active AND irAE overlay active."""
        patient = _patient(
            [TreatmentModality.CYTOTOXIC_CHEMO, TreatmentModality.IMMUNOTHERAPY],
            days_since_chemo=7,
        )
        symptoms = [
            Symptom(name=SymptomName.FEVER, temperature_celsius=38.5),
            Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5),
        ]
        level, rules = evaluate_symptoms(grade_all(symptoms), patient)
        rule_ids = [r["id"] for r in rules]
        # FN rule fires
        assert any(rid.startswith("FN") for rid in rule_ids)
        # irAE rule fires
        assert any(r.get("irae") for r in rules)
        # Highest level = EMERGENCY (FN wins)
        assert level == TriageLevel.EMERGENCY

    def test_highest_modality_level_wins(self):
        """EMERGENCY beats URGENT in multi-modality scenario."""
        patient = _patient([TreatmentModality.IMMUNOTHERAPY])
        symptoms = [
            Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_3),  # EMERGENCY
            Symptom(name=SymptomName.NAUSEA, ctcae_grade=CTCAEGrade.GRADE_2),       # ROUTINE
        ]
        level, _ = evaluate_symptoms(grade_all(symptoms), patient)
        assert level == TriageLevel.EMERGENCY
