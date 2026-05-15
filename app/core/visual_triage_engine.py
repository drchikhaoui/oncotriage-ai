"""
Visual Triage Engine — Gemini Vision → COSTaRS + irAE pipeline.

Privacy guarantees:
- Image bytes are NEVER written to disk, DB, or logs
- EXIF metadata is stripped before any external API call
- debug_retain_images flag controls whether preprocessed bytes are held in memory
  (false by default; never true in production)
"""
import json
import logging
import uuid
from pathlib import Path

from app.core.costars_engine import grade_all
from app.core.irae_engine import evaluate_irae
from app.core.triage_engine import evaluate_symptoms
from app.integrations import gemini_vision, nci_thesaurus, openfda, pubmed
from app.integrations.vision_providers.chain import get_chain
from app.integrations.vision_providers.prompts import build_prompt
from app.models.patient import PatientContext
from app.models.symptom import CTCAEGrade, Symptom, SymptomName
from app.models.triage import TriageLevel
from app.models.visual_assessment import (
    ExternalEnrichment,
    VisualAssessment,
    VisualTriageResult,
)

logger = logging.getLogger(__name__)

_AE_MAP_PATH = Path(__file__).parent.parent / "data" / "ae_regimen_map.json"

with open(_AE_MAP_PATH) as _f:
    _AE_MAP: dict = json.load(_f)

_AE_LOOKUP: dict[str, dict] = {ae["id"]: ae for ae in _AE_MAP["ae_types"]}

# Map visual AE type → COSTaRS SymptomName
_AE_TO_SYMPTOM: dict[str, SymptomName] = {
    "papulopustular_eruption": SymptomName.SKIN_RASH,
    "hand_foot_syndrome": SymptomName.SKIN_REACTIONS,
    "checkpoint_dermatitis": SymptomName.SKIN_RASH,
    "radiation_dermatitis": SymptomName.SKIN_RASH,
    "oral_mucositis": SymptomName.MUCOSITIS,
    "unsure": SymptomName.SKIN_RASH,
}


def get_available_aes(modalities: list[str]) -> list[dict]:
    """
    Return AE options relevant to the patient's treatment modalities.
    Always returns all AEs (including unsure) if no modalities specified.
    The 'unsure' option is always included regardless of modality.
    """
    if not modalities:
        return _AE_MAP["ae_types"]
    modality_set = set(modalities)
    return [
        ae for ae in _AE_MAP["ae_types"]
        if ae["id"] == "unsure" or any(m in modality_set for m in ae["triggering_modalities"])
    ]


