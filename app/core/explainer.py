"""
Reasoning trace generator — produces auditable, citation-backed explanations
for every triage decision. Updated for COSTaRS v2020.
"""
import json
from pathlib import Path

from app.models.patient import PatientContext
from app.models.triage import ReasoningStep, TriageLevel, TriageResult

_RULES_PATH = Path(__file__).parent.parent / "data" / "nccn_rules.json"
with open(_RULES_PATH) as f:
    _TRIAGE_LEVELS = json.load(f)["triage_levels"]

_COSTARS_CITATION = (
    "Stacey D, Carley M, Ballantyne B, et al. Pan-Canadian Oncology Symptom Triage "
    "and Remote Support (COSTaRS) Practice Guides. Ottawa: University of Ottawa; 2020."
)


def build_reasoning_trace(
    triage_level: TriageLevel,
    fired_rules: list[dict],
    graded_symptoms: list[dict],
    patient: PatientContext,
    session_id: str,
    llm_used: bool = False,
) -> TriageResult:
    level_meta = _TRIAGE_LEVELS[triage_level.value]
    steps: list[ReasoningStep] = []
    citations: set[str] = set()
    irae_suspected = any(r.get("irae") for r in fired_rules)

    # Step 1: symptoms graded
    for i, gs in enumerate(graded_symptoms):
        grade_label = f"Grade {gs['ctcae_grade']} ({gs['severity']})" if gs.get("severity") != "unknown" else f"Grade {gs['ctcae_grade']}"
        desc = gs.get("ctcae_description", "")
        desc_suffix = f" {desc}" if desc else ""
        step_text = f"Symptom identified: {gs['term']} — COSTaRS/CTCAE {grade_label}.{desc_suffix}"
        steps.append(ReasoningStep(step=i + 1, finding=step_text, source=_COSTARS_CITATION))
    citations.add(_COSTARS_CITATION)

    offset = len(steps)

    # Step 2: fired rules
    for j, rule in enumerate(fired_rules):
        steps.append(ReasoningStep(
            step=offset + j + 1,
            finding=rule["reasoning"],
            source=rule.get("citation", ""),
        ))
        if rule.get("citation"):
            citations.add(rule["citation"])

    # Step 3: patient context notes
    if patient.recent_chemo:
        days = patient.days_since_chemo
        steps.append(ReasoningStep(
            step=len(steps) + 1,
            finding=f"Clinical context: Last chemotherapy {days} day(s) ago — patient is within neutropenic risk window.",
            source="NCCN Prevention and Treatment of Cancer-Related Infections v2.2024",
        ))
        citations.add("NCCN Prevention and Treatment of Cancer-Related Infections v2.2024")

    if patient.thrombocytopenia_history:
        steps.append(ReasoningStep(
            step=len(steps) + 1,
            finding="Clinical context: Known thrombocytopenia history — bleeding thresholds are lowered.",
            source="NCCN Hematopoietic Growth Factors v2.2024",
        ))

    if irae_suspected:
        steps.append(ReasoningStep(
            step=len(steps) + 1,
            finding="irAE Alert: Patient is on immunotherapy. Immune-related adverse event (irAE) protocols applied per NCCN/ASCO guidelines. Early recognition and intervention are critical.",
            source="NCCN Management of Immunotherapy-Related Toxicities v1.2024",
        ))
        citations.add("NCCN Management of Immunotherapy-Related Toxicities v1.2024")

    return TriageResult(
        session_id=session_id,
        triage_level=triage_level,
        emoji=level_meta["emoji"],
        color=level_meta["color"],
        action=level_meta["action"],
        timeframe=level_meta["timeframe"],
        reasoning_steps=steps,
        triggered_rules=[r["id"] for r in fired_rules],
        citations=sorted(citations),
        symptoms_graded=[
            {k: v for k, v in gs.items() if k != "raw_symptom"}
            for gs in graded_symptoms
        ],
        irae_suspected=irae_suspected,
        llm_used=llm_used,
    )
