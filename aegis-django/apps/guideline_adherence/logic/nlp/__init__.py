"""NLP extraction layer for Guideline Adherence.

Provides LLM-based extraction of clinical findings from notes:
- Clinical appearance (well/ill/toxic) with tiered triage+full model
- GI symptoms for C. diff testing appropriateness
"""

from .clinical_impression import (
    ClinicalAppearance,
    ClinicalImpressionResult,
    ClinicalImpressionExtractor,
    TieredClinicalImpressionExtractor,
    get_clinical_impression_extractor,
    get_tiered_clinical_impression_extractor,
)
from .triage_extractor import (
    TriageDecision,
    AppearanceTriageResult,
    ClinicalAppearanceTriageExtractor,
    get_triage_extractor,
)
from .gi_symptoms import (
    StoolConsistency,
    GISymptomResult,
    GISymptomExtractor,
    get_gi_symptom_extractor,
)

__all__ = [
    # Clinical impression
    "ClinicalAppearance",
    "ClinicalImpressionResult",
    "ClinicalImpressionExtractor",
    "TieredClinicalImpressionExtractor",
    "get_clinical_impression_extractor",
    "get_tiered_clinical_impression_extractor",
    # Triage
    "TriageDecision",
    "AppearanceTriageResult",
    "ClinicalAppearanceTriageExtractor",
    "get_triage_extractor",
    # GI symptoms
    "StoolConsistency",
    "GISymptomResult",
    "GISymptomExtractor",
    "get_gi_symptom_extractor",
]