async def analyze_image(
    image_bytes: bytes,
    filename: str,
    suspected_ae: str,
    patient: PatientContext,
    session_id: str | None = None,
    anatomical_location: str = "",
) -> VisualTriageResult:
    """
    Full visual triage pipeline:
    1. Validate + preprocess image (EXIF strip, resize, re-encode)
    2. Call Gemini Vision for structured CTCAE assessment
    3. Route assessment through COSTaRS + irAE engines
    4. Enrich with OpenFDA + PubMed
    5. Return VisualTriageResult (image bytes discarded)
    """
    sid = session_id or str(uuid.uuid4())
    ae_config = _AE_LOOKUP.get(suspected_ae)
    if not ae_config:
        raise ValueError(f"Unknown AE type: {suspected_ae}")

    # ── Step 1: Preprocess ────────────────────────────────────────────────────
    jpeg_bytes, mime_type = gemini_vision.preprocess_image(image_bytes, filename)
    thumbnail = gemini_vision.make_thumbnail(jpeg_bytes)

    # ── Step 2: Vision assessment via fallback chain ───────────────────────────
    modality_str = ", ".join(patient.treatment_modalities_str) or "not specified"
    chemo_context = (
        f"Last treatment: {patient.last_chemo_date}" if patient.last_chemo_date else "not specified"
    )

    is_open_classification = suspected_ae == "unsure"
    ae_label = (
        "open classification — identify what skin or mucosal condition you see"
        if is_open_classification
        else ae_config["label"].get(patient.locale, ae_config["label"]["en"])
    )

    prompt = build_prompt(
        suspected_ae=ae_label,
        treatment_modality=modality_str,
        recent_treatment_dates=chemo_context,
        language=patient.locale,
        open_classification=is_open_classification,
        anatomical_location=anatomical_location,
    )

    vision_response = await get_chain().analyze(jpeg_bytes=jpeg_bytes, prompt=prompt)
    assessment = VisualAssessment.model_validate(vision_response.assessment_dict)
    provider_used = vision_response.provider_used
    model_used = vision_response.model_used

    # Discard image bytes now
    del jpeg_bytes
    del image_bytes

    location_hint = anatomical_location.strip() or None

    # ── Step 3: Handle non-gradable images ────────────────────────────────────
    if not assessment.image_quality.adequate:
        return VisualTriageResult(
            assessment=assessment,
            triage_level=None,
            status="retake_required",
            suspected_ae=suspected_ae,
            session_id=sid,
            provider_used=provider_used,
            model_used=model_used,
            anatomical_location_hint=location_hint,
            thumbnail_data_url=thumbnail,
        )

    if not assessment.ae_match:
        return VisualTriageResult(
            assessment=assessment,
            triage_level=TriageLevel.ROUTINE,
            status="ambiguous",
            suspected_ae=suspected_ae,
            session_id=sid,
            provider_used=provider_used,
            model_used=model_used,
            anatomical_location_hint=location_hint,
            thumbnail_data_url=thumbnail,
        )

    # ── Step 4: Build Symptom from visual grade ───────────────────────────────
    symptom_name = _AE_TO_SYMPTOM.get(suspected_ae, SymptomName.SKIN_RASH)
    grade_int = assessment.ctcae_grade_visual.grade if assessment.ctcae_grade_visual else None
    ctcae_grade = CTCAEGrade(grade_int) if grade_int else None

    morphology_descriptors = (
        assessment.visual_findings.primary_morphology
        if assessment.visual_findings
        else []
    )

    symptom = Symptom(
        name=symptom_name,
        ctcae_grade=ctcae_grade,
        severity_descriptor=_grade_to_severity(grade_int),
        descriptors=morphology_descriptors,
        raw_text=f"Visual assessment: {assessment.ae_match_explanation}",
    )

    graded = grade_all([symptom])

    # ── Step 5: Triage + irAE overlay ────────────────────────────────────────
    triage_level, rules = evaluate_symptoms(graded, patient)
    irae_rules = evaluate_irae(graded, patient)
    irae_suspected = bool(irae_rules)

    if irae_rules:
        irae_levels = [r["triage_level"] for r in irae_rules]
        highest = max(irae_levels, key=lambda lvl: _LEVEL_ORDER[lvl], default=triage_level)
        if _LEVEL_ORDER[highest] > _LEVEL_ORDER[triage_level]:
            triage_level = highest

    # Replace generic SKIN rules with AE-specific guidance when available
    ae_rules = _get_ae_specific_rules(suspected_ae, grade_int, triage_level)
    if ae_rules:
        # Keep irAE rules; swap out generic SKIN rules for AE-specific ones
        rules = [r for r in rules if not r.get("id", "").startswith("SKIN-")]
        rules = ae_rules + rules
    all_rules = rules + irae_rules

    # ── Step 6: External enrichment ──────────────────────────────────────────
    enrichment = await _build_enrichment(ae_config, patient, suspected_ae)

    return VisualTriageResult(
        assessment=assessment,
        triage_level=triage_level,
        triage_rules=all_rules,
        graded_symptoms=graded,
        status="success",
        suspected_ae=suspected_ae,
        enrichment=enrichment,
        session_id=sid,
        irae_suspected=irae_suspected,
        provider_used=provider_used,
        model_used=model_used,
        anatomical_location_hint=location_hint,
        thumbnail_data_url=thumbnail,
    )


_LEVEL_ORDER: dict[TriageLevel, int] = {
    TriageLevel.SELF_CARE: 0,
    TriageLevel.ROUTINE: 1,
    TriageLevel.URGENT: 2,
    TriageLevel.EMERGENCY: 3,
}


def _grade_to_severity(grade: int | None) -> str:
    return {1: "mild", 2: "moderate", 3: "severe", 4: "severe"}.get(grade or 0, "unknown")


