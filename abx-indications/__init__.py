"""ABX Indications Module.

Provides indication taxonomy and LLM-based extraction for antibiotic stewardship.
Implements Joint Commission requirements for clinical syndrome documentation.
"""

from .indication_taxonomy import (
    TherapyIntent,
    IndicationCategory,
    IndicationMapping,
    INDICATION_TAXONOMY,
    get_indication_by_synonym,
    get_indications_by_category,
    get_never_appropriate_indications,
)

from .indication_extractor import (
    IndicationExtraction,
    IndicationExtractor,
    INDICATION_EXTRACTION_SCHEMA,
)

# Legacy imports for backward compatibility
try:
    from .pediatric_abx_indications import (
        AntibioticIndicationClassifier,
        IndicationCategory as LegacyIndicationCategory,
    )
except ImportError:
    AntibioticIndicationClassifier = None
    LegacyIndicationCategory = None

__all__ = [
    # Taxonomy
    "TherapyIntent",
    "IndicationCategory",
    "IndicationMapping",
    "INDICATION_TAXONOMY",
    "get_indication_by_synonym",
    "get_indications_by_category",
    "get_never_appropriate_indications",
    # Extraction
    "IndicationExtraction",
    "IndicationExtractor",
    "INDICATION_EXTRACTION_SCHEMA",
    # Legacy
    "AntibioticIndicationClassifier",
]
