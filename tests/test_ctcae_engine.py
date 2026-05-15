from app.core.ctcae_engine import grade_all, grade_symptom
from app.models.symptom import CTCAEGrade, Symptom, SymptomName


def make_fever(temp=None, duration=None, grade=None, desc=None):
    return Symptom(
        name=SymptomName.FEVER,
        temperature_celsius=temp,
        duration_hours=duration,
        ctcae_grade=grade,
        severity_descriptor=desc,
    )


class TestFeverGrading:
    def test_grade1_38c(self):
        assert grade_symptom(make_fever(temp=38.0)) == CTCAEGrade.GRADE_1

    def test_grade1_38_5c(self):
        assert grade_symptom(make_fever(temp=38.5)) == CTCAEGrade.GRADE_1

    def test_grade2_39_2c(self):
        assert grade_symptom(make_fever(temp=39.2)) == CTCAEGrade.GRADE_2

    def test_grade3_40_5c_short(self):
        assert grade_symptom(make_fever(temp=40.5, duration=10)) == CTCAEGrade.GRADE_3

    def test_grade4_40_5c_prolonged(self):
        assert grade_symptom(make_fever(temp=40.5, duration=25)) == CTCAEGrade.GRADE_4

    def test_grade_passthrough(self):
        assert grade_symptom(make_fever(grade=CTCAEGrade.GRADE_2)) == CTCAEGrade.GRADE_2


class TestVomitingGrading:
    def test_grade1_1_episode(self):
        s = Symptom(name=SymptomName.VOMITING, episodes_per_24h=1)
        assert grade_symptom(s) == CTCAEGrade.GRADE_1

    def test_grade2_4_episodes(self):
        s = Symptom(name=SymptomName.VOMITING, episodes_per_24h=4)
        assert grade_symptom(s) == CTCAEGrade.GRADE_2

    def test_grade3_6_episodes(self):
        s = Symptom(name=SymptomName.VOMITING, episodes_per_24h=6)
        assert grade_symptom(s) == CTCAEGrade.GRADE_3

    def test_grade3_10_episodes(self):
        s = Symptom(name=SymptomName.VOMITING, episodes_per_24h=10)
        assert grade_symptom(s) == CTCAEGrade.GRADE_3


class TestDiarrheaGrading:
    def test_grade1_2_stools(self):
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=2)
        assert grade_symptom(s) == CTCAEGrade.GRADE_1

    def test_grade2_5_stools(self):
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=5)
        assert grade_symptom(s) == CTCAEGrade.GRADE_2

    def test_grade3_7_stools(self):
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=7)
        assert grade_symptom(s) == CTCAEGrade.GRADE_3

    def test_grade3_10_stools(self):
        s = Symptom(name=SymptomName.DIARRHEA, stools_above_baseline=10)
        assert grade_symptom(s) == CTCAEGrade.GRADE_3


class TestPainGrading:
    def test_grade1_nrs_2(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=2)
        assert grade_symptom(s) == CTCAEGrade.GRADE_1

    def test_grade2_nrs_5(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=5)
        assert grade_symptom(s) == CTCAEGrade.GRADE_2

    def test_grade3_nrs_8(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=8)
        assert grade_symptom(s) == CTCAEGrade.GRADE_3

    def test_grade4_nrs_10(self):
        s = Symptom(name=SymptomName.PAIN, pain_nrs=10)
        assert grade_symptom(s) == CTCAEGrade.GRADE_4


class TestDyspneaGrading:
    def test_grade3_at_rest(self):
        s = Symptom(name=SymptomName.DYSPNEA, at_rest=True)
        assert grade_symptom(s) == CTCAEGrade.GRADE_3

    def test_grade1_exertion(self):
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="mild", at_rest=False)
        assert grade_symptom(s) == CTCAEGrade.GRADE_1

    def test_grade2_descriptor(self):
        s = Symptom(name=SymptomName.DYSPNEA, severity_descriptor="moderate")
        assert grade_symptom(s) == CTCAEGrade.GRADE_2


class TestGradeAll:
    def test_returns_list_with_all_fields(self):
        symptoms = [
            Symptom(name=SymptomName.FEVER, temperature_celsius=38.7),
            Symptom(name=SymptomName.FATIGUE, ctcae_grade=CTCAEGrade.GRADE_2),
        ]
        results = grade_all(symptoms)
        assert len(results) == 2
        for r in results:
            assert "ctcae_grade" in r
            assert "severity" in r
            assert "term" in r
            assert "raw_symptom" in r