# AE-specific clinical guidance by (ae_id, ctcae_grade).
# These replace the generic COSTaRS SKIN rules in the visual triage pipeline.
_AE_RULES: dict[str, dict[int, dict]] = {
    "papulopustular_eruption": {
        1: {
            "id": "EGFR-RASH-G1", "name": "EGFR-TKI Papulopustular Eruption — Grade 1",
            "triage_level": TriageLevel.SELF_CARE,
            "reasoning": "Grade 1 EGFR-TKI papulopustular rash (<10% BSA, no pain). Gentle cleanser, oil-free moisturizer, SPF 30+ daily. Topical clindamycin 1% gel to active lesions. No dose modification required.",
            "citation": "MASCC/ESMO EGFR Inhibitor Cutaneous Toxicities Recommendations 2018; NCCN Dermatologic Toxicities v1.2024",
        },
        2: {
            "id": "EGFR-RASH-G2", "name": "EGFR-TKI Papulopustular Eruption — Grade 2",
            "triage_level": TriageLevel.ROUTINE,
            "reasoning": "Grade 2 EGFR-TKI papulopustular rash (10–30% BSA, affecting ADLs). Topical clindamycin 1% + low-potency topical corticosteroid. Oral doxycycline 100 mg BID × 4–6 weeks. SPF 30+ daily. Dose reduction not required at Grade 2.",
            "citation": "MASCC/ESMO EGFR Inhibitor Cutaneous Toxicities Recommendations 2018; Lacouture ME et al. J Clin Oncol 2011",
        },
        3: {
            "id": "EGFR-RASH-G3", "name": "EGFR-TKI Papulopustular Eruption — Grade 3",
            "triage_level": TriageLevel.URGENT,
            "reasoning": "Grade 3 EGFR-TKI papulopustular rash (>30% BSA, limiting self-care). Interrupt EGFR inhibitor. Systemic doxycycline or minocycline, same-day dermatology evaluation. Resume at reduced dose after improvement to ≤ Grade 1.",
            "citation": "MASCC/ESMO EGFR Inhibitor Cutaneous Toxicities Recommendations 2018",
        },
        4: {
            "id": "EGFR-RASH-G4", "name": "EGFR-TKI Papulopustular Eruption — Grade 4",
            "triage_level": TriageLevel.EMERGENCY,
            "reasoning": "Grade 4 EGFR-TKI papulopustular rash with extensive superinfection. Discontinue EGFR inhibitor. IV antibiotics, emergency dermatology consultation. Do not rechallenge without specialist review.",
            "citation": "MASCC/ESMO EGFR Inhibitor Cutaneous Toxicities Recommendations 2018",
        },
    },
    "hand_foot_syndrome": {
        1: {
            "id": "HFS-G1", "name": "Hand-Foot Syndrome — Grade 1",
            "triage_level": TriageLevel.SELF_CARE,
            "reasoning": "Grade 1 HFS (minimal erythema/hyperkeratosis, no pain). Thick emollients — urea cream 10–20%, petroleum jelly. Protective footwear, avoid heat and friction. No dose modification required.",
            "citation": "ASCO Clinical Practice Guideline HFS 2021; NCCN Dermatologic Toxicities v1.2024",
        },
        2: {
            "id": "HFS-G2", "name": "Hand-Foot Syndrome — Grade 2",
            "triage_level": TriageLevel.ROUTINE,
            "reasoning": "Grade 2 HFS (painful erythema, blistering, limiting ADLs). Urea cream 10–20% + topical analgesic (lidocaine gel pre-meals). Consider 7-day dose interruption if not improving. Follow-up within 24–48 h.",
            "citation": "ASCO Clinical Practice Guideline HFS 2021",
        },
        3: {
            "id": "HFS-G3", "name": "Hand-Foot Syndrome — Grade 3",
            "triage_level": TriageLevel.URGENT,
            "reasoning": "Grade 3 HFS (severe pain, blistering, unable to perform self-care). Dose interruption of causative agent until recovery to ≤ Grade 1. Wound care, pain management, same-day oncology evaluation.",
            "citation": "ASCO Clinical Practice Guideline HFS 2021",
        },
        4: {
            "id": "HFS-G4", "name": "Hand-Foot Syndrome — Grade 4",
            "triage_level": TriageLevel.EMERGENCY,
            "reasoning": "Grade 4 HFS (life-threatening consequences). Permanently discontinue causative agent. Emergency wound care and pain management.",
            "citation": "ASCO Clinical Practice Guideline HFS 2021",
        },
    },
    "checkpoint_dermatitis": {
        1: {
            "id": "ICI-DERM-G1", "name": "ICI Immune-Related Dermatitis — Grade 1",
            "triage_level": TriageLevel.SELF_CARE,
            "reasoning": "Grade 1 ICI-related maculopapular rash (<10% BSA). Topical low-potency corticosteroid. Continue ICI. Monitor closely — ICI rashes can progress rapidly. Notify oncology at next visit.",
            "citation": "ASCO irAE Management Guideline 2021 (Schneider BJ et al. J Clin Oncol 39:4073); NCCN Immunotherapy-Related Toxicities v1.2024",
        },
        2: {
            "id": "ICI-DERM-G2", "name": "ICI Immune-Related Dermatitis — Grade 2",
            "triage_level": TriageLevel.ROUTINE,
            "reasoning": "Grade 2 ICI-related dermatitis (10–30% BSA). Topical mid-potency corticosteroid + oral antihistamine. Consider holding ICI until improvement to ≤ Grade 1. Dermatology referral. Rule out SJS/TEN if mucosal involvement. Per ASCO irAE Guideline 2021.",
            "citation": "ASCO irAE Management Guideline 2021; NCCN Immunotherapy-Related Toxicities v1.2024",
        },
        3: {
            "id": "ICI-DERM-G3", "name": "ICI Immune-Related Dermatitis — Grade 3",
            "triage_level": TriageLevel.URGENT,
            "reasoning": "Grade 3 ICI-related dermatitis (>30% BSA or significant impairment). Hold ICI. Systemic prednisone 1–2 mg/kg/day. Same-day dermatology evaluation — SJS/TEN must be excluded. If SJS/TEN suspected: permanent ICI discontinuation.",
            "citation": "ASCO irAE Management Guideline 2021; Schneider BJ et al. J Clin Oncol 2021",
        },
        4: {
            "id": "ICI-DERM-G4", "name": "ICI Immune-Related Dermatitis — Grade 4",
            "triage_level": TriageLevel.EMERGENCY,
            "reasoning": "Grade 4 ICI-related dermatitis (generalized exfoliative, bullous, or SJS/TEN). Permanently discontinue ICI. Emergency hospitalization, IV methylprednisolone, dermatology and burns team consultation.",
            "citation": "ASCO irAE Management Guideline 2021; NCCN Immunotherapy-Related Toxicities v1.2024",
        },
    },
    "radiation_dermatitis": {
        1: {
            "id": "RAD-DERM-G1", "name": "Radiation Dermatitis — Grade 1",
            "triage_level": TriageLevel.SELF_CARE,
            "reasoning": "Grade 1 radiation dermatitis (faint erythema, dry desquamation). Fragrance-free moisturizer, gentle cleansing, loose clothing over the area. Avoid sun exposure to the radiated field.",
            "citation": "NCCN Supportive Care — Dermatologic Toxicities v1.2024",
        },
        2: {
            "id": "RAD-DERM-G2", "name": "Radiation Dermatitis — Grade 2",
            "triage_level": TriageLevel.ROUTINE,
            "reasoning": "Grade 2 radiation dermatitis (moderate/brisk erythema, patchy moist desquamation in skin folds). Saline compresses, low-potency topical corticosteroid, hydrocolloid dressing for moist areas. Notify radiation oncology team.",
            "citation": "NCCN Supportive Care — Dermatologic Toxicities v1.2024; Bray FN et al. J Clin Aesthet Dermatol 2016",
        },
        3: {
            "id": "RAD-DERM-G3", "name": "Radiation Dermatitis — Grade 3",
            "triage_level": TriageLevel.URGENT,
            "reasoning": "Grade 3 radiation dermatitis (moist desquamation outside folds, bleeds with minor trauma). Wound care team referral, non-adherent dressings, pain management. Radiation oncology notification same-day.",
            "citation": "NCCN Supportive Care — Dermatologic Toxicities v1.2024",
        },
        4: {
            "id": "RAD-DERM-G4", "name": "Radiation Dermatitis — Grade 4",
            "triage_level": TriageLevel.EMERGENCY,
            "reasoning": "Grade 4 radiation dermatitis (skin necrosis, spontaneous bleeding). Emergency wound care. Discontinue radiotherapy pending assessment. Plastic surgery/burns team consultation.",
            "citation": "NCCN Supportive Care — Dermatologic Toxicities v1.2024",
        },
    },
    "oral_mucositis": {
        1: {
            "id": "MUCOS-G1", "name": "Oral Mucositis — Grade 1",
            "triage_level": TriageLevel.SELF_CARE,
            "reasoning": "Grade 1 oral mucositis (mild symptoms). Saline/bicarbonate rinses 4–6×/day, soft toothbrush. Soft diet. Ice chips during chemotherapy infusion (cryotherapy) if applicable. No dose modification required.",
            "citation": "MASCC/ISOO Clinical Practice Guideline Update 2020; Lalla RV et al. Cancer 2014",
        },
        2: {
            "id": "MUCOS-G2", "name": "Oral Mucositis — Grade 2",
            "triage_level": TriageLevel.ROUTINE,
            "reasoning": "Grade 2 oral mucositis (moderate pain, modified diet needed). Saline/bicarbonate rinses, topical lidocaine gel pre-meals, soft or liquid diet, ensure oral hydration. Follow-up within 24–48 h. Screen for oral candidiasis.",
            "citation": "MASCC/ISOO Clinical Practice Guideline Update 2020; Lalla RV et al. Cancer 2014",
        },
        3: {
            "id": "MUCOS-G3", "name": "Oral Mucositis — Grade 3",
            "triage_level": TriageLevel.URGENT,
            "reasoning": "Grade 3 oral mucositis (severe pain, unable to eat). IV hydration, parenteral/enteral nutrition consideration, IV opioid for pain, antifungal/antiviral coverage. Chemotherapy dose hold until recovery to ≤ Grade 2.",
            "citation": "MASCC/ISOO Clinical Practice Guideline Update 2020",
        },
        4: {
            "id": "MUCOS-G4", "name": "Oral Mucositis — Grade 4",
            "triage_level": TriageLevel.EMERGENCY,
            "reasoning": "Grade 4 oral mucositis (life-threatening, urgent intervention required). Emergency hospitalization, IV fluids + nutritional support, opioid pain management, concurrent infection management.",
            "citation": "MASCC/ISOO Clinical Practice Guideline Update 2020",
        },
    },
}


