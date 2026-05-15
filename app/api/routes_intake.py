import uuid

from fastapi import APIRouter

router = APIRouter(prefix="/api/intake", tags=["intake"])


@router.get("/session")
async def new_session() -> dict:
    """Generate a new anonymous session ID for a patient intake."""
    return {"session_id": str(uuid.uuid4())}


@router.get("/symptoms/list")
async def list_supported_symptoms() -> dict:
    """Return list of symptoms the system can triage."""
    return {
        "symptoms": [
            {"id": "fever", "label": "Fever / High Temperature"},
            {"id": "nausea", "label": "Nausea"},
            {"id": "vomiting", "label": "Vomiting"},
            {"id": "diarrhea", "label": "Diarrhea"},
            {"id": "constipation", "label": "Constipation"},
            {"id": "fatigue", "label": "Fatigue / Tiredness"},
            {"id": "pain", "label": "Pain"},
            {"id": "dyspnea", "label": "Shortness of Breath"},
            {"id": "mucositis", "label": "Mouth Sores / Mucositis"},
            {"id": "peripheral_neuropathy", "label": "Numbness / Tingling (Neuropathy)"},
            {"id": "bleeding", "label": "Bleeding / Bruising"},
            {"id": "neurologic", "label": "Neurologic Symptoms (weakness, vision, headache)"},
        ]
    }
