"""
COSTaRS v2020 grading engine — deterministic symptom severity grading.
Pan-Canadian Oncology Symptom Triage and Remote Support (COSTaRS) Practice Guides,
University of Ottawa School of Nursing, 2020.
License: CC BY-NC-ND 4.0
"""
import json
from pathlib import Path

from app.models.symptom import CTCAEGrade, Symptom, SymptomName

_DATA_PATH = Path(__file__).parent.parent / "data" / "costars_v2020.json"

with open(_DATA_PATH) as f:
    COSTARS_DATA = json.load(f)

_PROTOCOLS = COSTARS_DATA["protocols"]
_CITATION = COSTARS_DATA["citation"]

_SYMPTOM_TO_PROTOCOL: dict[SymptomName, str] = {
    SymptomName.FEVER: "fever",
    SymptomName.NAUSEA: "nausea_vomiting",
    SymptomName.VOMITING: "nausea_vomiting",
    SymptomName.DIARRHEA: "diarrhea",
    SymptomName.CONSTIPATION: "constipation",
    SymptomName.FATIGUE: "fatigue",
    SymptomName.PAIN: "pain",
    SymptomName.DYSPNEA: "dyspnea",
    SymptomName.MUCOSITIS: "mucositis",
    SymptomName.PERIPHERAL_NEUROPATHY: "peripheral_neuropathy",
    SymptomName.BLEEDING: "bleeding",
    SymptomName.ANXIETY: "anxiety",
    SymptomName.DEPRESSION: "depression",
    SymptomName.ANOREXIA: "anorexia",
    SymptomName.SKIN_RASH: "skin_rash",
    SymptomName.SKIN_REACTIONS: "skin_reactions",
    SymptomName.SLEEP_WAKE_DISTURBANCE: "sleep_wake_disturbance",
    SymptomName.XEROSTOMIA: "xerostomia",
}


def grade_fever(symptom: Symptom) -> CTCAEGrade:
    temp = symptom.temperature_celsius
    if temp is None:
        if symptom.ctcae_grade:
            return symptom.ctcae_grade
        desc = (symptom.severity_descriptor or "").lower()
        if "severe" in desc or "high" in desc:
            return CTCAEGrade.GRADE_3
        if "moderate" in desc:
            return CTCAEGrade.GRADE_2
        return CTCAEGrade.GRADE_1

    duration = symptom.duration_hours or 0
    if temp > 40.0:
        return CTCAEGrade.GRADE_4 if duration > 24 else CTCAEGrade.GRADE_3
    if temp >= 39.1:
        return CTCAEGrade.GRADE_2
    if temp >= 38.0:
        return CTCAEGrade.GRADE_1
    return CTCAEGrade.GRADE_1


def grade_nausea_vomiting(symptom: Symptom) -> CTCAEGrade:
    if symptom.ctcae_grade:
        return symptom.ctcae_grade
    episodes = symptom.episodes_per_24h
    if episodes is not None:
        if episodes >= 6:
            return CTCAEGrade.GRADE_3
        if episodes >= 3:
            return CTCAEGrade.GRADE_2
        return CTCAEGrade.GRADE_1
    desc = (symptom.severity_descriptor or "").lower()
    if "severe" in desc or "constant" in desc or "unable" in desc:
        return CTCAEGrade.GRADE_3
    if "moderate" in desc or "frequent" in desc:
        return CTCAEGrade.GRADE_2
    return CTCAEGrade.GRADE_1


def grade_diarrhea(symptom: Symptom) -> CTCAEGrade:
    if symptom.ctcae_grade:
        return symptom.ctcae_grade
    stools = symptom.stools_above_baseline or symptom.episodes_per_24h
    if stools is not None:
        if stools >= 7:
            return CTCAEGrade.GRADE_3
        if stools >= 4:
            return CTCAEGrade.GRADE_2
        return CTCAEGrade.GRADE_1
    desc = (symptom.severity_descriptor or "").lower()
    if "severe" in desc or "watery" in desc or "uncontrol" in desc:
        return CTCAEGrade.GRADE_3
    if "moderate" in desc or "frequent" in desc:
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
    combined = (symptom.severity_descriptor or "").lower() + " " + " ".join(symptom.descriptors).lower()
    if "rest" in combined or "severe" in combined or "unable" in combined:
        return CTCAEGrade.GRADE_3
    if "minimal" in combined or "slight" in combined or "moderate" in combined or "exertion" in combined:
        return CTCAEGrade.GRADE_2
    return CTCAEGrade.GRADE_1


def grade_generic(symptom: Symptom) -> CTCAEGrade:
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
    SymptomName.NAUSEA: grade_nausea_vomiting,
    SymptomName.VOMITING: grade_nausea_vomiting,
    SymptomName.DIARRHEA: grade_diarrhea,
    SymptomName.PAIN: grade_pain,
    SymptomName.DYSPNEA: grade_dyspnea,
}


def grade_symptom(symptom: Symptom) -> CTCAEGrade:
    grader = _GRADERS.get(symptom.name, grade_generic)
    return grader(symptom)


def grade_all(symptoms: list[Symptom]) -> list[dict]:
    """Grade a list of symptoms and return enriched dicts with COSTaRS v2020 protocol info."""
    results = []
    for s in symptoms:
        grade = grade_symptom(s)
        protocol_id = _SYMPTOM_TO_PROTOCOL.get(s.name, s.name.value)
        protocol = _PROTOCOLS.get(protocol_id, {})
        grade_key = f"grade_{grade.value}"
        grade_info = protocol.get("severity_grading", {}).get(grade_key, {})
        results.append({
            "symptom": s.name.value,
            "protocol_id": protocol_id,
            "ctcae_grade": grade.value,
            "severity": grade_info.get("level", "unknown"),
            "ctcae_description": grade_info.get("criteria", ""),
            "term": protocol.get("names", {}).get("en", s.name.value.replace("_", " ").title()),
            "costars_rules": protocol.get("triage_rules", []),
            "self_care": protocol.get("self_care", []),
            "citation": _CITATION,
            "raw_symptom": s,
        })
    return results