def _get_ae_specific_rules(
    suspected_ae: str,
    grade_int: int | None,
    triage_level: TriageLevel,
) -> list[dict]:
    """Return AE-specific clinical rule(s) for this AE+grade, or empty list if not applicable."""
    ae_rules = _AE_RULES.get(suspected_ae)
    if not ae_rules or not grade_int:
        return []
    capped = min(grade_int, max(ae_rules.keys()))
    rule = ae_rules.get(capped)
    if not rule:
        return []
    # Preserve the triage_level already computed (may have been escalated by irAE overlay)
    effective_level = max(
        rule["triage_level"],
        triage_level,
        key=lambda lvl: _LEVEL_ORDER[lvl],
    )
    return [{**rule, "triage_level": effective_level}]


async def _build_enrichment(
    ae_config: dict,
    patient: PatientContext,
    suspected_ae: str,
) -> ExternalEnrichment:
    """Gather OpenFDA + PubMed + NCI enrichment asynchronously."""
    import asyncio

    nci_term = nci_thesaurus.get_term_local(suspected_ae, patient.locale)
    ctcae_term = ae_config.get("ctcae_term", "")

    # Build PubMed query from AE + treatment context
    drug_context = ""
    if patient.treatment_modalities_str:
        drug_context = patient.treatment_modalities_str[0].replace("_", " ")
    pubmed_query = f"{ctcae_term} {drug_context} incidence treatment".strip()

    async def _get_pubmed():
        try:
            return await pubmed.search_citations(pubmed_query, max_results=2)
        except Exception:
            return []

    async def _get_openfda():
        try:
            top = await openfda.fetch_top_reactions_for_drug(drug_context or ae_config["id"])
            return top
        except Exception:
            return []

    citations_list, fda_reactions = await asyncio.gather(_get_pubmed(), _get_openfda())

    openfda_summary = None
    openfda_count = None
    if fda_reactions:
        top = fda_reactions[0]
        openfda_count = top.get("count", 0)
        drug_display = drug_context or ae_config["id"].replace("_", " ")
        openfda_summary = openfda.build_enrichment_summary(
            drug_display, top.get("term", ctcae_term), openfda_count
        )

    return ExternalEnrichment(
        openfda_summary=openfda_summary,
        openfda_report_count=openfda_count,
        pubmed_citations=[c.to_dict() for c in citations_list],
        nci_term=nci_term,
    )
