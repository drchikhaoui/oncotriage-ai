from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TreatmentModality(str, Enum):
    CYTOTOXIC_CHEMO = "cytotoxic_chemo"
    IMMUNOTHERAPY = "immunotherapy"
    TARGETED_THERAPY = "targeted_therapy"
    RADIATION = "radiation"
    HORMONAL = "hormonal_endocrine"
    CAR_T = "car_t"
    STEM_CELL_TRANSPLANT = "stem_cell_transplant"


class TreatmentLine(str, Enum):
    FIRST = "first"
    SECOND = "second"
    THIRD_PLUS = "third_plus"
    MAINTENANCE = "maintenance"
    SURVEILLANCE = "surveillance"


class PatientContext(BaseModel):
    """Anonymous patient context — no PII stored."""
    session_id: str
    cancer_type: Optional[str] = None
    treatment_modalities: list[TreatmentModality] = Field(default_factory=list)
    treatment_line: Optional[TreatmentLine] = None
    last_chemo_date: Optional[date] = None
    thrombocytopenia_history: bool = False
    current_medications: list[str] = Field(default_factory=list)
    locale: str = Field("en", description="Patient locale: en | fr | ar")

    @property
    def days_since_chemo(self) -> Optional[int]:
        if self.last_chemo_date is None:
            return None
        return (date.today() - self.last_chemo_date).days

    @property
    def recent_chemo(self) -> bool:
        """Within standard 14-day neutropenic window."""
        d = self.days_since_chemo
        return d is not None and d <= 14

    @property
    def recent_chemo_car_t(self) -> bool:
        """CAR-T/SCT 30-day extended window."""
        d = self.days_since_chemo
        return d is not None and d <= 30

    @property
    def has_immunotherapy(self) -> bool:
        return TreatmentModality.IMMUNOTHERAPY in self.treatment_modalities

    @property
    def has_cytotoxic(self) -> bool:
        return TreatmentModality.CYTOTOXIC_CHEMO in self.treatment_modalities

    @property
    def has_car_t_or_transplant(self) -> bool:
        return (TreatmentModality.CAR_T in self.treatment_modalities or
                TreatmentModality.STEM_CELL_TRANSPLANT in self.treatment_modalities)

    @property
    def febrile_neutropenia_applies(self) -> bool:
        """FN protocol applies for cytotoxic chemo, CAR-T, or SCT within window."""
        if self.has_car_t_or_transplant and self.recent_chemo_car_t:
            return True
        if self.has_cytotoxic and self.recent_chemo:
            return True
        return False

    @property
    def treatment_modalities_str(self) -> list[str]:
        return [m.value for m in self.treatment_modalities]
