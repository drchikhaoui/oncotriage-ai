"""
irAE engine tests — validates immune-related adverse event detection.
All 8 irAE protocols from NCCN Management of Immunotherapy-Related Toxicities v1.2024.
"""
from app.core.costars_engine import grade_all
from app.core.irae_engine import evaluate_irae
from app.models.patient import PatientContext, TreatmentModality
from app.models.symptom import CTCAEGrade, Symptom, SymptomName
from app.models.triage import TriageLevel


def _immunotherapy_patient(session_id: str = "irae-test") -> PatientContext:
    return PatientContext(
        session_id=session_id,
        treatment_modalities=[TreatmentModality.IMMUNOTHERAPY],
    )


def _no_immunotherapy_patient(session_id: str = "no-irae-test") -> PatientContext:
    return PatientContext(session_id=session_id)


class TestIrAEGate:
    def test_no_rules_without_immunotherapy(self):
        patient = _no_immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=6)
        graded = grade_all([s])
        assert evaluate_irae(graded, patient) == []

    def test_returns_list_with_immunotherapy(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=6)
        graded = grade_all([s])
        result = evaluate_irae(graded, patient)
        assert isinstance(result, list)


class TestColitisProtocol:
    def test_diarrhea_g2_fires_colitis_rule(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)  # grade 2
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "colitis_g2_plus" in rule_ids

    def test_diarrhea_g4_fires_colitis_g4_rule(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, ctcae_grade=CTCAEGrade.GRADE_4)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "colitis_g4" in rule_ids

    def test_diarrhea_g4_is_emergency(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, ctcae_grade=CTCAEGrade.GRADE_4)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        emergency_rules = [r for r in rules if r["triage_level"] == TriageLevel.EMERGENCY]
        assert emergency_rules

    def test_diarrhea_g1_no_irae_rule(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=2)  # grade 1
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "colitis_g2_plus" not in rule_ids
        assert "colitis_g4" not in rule_ids


class TestPneumonitisProtocol:
    def test_any_dyspnea_fires_pneumonitis_rule(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="mild")
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "pneumonitis_any_grade_immunotherapy" in rule_ids

    def test_pneumonitis_g1_is_urgent(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="mild")
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        pneumonitis = next((r for r in rules if r["id"] == "pneumonitis_any_grade_immunotherapy"), None)
        assert pneumonitis is not None
        assert pneumonitis["triage_level"] == TriageLevel.URGENT

    def test_pneumonitis_g3_fires_severe_rule(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DYSPNEA, at_rest=True)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "pneumonitis_severe" in rule_ids

    def test_pneumonitis_severe_is_emergency(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DYSPNEA, at_rest=True)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        severe_rule = next((r for r in rules if r["id"] == "pneumonitis_severe"), None)
        assert severe_rule is not None
        assert severe_rule["triage_level"] == TriageLevel.EMERGENCY


class TestDermatitisProtocol:
    def test_skin_rash_g2_fires_urgent(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_2)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "irae_dermatitis_g2" in rule_ids
        g2_rule = next(r for r in rules if r["id"] == "irae_dermatitis_g2")
        assert g2_rule["triage_level"] == TriageLevel.URGENT

    def test_skin_rash_g3_fires_emergency(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_3)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "irae_dermatitis_g3_plus" in rule_ids
        g3_rule = next(r for r in rules if r["id"] == "irae_dermatitis_g3_plus")
        assert g3_rule["triage_level"] == TriageLevel.EMERGENCY

    def test_skin_reactions_also_triggers_dermatitis(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.SKIN_REACTIONS, ctcae_grade=CTCAEGrade.GRADE_2)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "irae_dermatitis_g2" in rule_ids


class TestMyocarditisProtocol:
    def test_chest_pain_descriptor_triggers_myocarditis(self):
        patient = _immunotherapy_patient()
        s = Symptom(
            name=SymptomName.PAIN,
            severity_descriptor="moderate",
            descriptors=["chest pain", "palpitations"],
        )
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        rule_ids = [r["id"] for r in rules]
        assert "myocarditis_any_grade" in rule_ids

    def test_myocarditis_rule_is_emergency(self):
        patient = _immunotherapy_patient()
        s = Symptom(
            name=SymptomName.DYSPNEA,
            severity_descriptor="moderate",
            descriptors=["palpitations", "racing heart"],
        )
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        myocarditis_rule = next((r for r in rules if r["id"] == "myocarditis_any_grade"), None)
        assert myocarditis_rule is not None
        assert myocarditis_rule["triage_level"] == TriageLevel.EMERGENCY


class TestIrAERuleStructure:
    def test_all_irae_rules_have_required_fields(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        for rule in rules:
            assert "id" in rule
            assert "protocol_id" in rule
            assert "protocol_name" in rule
            assert "triage_level" in rule
            assert "reasoning" in rule
            assert "citation" in rule
            assert rule.get("irae") is True

    def test_irae_rules_have_nccn_citation(self):
        patient = _immunotherapy_patient()
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        graded = grade_all([s])
        rules = evaluate_irae(graded, patient)
        for rule in rules:
            assert "NCCN" in rule["citation"] or "Schneider" in rule["citation"]
