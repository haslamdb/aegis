"""Data models for the dosing verification rules engine."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class MedicationOrder:
    """A single medication order from FHIR."""
    drug_name: str
    dose_value: float
    dose_unit: str          # mg, mg/kg, g
    interval: str           # q6h, q8h, q12h, q24h, etc.
    route: str              # IV, PO, IM, IT
    frequency_hours: int    # Normalized: q8h → 8
    daily_dose: float       # Calculated total daily dose
    daily_dose_per_kg: float | None  # If weight available
    start_date: str
    order_id: str
    infusion_duration_minutes: int | None = None  # For extended infusion checks
    rxnorm_code: str | None = None


@dataclass
class PatientContext:
    """All data needed for dosing evaluation, assembled from FHIR."""
    patient_id: str
    patient_mrn: str
    patient_name: str
    encounter_id: str | None

    # Demographics
    age_years: float | None
    weight_kg: float | None
    height_cm: float | None
    gestational_age_weeks: int | None  # Neonates only
    bsa: float | None                   # Body surface area (calculated)

    # Renal
    scr: float | None
    gfr: float | None
    crcl: float | None                  # Cockcroft-Gault CrCl
    is_on_dialysis: bool = False
    dialysis_type: str | None = None    # HD, CRRT, PD

    # Current antimicrobials
    antimicrobials: list[MedicationOrder] = field(default_factory=list)

    # Indication (from ABX Indications module)
    indication: str | None = None
    indication_confidence: float | None = None
    indication_source: str | None = None

    # Co-medications (for DDI)
    co_medications: list[MedicationOrder] = field(default_factory=list)

    # Allergies
    allergies: list[dict] = field(default_factory=list)  # [{substance, severity, reaction}]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "patient_id": self.patient_id,
            "patient_mrn": self.patient_mrn,
            "patient_name": self.patient_name,
            "encounter_id": self.encounter_id,
            "age_years": self.age_years,
            "weight_kg": self.weight_kg,
            "height_cm": self.height_cm,
            "gestational_age_weeks": self.gestational_age_weeks,
            "bsa": self.bsa,
            "scr": self.scr,
            "gfr": self.gfr,
            "crcl": self.crcl,
            "is_on_dialysis": self.is_on_dialysis,
            "dialysis_type": self.dialysis_type,
            "antimicrobials": [
                {
                    "drug_name": med.drug_name,
                    "dose_value": med.dose_value,
                    "dose_unit": med.dose_unit,
                    "interval": med.interval,
                    "route": med.route,
                    "frequency_hours": med.frequency_hours,
                    "daily_dose": med.daily_dose,
                    "daily_dose_per_kg": med.daily_dose_per_kg,
                    "start_date": med.start_date,
                    "order_id": med.order_id,
                }
                for med in self.antimicrobials
            ],
            "indication": self.indication,
            "indication_confidence": self.indication_confidence,
            "indication_source": self.indication_source,
            "co_medications": [
                {
                    "drug_name": med.drug_name,
                    "dose_value": med.dose_value,
                    "dose_unit": med.dose_unit,
                    "interval": med.interval,
                }
                for med in self.co_medications
            ],
            "allergies": self.allergies,
        }
