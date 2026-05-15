"""
Triage decision engine — regimen-aware, COSTaRS v2020 + NCCN guideline-based.
All decisions produce auditable rule IDs and reasoning traces.
"""
import json
from pathlib import Path

from app.core.irae_engine import evaluate_irae
from app.models.patient import PatientContext, TreatmentModality
from app.models.symptom import Symptom, SymptomName
from app.models.triage import TriageLevel

_FLAGS_PATH = Path(__file__).parent.parent / "data" / "red_flags.json"
_REGIMEN_PATH = Path(__file__).parent.parent / "data" / "regimen_modifiers.json"

with open(_FLAGS_PATH) as f:
    RED_FLAGS_DATA = json.load(f)

with open(_REGIMEN_PATH) as f:
    REGIMEN_DATA = json.load(f)

_LEVEL_PRIORITY = {
    TriageLevel.EMERGENCY: 4,
    TriageLevel.URGENT: 3,
    TriageLevel.ROUTINE: 2,
    TriageLevel.SELF_CARE: 1,
}


def _escalate(current: TriageLevel, candidate: TriageLevel) -> TriageLevel:
    if _LEVEL_PRIORITY[candidate] > _LEVEL_PRIORITY[current]:
        return candidate
    return current


def check_immediate_escalation_keywords(free_text: str) -> tuple[bool, list[str]]:
    """Scan free text for life-threatening keywords before full processing."""
    if not free_text:
        return False, []
    text_lower = free_text.lower()
    triggered = [kw for kw in RED_FLAGS_DATA["immediate_escalation_keywords"] if kw in text_lower]
    return bool(triggered), triggered


def _check_febrile_neutropenia(
    symptom: Symptom,
    graded_value: int,
    patient: PatientContext,
) -> tuple[TriageLevel | None, str | None, str | None]:
    """Returns (level, rule_id, reasoning) if febrile neutropenia / CRS protocol fires."""
    if symptom.name != SymptomName.FEVER:
        return None, None, None

    days = patient.days_since_chemo

    # CAR-T / SCT: 30-day extended window — any fever = CRS risk
    if patient.has_car_t_or_transplant and patient.recent_chemo_car_t:
        temp = symptom.temperature_celsius
        temp_str = f" ({temp}°C)" if temp else ""
        modality = "CAR-T" if TreatmentModality.CAR_T in patient.treatment_modalities else "SCT"
        reasoning = (
            f"Fever{temp_str} within 30 days post {modality} (day {days}). "
            "Cytokine release syndrome (CRS) protocol applied — EMERGENCY. "
            "Tocilizumab, corticosteroids, and immediate hemato-oncology evaluation required. "
            "Per NCCN B-Cell Lymphomas and ASTCT CRS Consensus Grading 2019."
        )
        return TriageLevel.EMERGENCY, "FN-CAR-T", reasoning

    # Cytotoxic chemo: 14-day standard window.
    # Legacy mode: if no modalities specified but chemo date set, assume cytotoxic for backward compat.
    is_cytotoxic_context = patient.has_cytotoxic or (
        not patient.treatment_modalities and patient.last_chemo_date is not None
    )
    if not is_cytotoxic_context or not patient.recent_chemo:
        return None, None, None

    temp = symptom.temperature_celsius
    duration = symptom.duration_hours or 0

    if temp is not None:
        if temp >= 38.3:
            reasoning = (
                f"Temperature {temp}°C meets NCCN febrile neutropenia threshold (≥38.3°C single reading). "
                f"Last chemotherapy {days} day(s) ago (within 14-day neutropenic window). "
                "Immediate ED evaluation — blood cultures, CBC, empiric broad-spectrum antibiotics."
            )
            return TriageLevel.EMERGENCY, "FN-001", reasoning
        if temp >= 38.0 and duration >= 1:
            reasoning = (
                f"Temperature {temp}°C sustained ≥1h meets alternate NCCN FN criterion. "
                f"Last chemotherapy {days} day(s) ago. Emergency evaluation required."
            )
            return TriageLevel.EMERGENCY, "FN-002", reasoning

    if graded_value >= 1:
        reasoning = (
            f"Fever (COSTaRS/CTCAE Grade {graded_value}) + recent chemotherapy ({days} day(s) ago). "
            "Febrile neutropenia protocol applied — Emergency evaluation required."
        )
        return TriageLevel.EMERGENCY, "FN-001", reasoning

    return None, None, None


