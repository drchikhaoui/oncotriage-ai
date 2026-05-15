"""
COSTaRS v2020 engine tests — validates grading for all supported protocols.
"""
from app.core.costars_engine import COSTARS_DATA, grade_all, grade_symptom
from app.models.symptom import CTCAEGrade, Symptom, SymptomName


class TestFeverGrading:
    def test_38_0c_is_grade1(self):
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.0)
        assert grade_symptom(s).value == 1

    def test_38_3c_is_grade1(self):
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=38.3)
        assert grade_symptom(s).value == 1

    def test_39_5c_is_grade2(self):
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=39.5)
        assert grade_symptom(s).value == 2

    def test_40_5c_short_duration_is_grade3(self):
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=40.5, duration_hours=5)
        assert grade_symptom(s).value == 3

    def test_40_5c_prolonged_is_grade4(self):
        s = Symptom(name=SymptomName.FEVER, temperature_celsius=40.5, duration_hours=25)
        assert grade_symptom(s).value == 4

    def test_no_temp_severe_descriptor_is_grade3(self):
        s = Symptom(name=SymptomName.FEVER, severity_descriptor="severe")
        assert grade_symptom(s).value == 3

    def test_explicit_grade_used_when_no_temp(self):
        """Explicit ctcae_grade is used when no temperature is provided."""
        s = Symptom(name=SymptomName.FEVER, ctcae_grade=CTCAEGrade.GRADE_3)
        assert grade_symptom(s).value == 3


class TestNauseaVomitingGrading:
    def test_grade1_low_episodes(self):
        s = Symptom(name=SymptomName.VOMITING, episodes_per_24h=1)
        assert grade_symptom(s).value == 1

    def test_grade2_3_to_5_episodes(self):
        s = Symptom(name=SymptomName.VOMITING, episodes_per_24h=4)
        assert grade_symptom(s).value == 2

    def test_grade3_6plus_episodes(self):
        s = Symptom(name=SymptomName.VOMITING, episodes_per_24h=8)
        assert grade_symptom(s).value == 3

    def test_nausea_severe_descriptor_grade3(self):
        s = Symptom(name=SymptomName.NAUSEA, severity_descriptor="severe")
        assert grade_symptom(s).value == 3

    def test_nausea_maps_to_nausea_vomiting_protocol(self):
        graded = grade_all([Symptom(name=SymptomName.NAUSEA, ctcae_grade=CTCAEGrade.GRADE_1)])
        assert graded[0]["protocol_id"] == "nausea_vomiting"

    def test_vomiting_maps_to_nausea_vomiting_protocol(self):
        graded = grade_all([Symptom(name=SymptomName.VOMITING, ctcae_grade=CTCAEGrade.GRADE_2)])
        assert graded[0]["protocol_id"] == "nausea_vomiting"


class TestDiarrheaGrading:
    def test_grade1_lt4_stools(self):
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=2)
        assert grade_symptom(s).value == 1

    def test_grade2_4_to_6_stools(self):
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        assert grade_symptom(s).value == 2

    def test_grade3_7plus_stools(self):
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=10)
        assert grade_symptom(s).value == 3

    def test_descriptor_watery_is_grade3(self):
        s = Symptom(name=SymptomName.DIARRHEA, severity_descriptor="watery uncontrolled")
        assert grade_symptom(s).value == 3

    def test_explicit_grade_respected(self):
        s = Symptom(name=SymptomName.DIARRHEA, ctcae_grade=CTCAEGrade.GRADE_4)
        assert grade_symptom(s).value == 4


class TestPainGrading:
    def test_nrs_3_is_grade1(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=3)
        assert grade_symptom(s).value == 1

    def test_nrs_5_is_grade2(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=5)
        assert grade_symptom(s).value == 2

    def test_nrs_7_is_grade3(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=7)
        assert grade_symptom(s).value == 3

    def test_nrs_10_is_grade4(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=10)
        assert grade_symptom(s).value == 4

    def test_severe_descriptor_is_grade3(self):
        s = Symptom(name=SymptomName.PAIN, severity_descriptor="severe unbearable")
        assert grade_symptom(s).value == 3


class TestDyspneaGrading:
    def test_at_rest_is_grade3(self):
        s = Symptom(name=SymptomName.DYSPNEA, at_rest=True)
        assert grade_symptom(s).value == 3

    def test_moderate_descriptor_is_grade2(self):
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="moderate")
        assert grade_symptom(s).value == 2

    def test_exertion_descriptor_is_grade2(self):
        s = Symptom(name=SymptomName.DYSPNEA, descriptors=["on exertion"])
        assert grade_symptom(s).value == 2

    def test_mild_is_grade1(self):
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="mild")
        assert grade_symptom(s).value == 1


class TestGradeAllOutput:
    def test_returns_list_with_correct_length(self):
        symptoms = [
            Symptom(name=SymptomName.FEVER, temperature_celsius=38.5),
            Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_2),
        ]
        result = grade_all(symptoms)
        assert len(result) == 2

    def test_each_entry_has_required_keys(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=5)
        result = grade_all([s])
        entry = result[0]
        required = {"symptom", "protocol_id", "ctcae_grade", "severity", "ctcae_description", "term", "citation", "raw_symptom"}
        assert required.issubset(entry.keys())

    def test_costars_citation_present(self):
        s = Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_2)
        result = grade_all([s])
        assert "COSTaRS" in result[0]["citation"] or "Ottawa" in result[0]["citation"]

    def test_term_is_english_name(self):
        s = Symptom(name=SymptomName.MUCOSITIS, ctcae_grade=CTCAEGrade.GRADE_2)
        result = grade_all([s])
        assert result[0]["term"] != ""

    def test_new_costars_symptoms_grade_correctly(self):
        symptoms = [
            Symptom(name=SymptomName.ANXIETY, ctcae_grade=CTCAEGrade.GRADE_2),
            Symptom(name=SymptomName.SKIN_RASH, ctcae_grade=CTCAEGrade.GRADE_3),
            Symptom(name=SymptomName.XEROSTOMIA, ctcae_grade=CTCAEGrade.GRADE_1),
        ]
        result = grade_all(symptoms)
        grades = [r["ctcae_grade"] for r in result]
        assert grades == [2, 3, 1]


class TestCOSTaRSDataIntegrity:
    def test_all_17_protocols_loaded(self):
        expected_protocols = {
            "anorexia", "anxiety", "bleeding", "constipation", "depression",
            "diarrhea", "dyspnea", "fatigue", "fever", "mucositis",
            "nausea_vomiting", "pain", "peripheral_neuropathy",
            "skin_reactions", "sleep_wake_disturbance", "xerostomia", "skin_rash",
        }
        loaded = set(COSTARS_DATA["protocols"].keys())
        missing = expected_protocols - loaded
        assert not missing, f"Missing COSTaRS protocols: {missing}"

    def test_each_protocol_has_triage_rules(self):
        for protocol_id, protocol in COSTARS_DATA["protocols"].items():
            rules = protocol.get("triage_rules", [])
            assert len(rules) > 0, f"Protocol {protocol_id} has no triage rules"

    def test_each_protocol_has_multilingual_names(self):
        for protocol_id, protocol in COSTARS_DATA["protocols"].items():
            names = protocol.get("names", {})
            for lang in ("en", "fr", "ar"):
                assert lang in names, f"Protocol {protocol_id} missing {lang} name"
