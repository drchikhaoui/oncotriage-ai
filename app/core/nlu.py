"""
LLM-based NLU layer — Claude API for symptom extraction from free text.
Gracefully degrades to structured form if LLM is unavailable.
"""
import json
import logging
import re

from app.config import settings
from app.models.symptom import Symptom, SymptomName

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a clinical NLU engine for an oncology triage system.
Extract structured symptom data from the patient's free-text description.

Return ONLY a JSON array of symptom objects. Each object must match this schema:
{
  "name": one of [fever, nausea, vomiting, diarrhea, constipation, fatigue, pain, dyspnea, mucositis, peripheral_neuropathy, bleeding, neurologic, other],
  "severity_descriptor": "mild" | "moderate" | "severe" | "life-threatening" | descriptive phrase,
  "duration_hours": number or null,
  "onset": "sudden" | "gradual" | "unknown",
  "temperature_celsius": number or null (only for fever),
  "pain_nrs": integer 0-10 or null (only for pain),
  "episodes_per_24h": integer or null (for vomiting/diarrhea),
  "stools_above_baseline": integer or null (for diarrhea),
  "at_rest": boolean or null (for dyspnea — true if occurs at rest),
  "uncontrolled": boolean or null (for pain — true if not responding to current meds),
  "descriptors": [array of relevant keywords],
  "associated_symptoms": [array of other symptoms mentioned]
}

Rules:
- Extract ALL symptoms mentioned, even if mild
- Be conservative with severity — when uncertain, choose the lower grade
- For neurologic symptoms (new focal weakness, severe headache, vision changes, seizure), always use name: "neurologic"
- NEVER include patient name, date of birth, or any identifying information
- If no recognizable oncology symptoms are present, return an empty array []
- Return only the JSON array, no explanation"""


async def extract_symptoms_from_text(free_text: str) -> tuple[list[Symptom], bool]:
    """
    Returns (list_of_symptoms, llm_was_used).
    Falls back to empty list if LLM unavailable — caller handles fallback form.
    """
    if settings.disable_llm or not settings.anthropic_api_key:
        logger.info("LLM disabled or no API key — using structured form fallback")
        return [], False

    try:
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

        message = await client.messages.create(
            model=settings.llm_model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": f"Extract symptoms from this patient description: {free_text[:2000]}"
                }
            ],
        )

        raw = message.content[0].text.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)

        symptom_data = json.loads(raw)
        if not isinstance(symptom_data, list):
            logger.warning("LLM returned non-list JSON — falling back")
            return [], False

        symptoms = []
        for item in symptom_data:
            try:
                name_raw = item.get("name", "other").lower().replace(" ", "_")
                try:
                    name = SymptomName(name_raw)
                except ValueError:
                    name = SymptomName.OTHER

                symptom = Symptom(
                    name=name,
                    severity_descriptor=item.get("severity_descriptor"),
                    duration_hours=item.get("duration_hours"),
                    onset=item.get("onset"),
                    temperature_celsius=item.get("temperature_celsius"),
                    pain_nrs=item.get("pain_nrs"),
                    episodes_per_24h=item.get("episodes_per_24h"),
                    stools_above_baseline=item.get("stools_above_baseline"),
                    at_rest=item.get("at_rest"),
                    uncontrolled=item.get("uncontrolled"),
                    descriptors=item.get("descriptors", []),
                    associated_symptoms=item.get("associated_symptoms", []),
                    # raw_text intentionally not stored — HIPAA
                )
                symptoms.append(symptom)
            except Exception as e:
                logger.warning(f"Failed to parse symptom item: {e}")
                continue

        return symptoms, True

    except Exception as e:
        logger.error(f"LLM extraction failed: {e}")
        return [], False
