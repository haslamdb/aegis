"""Data models for allergy-aware antibiotic recommendations."""

from dataclasses import dataclass, field
from enum import Enum


class AntibioticClass(Enum):
    """Major antibiotic drug classes for allergy cross-reactivity."""
    PENICILLIN = "penicillin"
    CEPHALOSPORIN = "cephalosporin"
    CARBAPENEM = "carbapenem"
    MONOBACTAM = "monobactam"  # Aztreonam - safe in penicillin allergy
    FLUOROQUINOLONE = "fluoroquinolone"
    AMINOGLYCOSIDE = "aminoglycoside"
    GLYCOPEPTIDE = "glycopeptide"  # Vancomycin, telavancin
    LIPOPEPTIDE = "lipopeptide"  # Daptomycin
    OXAZOLIDINONE = "oxazolidinone"  # Linezolid
    MACROLIDE = "macrolide"
    TETRACYCLINE = "tetracycline"
    SULFONAMIDE = "sulfonamide"
    NITROIMIDAZOLE = "nitroimidazole"  # Metronidazole
    ANTIFUNGAL_AZOLE = "antifungal_azole"
    ANTIFUNGAL_ECHINOCANDIN = "antifungal_echinocandin"
    ANTIFUNGAL_POLYENE = "antifungal_polyene"  # Amphotericin
    OTHER = "other"


class CrossReactivityRisk(Enum):
    """Risk level for cross-reactivity between drug classes."""
    NONE = "none"  # No known cross-reactivity
    LOW = "low"  # <2% cross-reactivity (e.g., penicillin → 3rd gen cephalosporin)
    MODERATE = "moderate"  # 2-10% cross-reactivity
    HIGH = "high"  # >10% cross-reactivity (e.g., penicillin → 1st gen cephalosporin)
    CONTRAINDICATED = "contraindicated"  # Same class or known severe reaction


@dataclass
class AllergyConflict:
    """Represents a conflict between a recommendation and patient allergy."""
    antibiotic: str
    antibiotic_class: AntibioticClass
    allergy_substance: str
    allergy_class: AntibioticClass
    cross_reactivity_risk: CrossReactivityRisk
    is_anaphylaxis_history: bool
    warning_message: str

    @property
    def is_contraindicated(self) -> bool:
        """Check if this is an absolute contraindication."""
        if self.is_anaphylaxis_history:
            # Any risk is too high with anaphylaxis history
            return self.cross_reactivity_risk != CrossReactivityRisk.NONE
        return self.cross_reactivity_risk == CrossReactivityRisk.CONTRAINDICATED

    @property
    def requires_caution(self) -> bool:
        """Check if this requires caution but may be usable."""
        if self.is_anaphylaxis_history:
            return False  # No, it's contraindicated
        return self.cross_reactivity_risk in [
            CrossReactivityRisk.LOW,
            CrossReactivityRisk.MODERATE,
        ]


@dataclass
class SafeRecommendation:
    """A recommendation that has been filtered for allergy safety."""
    original_recommendations: list[str]
    safe_recommendations: list[str]
    excluded_antibiotics: list[AllergyConflict] = field(default_factory=list)
    caution_antibiotics: list[AllergyConflict] = field(default_factory=list)
    alternative_suggestions: list[str] = field(default_factory=list)
    warning_text: str | None = None

    @property
    def has_conflicts(self) -> bool:
        """Check if any recommendations had allergy conflicts."""
        return len(self.excluded_antibiotics) > 0 or len(self.caution_antibiotics) > 0

    @property
    def has_safe_options(self) -> bool:
        """Check if there are any safe recommendations left."""
        return len(self.safe_recommendations) > 0

    def get_recommendation_text(self) -> str:
        """Generate recommendation text incorporating allergy considerations."""
        parts = []

        if self.safe_recommendations:
            parts.append(f"Consider: {', '.join(self.safe_recommendations)}")

        if self.caution_antibiotics:
            caution_names = [c.antibiotic for c in self.caution_antibiotics]
            parts.append(f"Use with caution (allergy history): {', '.join(caution_names)}")

        if self.excluded_antibiotics:
            excluded_names = [e.antibiotic for e in self.excluded_antibiotics]
            parts.append(f"AVOID (allergy): {', '.join(excluded_names)}")

        if self.alternative_suggestions:
            parts.append(f"Alternatives: {', '.join(self.alternative_suggestions)}")

        if self.warning_text:
            parts.append(self.warning_text)

        return " | ".join(parts) if parts else "No specific recommendations available."