def evaluate_symptoms(
    graded_symptoms: list[dict],
    patient: PatientContext,
    free_text: str | None = None,
) -> tuple[TriageLevel, list[dict]]:
    """
    Regimen-aware triage logic. Returns (triage_level, fired_rules).
    Each rule: {id, name, triage_level, reasoning, citation}.
    """
    current_level = TriageLevel.SELF_CARE
    fired_rules: list[dict] = []

    # Guard 1: immediate keyword escalation
    if free_text:
        escalated, keywords = check_immediate_escalation_keywords(free_text)
        if escalated:
            current_level = TriageLevel.EMERGENCY
            fired_rules.append({
                "id": "KW-001",
                "name": "Life-threatening keyword detected",
                "triage_level": TriageLevel.EMERGENCY,
                "reasoning": f"Patient description contains high-acuity keywords: {', '.join(keywords)}. Immediate escalation applied.",
                "citation": "Red flag keyword screening — pre-processing safety layer",
            })

    # Guard 2: irAE overlay (immunotherapy patients only)
    if patient.has_immunotherapy:
        for irae_rule in evaluate_irae(graded_symptoms, patient):
            current_level = _escalate(current_level, irae_rule["triage_level"])
            fired_rules.append({
                "id": irae_rule["id"],
                "name": f"irAE Alert: {irae_rule['protocol_name']}",
                "triage_level": irae_rule["triage_level"],
                "reasoning": irae_rule["reasoning"],
                "citation": irae_rule["citation"],
                "irae": True,
            })

    # Per-symptom evaluation
    for entry in graded_symptoms:
        symptom: Symptom = entry["raw_symptom"]
        grade: int = entry["ctcae_grade"]
        name: SymptomName = symptom.name

        # --- Febrile neutropenia / CRS ---
        fn_level, fn_rule_id, fn_reasoning = _check_febrile_neutropenia(symptom, grade, patient)
        if fn_level:
            current_level = _escalate(current_level, fn_level)
            fired_rules.append({
                "id": fn_rule_id,
                "name": "Febrile Neutropenia / CRS Protocol",
                "triage_level": fn_level,
                "reasoning": fn_reasoning,
                "citation": "NCCN Prevention and Treatment of Cancer-Related Infections v2.2024; Freifeld AG et al. CID 2011",
            })
            continue

        # --- SCT diarrhea — GvHD risk ---
        if name == SymptomName.DIARRHEA and TreatmentModality.STEM_CELL_TRANSPLANT in patient.treatment_modalities:
            if patient.recent_chemo_car_t:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "SCT-GVH-001",
                    "name": "Post-SCT Diarrhea — GvHD Risk",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Diarrhea within 30 days of stem cell transplant (COSTaRS Grade {grade}) — graft-versus-host disease must be excluded urgently.",
                    "citation": "NCCN Hematopoietic Cell Transplantation; Zeiser R, Blazar BR. NEJM 2017",
                })
                continue

        # --- Dyspnea ---
        if name == SymptomName.DYSPNEA:
            if grade >= 3 or symptom.at_rest:
                current_level = _escalate(current_level, TriageLevel.EMERGENCY)
                fired_rules.append({
                    "id": "RESP-001",
                    "name": "Dyspnea at Rest",
                    "triage_level": TriageLevel.EMERGENCY,
                    "reasoning": f"Dyspnea at rest (COSTaRS/CTCAE Grade {grade}) — life-threatening respiratory compromise. Possible PE, effusion, tamponade, or pneumonitis.",
                    "citation": "COSTaRS v2020 Dyspnea Protocol; NCCN Survivorship v2.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "RESP-002",
                    "name": "Moderate Dyspnea",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Dyspnea with minimal exertion (COSTaRS Grade {grade}). Same-day evaluation to rule out treatable causes.",
                    "citation": "COSTaRS v2020 Dyspnea Protocol",
                })
            elif not patient.has_immunotherapy:
                # Grade 1 without immunotherapy (irAE module handles immunotherapy case)
                current_level = _escalate(current_level, TriageLevel.SELF_CARE)
                fired_rules.append({
                    "id": "RESP-003",
                    "name": "Mild Dyspnea",
                    "triage_level": TriageLevel.SELF_CARE,
                    "reasoning": "Mild dyspnea on exertion only. Monitor for worsening. Notify oncology if increasing.",
                    "citation": "COSTaRS v2020 Dyspnea Protocol",
                })
            continue

        # --- Neurologic red flags ---
        if name == SymptomName.NEUROLOGIC:
            current_level = _escalate(current_level, TriageLevel.EMERGENCY)
            descriptor_str = ", ".join(symptom.descriptors) or symptom.severity_descriptor or "new onset"
            fired_rules.append({
                "id": "NEURO-001",
                "name": "Neurologic Red Flag",
                "triage_level": TriageLevel.EMERGENCY,
                "reasoning": f"New neurologic symptoms ({descriptor_str}) in oncology patient — brain metastasis, cord compression, ICANS, or stroke must be ruled out urgently.",
                "citation": "NCCN CNS Cancers v1.2024; COSTaRS v2020",
            })
            continue

        # --- Bleeding ---
        if name == SymptomName.BLEEDING:
            if grade >= 3:
                level = TriageLevel.EMERGENCY
                rule = "BLEED-002"
                reasoning = f"Grade {grade} bleeding (COSTaRS v2020) — transfusion or urgent hemostatic intervention required."
            elif grade >= 2 or patient.thrombocytopenia_history:
                level = TriageLevel.URGENT
                rule = "BLEED-001"
                reasoning = (
                    f"{'Any bleeding with thrombocytopenia history — platelet assessment urgent. ' if patient.thrombocytopenia_history else ''}"
                    f"Grade {grade} bleeding requires same-day evaluation and CBC."
                )
            else:
                level = TriageLevel.ROUTINE
                rule = "BLEED-003"
                reasoning = "Grade 1 bleeding (petechiae/minor bruising). Monitor closely. CBC/platelet count at next visit."
            current_level = _escalate(current_level, level)
            fired_rules.append({
                "id": rule,
                "name": "Bleeding Assessment",
                "triage_level": level,
                "reasoning": reasoning,
                "citation": "COSTaRS v2020 Bleeding Protocol; NCCN Hematopoietic Growth Factors v2.2024; Schiffer CA et al. JCO 2018",
            })
            continue

        # --- Nausea / Vomiting ---
        if name in (SymptomName.VOMITING, SymptomName.NAUSEA):
            if grade >= 3:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "GI-001",
                    "name": "Severe Nausea/Vomiting",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} nausea/vomiting (COSTaRS v2020) — inadequate oral intake and dehydration risk. IV hydration and antiemetic escalation required same-day.",
                    "citation": "COSTaRS v2020 Nausea/Vomiting Protocol; NCCN Antiemesis v2.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "GI-001b",
                    "name": "Moderate Nausea/Vomiting",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} nausea/vomiting limiting oral intake. Antiemetic optimization per NCCN within 24-48h.",
                    "citation": "COSTaRS v2020 Nausea/Vomiting Protocol; NCCN Antiemesis v2.2024",
                })
            else:
                current_level = _escalate(current_level, TriageLevel.SELF_CARE)
                fired_rules.append({
                    "id": "GI-001c",
                    "name": "Mild Nausea",
                    "triage_level": TriageLevel.SELF_CARE,
                    "reasoning": "Grade 1 nausea — mild, not affecting eating habits. Dietary adjustments and PRN antiemetics.",
                    "citation": "COSTaRS v2020 Nausea/Vomiting Protocol",
                })
            continue

        # --- Diarrhea ---
        if name == SymptomName.DIARRHEA:
            if grade >= 3:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "GI-002",
                    "name": "Severe Diarrhea",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} diarrhea (≥7 stools/day above baseline, COSTaRS v2020). IV hydration, electrolytes, C. difficile screen required same-day.",
                    "citation": "COSTaRS v2020 Diarrhea Protocol; NCCN Survivorship v2.2024",
                })
            elif grade == 2:
                if patient.has_immunotherapy:
                    current_level = _escalate(current_level, TriageLevel.URGENT)
                    fired_rules.append({
                        "id": "GI-002-imt",
                        "name": "Diarrhea Grade 2 + Immunotherapy",
                        "triage_level": TriageLevel.URGENT,
                        "reasoning": f"Grade {grade} diarrhea with immunotherapy — irAE colitis must be ruled out. Hold ICI, stool cultures, consider prednisone per NCCN irAE guidelines.",
                        "citation": "COSTaRS v2020; NCCN irAE v1.2024; Schneider BJ et al. JCO 2021",
                    })
                else:
                    current_level = _escalate(current_level, TriageLevel.ROUTINE)
                    fired_rules.append({
                        "id": "GI-002b",
                        "name": "Moderate Diarrhea",
                        "triage_level": TriageLevel.ROUTINE,
                        "reasoning": f"Grade {grade} diarrhea limiting ADLs (COSTaRS v2020). Loperamide, hydration, dietary modification. Follow up 24-48h.",
                        "citation": "COSTaRS v2020 Diarrhea Protocol",
                    })
            continue

        # --- Pain ---
        if name == SymptomName.PAIN:
            if grade >= 4:
                current_level = _escalate(current_level, TriageLevel.EMERGENCY)
                fired_rules.append({
                    "id": "PAIN-002",
                    "name": "Disabling Pain (Grade 4)",
                    "triage_level": TriageLevel.EMERGENCY,
                    "reasoning": f"Grade 4 pain (NRS {symptom.pain_nrs}/10). Rule out cord compression, pathologic fracture, organ obstruction. Emergency evaluation per COSTaRS v2020.",
                    "citation": "COSTaRS v2020 Pain Protocol; NCCN Adult Cancer Pain v2.2024",
                })
            elif grade == 3:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "PAIN-001",
                    "name": "Severe Pain",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade 3 pain (NRS {symptom.pain_nrs}/10, COSTaRS v2020) — severe, limiting self-care ADLs. Same-day opioid titration and reassessment required.",
                    "citation": "COSTaRS v2020 Pain Protocol; NCCN Adult Cancer Pain v2.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "PAIN-003",
                    "name": "Moderate Pain",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade 2 pain (NRS {symptom.pain_nrs}/10) limiting instrumental ADLs. Analgesic step-up per WHO pain ladder and COSTaRS v2020.",
                    "citation": "COSTaRS v2020 Pain Protocol; NCCN Adult Cancer Pain v2.2024; WHO Pain Ladder",
                })
            continue

        # --- Constipation ---
        if name == SymptomName.CONSTIPATION:
            if grade >= 4:
                current_level = _escalate(current_level, TriageLevel.EMERGENCY)
                fired_rules.append({
                    "id": "GI-003",
                    "name": "Severe Constipation / Possible Bowel Obstruction",
                    "triage_level": TriageLevel.EMERGENCY,
                    "reasoning": f"Grade {grade} constipation with obstipation — possible bowel obstruction. Emergency surgical evaluation per COSTaRS v2020.",
                    "citation": "COSTaRS v2020 Constipation Protocol",
                })
            elif grade >= 3:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "GI-003b",
                    "name": "Severe Constipation",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} constipation requiring manual evacuation. Bowel regimen review; consider methylnaltrexone if opioid-induced.",
                    "citation": "COSTaRS v2020 Constipation Protocol; NCCN Adult Cancer Pain v2.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "GI-003c",
                    "name": "Moderate Constipation",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} constipation. Laxative regimen review and dietary counseling per COSTaRS v2020.",
                    "citation": "COSTaRS v2020 Constipation Protocol",
                })
            continue

        # --- Mucositis ---
        if name == SymptomName.MUCOSITIS:
            if grade >= 3:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "MUC-001",
                    "name": "Severe Oral Mucositis",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} mucositis (COSTaRS v2020) — severe pain interfering with oral intake. Nutritional support, IV fluids, antifungal/antiviral review required.",
                    "citation": "COSTaRS v2020 Mucositis Protocol; MASCC/ISOO Guidelines 2020",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "MUC-001b",
                    "name": "Moderate Mucositis",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} mucositis with painful ulcers modifying diet. Magic mouthwash, soft diet, oral hygiene protocol per COSTaRS v2020.",
                    "citation": "COSTaRS v2020 Mucositis Protocol",
                })
            continue

        # --- Peripheral neuropathy ---
        if name == SymptomName.PERIPHERAL_NEUROPATHY:
            if grade >= 3:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "NEURO-002",
                    "name": "Severe CIPN",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} CIPN limiting self-care ADLs (COSTaRS v2020). Dose modification of neurotoxic agent and neurology referral per NCCN CIPN guidelines.",
                    "citation": "COSTaRS v2020 Peripheral Neuropathy Protocol; NCCN Survivorship v2.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "NEURO-002b",
                    "name": "Moderate CIPN",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} CIPN limiting instrumental ADLs. Duloxetine trial (ASCO Guideline) and fall risk assessment per COSTaRS v2020.",
                    "citation": "COSTaRS v2020 Peripheral Neuropathy Protocol; Loprinzi CL et al. NEJM 2018",
                })
            continue

        # --- Fatigue ---
        if name == SymptomName.FATIGUE:
            imt_addendum = (
                " Additional workup: TSH, morning cortisol, ACTH — screen for immunotherapy-induced thyroiditis / hypophysitis."
                if patient.has_immunotherapy else ""
            )
            if grade >= 3:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "FAT-001",
                    "name": "Severe Cancer-Related Fatigue",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} fatigue not relieved by rest (COSTaRS v2020). NCCN: CBC (anemia), TSH (hypothyroidism), PHQ-9 (depression), sleep assessment.{imt_addendum}",
                    "citation": "COSTaRS v2020 Fatigue Protocol; NCCN Cancer-Related Fatigue v2.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "FAT-001b",
                    "name": "Moderate Cancer-Related Fatigue",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} fatigue limiting instrumental ADLs (COSTaRS v2020). CBC, TSH, PHQ-9. Exercise and energy conservation counseling.{imt_addendum}",
                    "citation": "COSTaRS v2020 Fatigue Protocol; NCCN Cancer-Related Fatigue v2.2024",
                })
            continue

        # --- Fever (no qualifying chemo context — handled above) ---
        if name == SymptomName.FEVER:
            temp_str = f" ({symptom.temperature_celsius}°C)" if symptom.temperature_celsius else ""
            if grade >= 2:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "FEVER-001",
                    "name": "Fever — Oncology Patient",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} fever{temp_str} in oncology patient. Infectious workup required — immunosuppression from disease or corticosteroids may be present.",
                    "citation": "COSTaRS v2020 Fever Protocol; NCCN Guidelines",
                })
            else:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "FEVER-002",
                    "name": "Low-Grade Fever",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade 1 fever{temp_str}. Monitor temperature trends; notify oncology team if escalating or if chemotherapy is imminent.",
                    "citation": "COSTaRS v2020 Fever Protocol",
                })
            continue

        # --- Skin rash / reactions ---
        if name in (SymptomName.SKIN_RASH, SymptomName.SKIN_REACTIONS):
            label = "rash" if name == SymptomName.SKIN_RASH else "reaction"
            if grade >= 3:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "SKIN-001",
                    "name": f"Severe Skin {label.title()}",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} skin {label} (COSTaRS v2020) — Stevens-Johnson syndrome or TEN must be excluded. Same-day dermatology evaluation.",
                    "citation": "COSTaRS v2020 Skin Reactions Protocol; Schneider BJ et al. JCO 2021",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "SKIN-001b",
                    "name": f"Moderate Skin {label.title()}",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} skin {label} limiting daily function. Topical steroid management per COSTaRS v2020. Dermatology referral if not improving.",
                    "citation": "COSTaRS v2020 Skin Reactions Protocol",
                })
            continue

        # --- Anxiety / Depression (psycho-oncology) ---
        if name in (SymptomName.ANXIETY, SymptomName.DEPRESSION):
            label = "anxiety" if name == SymptomName.ANXIETY else "depression"
            if grade >= 3 or symptom.uncontrolled:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "PSY-001",
                    "name": f"Severe {label.title()}",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} {label} (COSTaRS v2020) limiting self-care ADLs — psychiatric evaluation and suicidality screening required.",
                    "citation": f"COSTaRS v2020 {label.title()} Protocol; NCCN Distress Management v3.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "PSY-001b",
                    "name": f"Moderate {label.title()}",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} {label} limiting daily function. PHQ-9/GAD-7 screening and referral per COSTaRS v2020 and NCCN Distress Management.",
                    "citation": f"COSTaRS v2020 {label.title()} Protocol; NCCN Distress Management v3.2024",
                })
            continue

        # --- Anorexia ---
        if name == SymptomName.ANOREXIA:
            if grade >= 3:
                current_level = _escalate(current_level, TriageLevel.URGENT)
                fired_rules.append({
                    "id": "ANOR-001",
                    "name": "Severe Anorexia",
                    "triage_level": TriageLevel.URGENT,
                    "reasoning": f"Grade {grade} anorexia with inadequate caloric intake (COSTaRS v2020). Nutritional assessment, consider enteral support or TPN.",
                    "citation": "COSTaRS v2020 Anorexia Protocol; NCCN Survivorship v2.2024",
                })
            elif grade == 2:
                current_level = _escalate(current_level, TriageLevel.ROUTINE)
                fired_rules.append({
                    "id": "ANOR-001b",
                    "name": "Moderate Anorexia",
                    "triage_level": TriageLevel.ROUTINE,
                    "reasoning": f"Grade {grade} anorexia with altered eating habits. Nutritional counseling and appetite stimulant review per COSTaRS v2020.",
                    "citation": "COSTaRS v2020 Anorexia Protocol",
                })
            continue

    if not fired_rules:
        current_level = TriageLevel.SELF_CARE
        fired_rules.append({
            "id": "DEFAULT-001",
            "name": "Grade 1 Symptoms — Self-Care",
            "triage_level": TriageLevel.SELF_CARE,
            "reasoning": "All symptoms are Grade 1 (mild) with no red-flag combinations per COSTaRS v2020. Home management appropriate. Monitor for worsening and contact oncology team if symptoms escalate.",
            "citation": "COSTaRS v2020; NCCN Survivorship v2.2024",
        })

    return current_level, fired_rules
