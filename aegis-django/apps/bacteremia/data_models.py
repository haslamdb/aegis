"""Data models for Bacteremia Monitoring.

Pure Python dataclasses - NOT Django models. These represent the domain
objects used by the matcher and FHIR client.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class CoverageStatus(Enum):
    """Coverage assessment result."""
    ADEQUATE = "adequate"
    INADEQUATE = "inadequate"
    UNKNOWN = "unknown"


@dataclass
class Patient:
    """Patient information."""
    fhir_id: str
    mrn: str
    name: str
    birth_date: Optional[str] = None
    gender: Optional[str] = None
    location: Optional[str] = None


@dataclass
class Antibiotic:
    """Active antibiotic order."""
    fhir_id: str
    medication_name: str
    rxnorm_code: Optional[str] = None
    route: Optional[str] = None
    status: str = "active"


@dataclass
class CultureResult:
    """Blood culture result."""
    fhir_id: str
    patient_id: str
    organism: Optional[str] = None
    gram_stain: Optional[str] = None
    status: str = "final"
    collected_date: Optional[datetime] = None
    resulted_date: Optional[datetime] = None


@dataclass
class CoverageAssessment:
    """Complete coverage assessment for a patient/culture."""
    patient: Patient
    culture: CultureResult
    current_antibiotics: list[Antibiotic] = field(default_factory=list)
    coverage_status: CoverageStatus = CoverageStatus.UNKNOWN
    organism_category: str = ""
    recommendation: str = ""
    missing_coverage: list[str] = field(default_factory=list)

    def to_alert_content(self) -> dict:
        """Convert assessment to alert content dictionary."""
        return {
            "culture_id": self.culture.fhir_id,
            "organism": self.culture.organism,
            "gram_stain": self.culture.gram_stain,
            "organism_category": self.organism_category,
            "coverage_status": self.coverage_status.value,
            "collected_date": (
                self.culture.collected_date.isoformat()
                if self.culture.collected_date
                else None
            ),
            "current_antibiotics": [
                {
                    "name": abx.medication_name,
                    "rxnorm": abx.rxnorm_code,
                    "route": abx.route,
                }
                for abx in self.current_antibiotics
            ],
            "recommendation": self.recommendation,
            "missing_coverage": self.missing_coverage,
        }
