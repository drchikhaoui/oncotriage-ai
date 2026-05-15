from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SymptomName(str, Enum):
    FEVER = "fever"
    NAUSEA = "nausea"
    VOMITING = "vomiting"
    DIARRHEA = "diarrhea"
    CONSTIPATION = "constipation"
    FATIGUE = "fatigue"
    PAIN = "pain"
    DYSPNEA = "dyspnea"
    MUCOSITIS = "mucositis"
    PERIPHERAL_NEUROPATHY = "peripheral_neuropathy"
    BLEEDING = "bleeding"
    NEUROLOGIC = "neurologic"
    ANXIETY = "anxiety"
    DEPRESSION = "depression"
    ANOREXIA = "anorexia"
    SKIN_RASH = "skin_rash"
    SKIN_REACTIONS = "skin_reactions"
    SLEEP_WAKE_DISTURBANCE = "sleep_wake_disturbance"
    XEROSTOMIA = "xerostomia"
    OTHER = "other"


class CTCAEGrade(int, Enum):
    GRADE_1 = 1
    GRADE_2 = 2
    GRADE_3 = 3
    GRADE_4 = 4
    GRADE_5 = 5


class Symptom(BaseModel):
    name: SymptomName
    ctcae_grade: Optional[CTCAEGrade] = None
    severity_descriptor: Optional[str] = Field(
        None, description="Free text from patient: mild/moderate/severe or qualitative"
    )
    duration_hours: Optional[float] = Field(None, description="Duration in hours")
    onset: Optional[str] = Field(None, description="sudden | gradual | unknown")
    temperature_celsius: Optional[float] = Field(None, description="Measured temperature if fever")
    pain_nrs: Optional[int] = Field(None, ge=0, le=10, description="Numeric Rating Scale 0-10")
    episodes_per_24h: Optional[int] = Field(None, description="For vomiting/diarrhea")
    stools_above_baseline: Optional[int] = Field(None, description="For diarrhea grading")
    at_rest: Optional[bool] = Field(None, description="For dyspnea — occurs at rest?")
    uncontrolled: Optional[bool] = Field(None, description="Unresponsive to current treatment")
    descriptors: list[str] = Field(default_factory=list, description="Associated descriptors/keywords")
    associated_symptoms: list[str] = Field(default_factory=list)
    raw_text: Optional[str] = Field(None, description="Original patient text — not stored in DB")


class SymptomIntakeRequest(BaseModel):
    """Intake payload — supports both free-text and structured input."""
    free_text: Optional[str] = Field(None, description="Patient's own words describing symptoms")
    structured_symptoms: list[Symptom] = Field(
        default_factory=list,
        description="Pre-structured symptoms (from form or fallback mode)"
    )
    session_id: str
    last_chemo_date: Optional[str] = Field(None, description="ISO date string YYYY-MM-DD")
    thrombocytopenia_history: bool = False
    cancer_type: Optional[str] = None
    treatment_status: Optional[str] = None
    treatment_modalities: list[str] = Field(default_factory=list)
    treatment_line: Optional[str] = None
    locale: str = Field("en", description="en | fr | ar")
    current_medications: list[str] = Field(default_factory=list)
