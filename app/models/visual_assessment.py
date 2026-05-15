"""Pydantic models for the visual triage pipeline."""
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models.triage import TriageLevel


class ImageQuality(BaseModel):
    adequate: bool
    issues: list[Literal["blurry", "poor_lighting", "too_close", "too_far", "partial_view"]]
    retake_recommended: bool


class VisualFindings(BaseModel):
    body_surface_area_percent_estimate: int = Field(ge=0, le=100)
    distribution: Literal["localized", "regional", "generalized"]
    primary_morphology: list[str]
    secondary_features: list[str]
    anatomical_site: str


class CTCAEGradeVisual(BaseModel):
    grade: Optional[int] = Field(None, ge=1, le=4)
    ctcae_descriptor: str
    confidence: Literal["low", "moderate", "high"]


class VisualAssessment(BaseModel):
    image_quality: ImageQuality
    ae_match: bool
    ae_match_explanation: str
    visual_findings: Optional[VisualFindings] = None
    ctcae_grade_visual: Optional[CTCAEGradeVisual] = None
    caveats: list[str]
    language: Literal["en", "fr", "ar"] = "en"


class ExternalEnrichment(BaseModel):
    openfda_summary: Optional[str] = None
    openfda_report_count: Optional[int] = None
    pubmed_citations: list[dict] = Field(default_factory=list)
    nci_term: Optional[str] = None


class VisualTriageResult(BaseModel):
    """Full result from the visual triage pipeline."""
    assessment: VisualAssessment
    triage_level: Optional[TriageLevel] = None
    triage_rules: list[dict] = Field(default_factory=list)
    graded_symptoms: list[dict] = Field(default_factory=list)
    status: Literal["success", "retake_required", "ambiguous"]
    suspected_ae: str
    enrichment: Optional[ExternalEnrichment] = None
    session_id: str
    irae_suspected: bool = False
    provider_used: Optional[str] = None
    model_used: Optional[str] = None
    # anatomical_location_hint: user-selected location, used as fallback if AI returns null
    anatomical_location_hint: Optional[str] = None
    # thumbnail_data_url is populated ephemerally by the route handler (never stored)
    thumbnail_data_url: Optional[str] = None
