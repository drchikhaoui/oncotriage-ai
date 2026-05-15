"""
CTCAE v5.0 grading engine — fully deterministic, no LLM dependency.
Grades symptoms based on clinical parameters against NCI CTCAE v5.0 thresholds.
"""
import json
from pathlib import Path

from app.models.symptom import CTCAEGrade, Symptom, SymptomName

_DATA_PATH = Path(__file__).parent.parent / "data" / "ctcae_v5.json"

with open(_DATA_PATH) as f:
    CTCAE_DATA = json.load(f)


def grade_fever(symptom: Symptom) -> CTCAEGrade:
    temp = symptom.temperature_celsius
    if temp is None:
        if symptom.ctcae_grade:
            return symptom.ctcae_grade
        desc = (symptom.severity_descriptor or "").lower()
        if "mild" in desc:
            return CTCAEGrade.GRADE_1
        if "moderate" in desc:
            return CTCAEGrade.GRADE_2
        if "severe" in desc or "high" in desc:
            return CTCAEGrade.GRADE_3
        return CTCAEGrade.GRADE_1

    duration = symptom.duration_hours or 0
    if temp > 40.0:
        return CTCAEGrade.GRADE_4 if duration > 24 else CTCAEGrade.GRADE_3
    if temp >= 39.1:
        return CTCAEGrade.GRADE_2
    if temp >= 38.0:
        return CTCAEGrade.GRADE_1
    return CTCAEGrade.GRADE_1


def grade_vomiting(symptom: Symptom) -> CTCAEGrade:
    if symptom.ctcae_grade:
        return symptom.ctcae_grade
    episodes = symptom.episodes_per_24h
    if episodes is None:
        desc = (symptom.severity_descriptor or "").lower()
        if "severe" in desc or "constant" in desc:
            return CTCAEGrade.GRADE_3
        if "moderate" in desc or "frequent" in desc:
            return CTCAEGrade.GRADE_2
        return CTCAEGrade.GRADE_1
    if episodes >= 6:
        return CTCAEGrade.GRADE_3
    if episodes >= 3:
        return CTCAEGrade.GRADE_2
    return CTCAEGrade.GRADE_1


def grade_diarrhea(symptom: Symptom) -> CTCAEGrade:
    if symptom.ctcae_grade:
        return symptom.ctcae_grade
    stools = symptom.stools_above_baseline or symptom.episodes_per_24h
    if stools is None:
        desc = (symptom.severity_descriptor or "").lower()
        if "severe" in desc or "watery" in desc or "uncontrol" in desc:
            return CTCAEGrade.GRADE_3
        if "moderate" in desc or "frequent" in desc:
            return CTCAEGrade.GRADE_2
        return CTCAEGrade.GRADE_1
    if stools >= 7:
        return CTCAEGrade.GRADE_3
    if stools >= 4:
        return CTCAEGrade.GRADE_2
    return CTCAEGrade.GRADE_1


def grade_pain(symptom: Symptom) -> CTCAEGrade:
    if symptom.ctcae_grade:
        return symptom.ctcae_grade
    nrs = symptom.pain_nrs
    if nrs is not None:
        if nrs >= 10:
            return CTCAEGrade.GRADE_4
        if nrs >= 7:
            return CTCAEGrade.GRADE_3
        if nrs >= 4:
            return CTCAEGrade.GRADE_2
        if nrs >= 1:
            return CTCAEGrade.GRADE_1
    desc = (symptom.severity_descriptor or "").lower()
    if "severe" in desc or "unbearable" in desc or "worst" in desc:
        return CTCAEGrade.GRADE_3
    if "moderate" in desc:
        return CTCAEGrade.GRADE_2
    return CTCAEGrade.GRADE_1


def grade_dyspnea(symptom: Symptom) -> CTCAEGrade:
    if symptom.ctcae_grade:
        return symptom.ctcae_grade
    if symptom.at_rest:
        return CTCAEGrade.GRADE_3
    desc = (symptom.severity_descriptor or "").lower()
    descriptors = " ".join(symptom.descriptors).lower()
    combined = desc + " " + descriptors
    if "rest" in combined or "severe" in combined or "unable" in combined:
        return CTCAEGrade.GRADE_3
    if "minimal" in combined or "slight" in combined or "moderate" in combined:
        return CTCAEGrade.GRADE_2
    return CTCAEGrade.GRADE_1


def grade_generic(symptom: Symptom) -> CTCAEGrade:
    """Fallback grader using severity descriptors."""
    if symptom.ctcae_grade:
        return symptom.ctcae_grade
    desc = (symptom.severity_descriptor or "").lower()
    if "grade 4" in desc or "life-threatening" in desc or "life threatening" in desc:
        return CTCAEGrade.GRADE_4
    if "grade 3" in desc or "severe" in desc:
        return CTCAEGrade.GRADE_3
    if "grade 2" in desc or "moderate" in desc:
        return CTCAEGrade.GRADE_2
    return CTCAEGrade.GRADE_1


_GRADERS = {
    SymptomName.FEVER: grade_fever,
    SymptomName.VOMITING: grade_vomiting,
    SymptomName.DIARRHEA: grade_diarrhea,
    SymptomName.PAIN: grade_pain,
    SymptomName.DYSPNEA: grade_dyspnea,
}


def grade_symptom(symptom: Symptom) -> CTCAEGrade:
    """
    Returns CTCAE grade for a symptom.
    Uses specific grader if available, otherwise falls back to generic.
    """
    grader = _GRADERS.get(symptom.name, grade_generic)
    return grader(symptom)


def grade_all(symptoms: list[Symptom]) -> list[dict]:
    """Grade a list of symptoms and return enriched dicts."""
    results = []
    for s in symptoms:
        grade = grade_symptom(s)
        ctcae_info = CTCAE_DATA["symptoms"].get(s.name.value, {})
        grade_info = ctcae_info.get("grades", {}).get(str(grade.value), {})
        results.append({
            "symptom": s.name.value,
            "ctcae_grade": grade.value,
            "severity": grade_info.get("severity", "unknown"),
            "ctcae_description": grade_info.get("description", ""),
            "term": ctcae_info.get("term", s.name.value),
            "raw_symptom": s,
        })
    return results
