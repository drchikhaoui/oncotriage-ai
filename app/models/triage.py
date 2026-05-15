from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TriageLevel(str, Enum):
    EMERGENCY = "EMERGENCY"
    URGENT = "URGENT"
    ROUTINE = "ROUTINE"
    SELF_CARE = "SELF_CARE"


class ReasoningStep(BaseModel):
    step: int
    finding: str
    source: Optional[str] = None


class TriageResult(BaseModel):
    session_id: str
    triage_level: TriageLevel
    emoji: str
    color: str
    action: str
    timeframe: str
    reasoning_steps: list[ReasoningStep]
    triggered_rules: list[str] = Field(default_factory=list, description="Rule IDs that fired")
    citations: list[str] = Field(default_factory=list)
    symptoms_graded: list[dict] = Field(default_factory=list)
    llm_used: bool = False
    irae_suspected: bool = False
    confidence: str = Field(default="high", description="high | medium | low")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    disclaimer: str = (
        "This tool is for clinical decision support only. "
        "It does not replace the clinical judgment of a licensed healthcare provider. "
        "All triage recommendations must be reviewed by qualified medical personnel."
    )
