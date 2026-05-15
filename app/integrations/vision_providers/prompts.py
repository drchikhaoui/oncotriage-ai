"""Shared CTCAE vision prompt — used by all providers."""

SYSTEM_PROMPT = """You are an oncology nursing assistant trained in CTCAE v5.0 grading
of dermatologic adverse events. You assess clinical photographs to support care-team
decision-making. You are NOT providing a medical diagnosis — you are extracting
visual features to support CTCAE severity grading by a clinician.

Strict rules:
- If the image is unclear, poorly lit, or out of focus: set image_quality.adequate=false
  and DO NOT attempt to grade (ctcae_grade_visual=null, visual_findings=null)
- If the image shows something outside the requested AE category: set ae_match=false
  and explain in ae_match_explanation
- Always include caveats and confidence level
- Never provide treatment recommendations — only describe visual features
- Return ONLY valid JSON matching the provided schema — no markdown, no commentary
"""

USER_PROMPT_TEMPLATE = """Suspected AE: {suspected_ae}
Patient treatment modality: {treatment_modality}
{anatomical_location_hint}Recent treatment dates context: {recent_treatment_dates}
Response language: {language}

Assess this photograph and return STRICT JSON with exactly this structure:

{{
  "image_quality": {{
    "adequate": true,
    "issues": [],
    "retake_recommended": false
  }},
  "ae_match": true,
  "ae_match_explanation": "describe what you see",
  "visual_findings": {{
    "body_surface_area_percent_estimate": 15,
    "distribution": "regional",
    "primary_morphology": ["papules", "pustules"],
    "secondary_features": [],
    "anatomical_site": "face and upper chest"
  }},
  "ctcae_grade_visual": {{
    "grade": 2,
    "ctcae_descriptor": "direct quote from CTCAE v5.0 matching this grade",
    "confidence": "moderate"
  }},
  "caveats": ["list any clinical caveats"],
  "language": "{language}"
}}

IMPORTANT: If image_quality.adequate is false OR ae_match is false,
set visual_findings=null and ctcae_grade_visual=null.
"""


_OPEN_CLASSIFICATION_SUFFIX = """

Note: This is an OPEN CLASSIFICATION request — the patient does not know which specific
reaction they have. Examine the image and identify the most likely pattern (acneiform rash,
hand-foot syndrome, maculopapular rash, radiation dermatitis, or oral mucositis).
Describe what you identified clearly in ae_match_explanation.
Set ae_match=true if you recognize any relevant skin or mucosal pattern."""


def build_prompt(
    suspected_ae: str,
    treatment_modality: str,
    recent_treatment_dates: str = "not specified",
    language: str = "en",
    open_classification: bool = False,
    anatomical_location: str = "",
) -> str:
    location_hint = (
        f"Patient-reported lesion location: {anatomical_location.strip()}\n"
        if anatomical_location.strip()
        else ""
    )
    base = USER_PROMPT_TEMPLATE.format(
        suspected_ae=suspected_ae,
        treatment_modality=treatment_modality,
        anatomical_location_hint=location_hint,
        recent_treatment_dates=recent_treatment_dates,
        language=language,
    )
    return base + (_OPEN_CLASSIFICATION_SUFFIX if open_classification else "")
