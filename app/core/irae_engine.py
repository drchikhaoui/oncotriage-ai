"""
irAE overlay engine — immune-related adverse event detection for immunotherapy patients.
NCCN Management of Immunotherapy-Related Toxicities v1.2024
ASCO irAE Guideline: Schneider BJ et al. JCO 2021
"""
import json
from pathlib import Path

from app.models.patient import PatientContext
from app.models.triage import TriageLevel

_DATA_PATH = Path(__file__).parent.parent / "data" / "irae_protocols.json"

with open(_DATA_PATH) as f:
    IRAE_DATA = json.load(f)

_PROTOCOLS = IRAE_DATA["protocols"]
_CITATION_PRIMARY = IRAE_DATA["citation_primary"]
_CITATION_NCCN = IRAE_DATA["citation_nccn"]

_TIER_TO_LEVEL = {
    "emergency": TriageLevel.EMERGENCY,
    "urgent": TriageLevel.URGENT,
    "routine": TriageLevel.ROUTINE,
    "self_care": TriageLevel.SELF_CARE,
}

# Protocol activation: maps protocol_id → symptom names that trigger evaluation
_PROTOCOL_TRIGGERS: dict[str, list[str]] = {
    "colitis": ["diarrhea"],
    "pneumonitis": ["dyspnea"],
    "hepatitis": ["fatigue", "nausea", "vomiting", "pain"],
    "hypophysitis": ["fatigue", "nausea", "vomiting", "neurologic", "anxiety"],
    "myocarditis": ["dyspnea", "pain", "fatigue"],
    "thyroiditis": ["fatigue"],
    "nephritis": ["fatigue"],
    "irae_dermatitis": ["skin_rash", "skin_reactions"],
}


def evaluate_irae(
    graded_symptoms: list[dict],
    patient: PatientContext,
) -> list[dict]:
    """
    Apply irAE overlay for immunotherapy patients.
    Returns list of fired irAE rules, each with: id, protocol_id, protocol_name,
    triage_level, reasoning, citation, irae=True.
    """
    if not patient.has_immunotherapy:
        return []

    symptom_names: set[str] = {gs["symptom"] for gs in graded_symptoms}
    grade_map: dict[str, int] = {gs["symptom"]: gs["ctcae_grade"] for gs in graded_symptoms}
    obj_map: dict[str, object] = {gs["symptom"]: gs.get("raw_symptom") for gs in graded_symptoms}

    fired: list[dict] = []

    for protocol_id, trigger_syms in _PROTOCOL_TRIGGERS.items():
        if not any(s in symptom_names for s in trigger_syms):
            continue

        protocol = _PROTOCOLS.get(protocol_id)
        if not protocol:
            continue

        for rule in protocol.get("triage_rules", []):
            if _matches_rule(rule["id"], symptom_names, grade_map, obj_map):
                fired.append({
                    "id": rule["id"],
                    "protocol_id": protocol_id,
                    "protocol_name": protocol["name"].get("en", protocol_id),
                    "triage_level": _TIER_TO_LEVEL.get(rule["tier"], TriageLevel.URGENT),
                    "reasoning": rule["reasoning"],
                    "citation": f"{_CITATION_NCCN}; {_CITATION_PRIMARY}",
                    "irae": True,
                })

    return fired


def _has_descriptor(obj_map: dict, *keywords: str) -> bool:
    """Check if any symptom object has a descriptor containing any of the keywords."""
    for sym in obj_map.values():
        if sym is None:
            continue
        all_text = " ".join(sym.descriptors).lower() + " " + (sym.severity_descriptor or "").lower()
        if any(kw in all_text for kw in keywords):
            return True
    return False


def _matches_rule(
    rule_id: str,
    symptom_names: set[str],
    grade_map: dict[str, int],
    obj_map: dict,
) -> bool:
    match rule_id:
        # Colitis
        case "colitis_g4":
            return grade_map.get("diarrhea", 0) >= 4
        case "colitis_g2_plus":
            return grade_map.get("diarrhea", 0) >= 2

        # Pneumonitis
        case "pneumonitis_any_grade_immunotherapy":
            return "dyspnea" in symptom_names
        case "pneumonitis_severe":
            return grade_map.get("dyspnea", 0) >= 3

        # Hepatitis
        case "hepatitis_jaundice_irae":
            return _has_descriptor(obj_map, "jaundice", "yellow", "icteric")
        case "hepatitis_symptoms":
            return _has_descriptor(obj_map, "dark urine", "ruq", "right upper", "dark_urine")

        # Hypophysitis
        case "hypophysitis_adrenal_crisis":
            return (
                grade_map.get("fatigue", 0) >= 3
                and _has_descriptor(obj_map, "confusion", "hypotension", "lightheaded", "faint")
            )
        case "hypophysitis_symptoms":
            return (
                grade_map.get("fatigue", 0) >= 2
                and _has_descriptor(obj_map, "headache", "head pain")
            )

        # Myocarditis — rare but ~50% case fatality; any chest/palpitation symptom with immunotherapy
        case "myocarditis_any_grade":
            return _has_descriptor(obj_map, "chest", "palpitation", "racing heart", "irregular")

        # Thyroiditis — requires specific clinical pattern (palpitations + tremor + heat intolerance)
        case "thyroiditis_storm" | "thyroiditis_symptoms":
            return False  # Requires very specific multi-symptom pattern; NLU handles this

        # Nephritis — requires hematuria / decreased output; not in basic symptom form
        case "nephritis_symptoms":
            return _has_descriptor(obj_map, "blood in urine", "hematuria", "decreased urine", "no urine", "swelling")

        # irAE Dermatitis
        case "irae_dermatitis_g3_plus":
            return max(grade_map.get("skin_rash", 0), grade_map.get("skin_reactions", 0)) >= 3
        case "irae_dermatitis_g2":
            return max(grade_map.get("skin_rash", 0), grade_map.get("skin_reactions", 0)) >= 2

        case _:
            return False
