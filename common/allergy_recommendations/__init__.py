"""Allergy-aware antibiotic recommendation support.

This module provides logic for filtering antibiotic recommendations based on
patient drug allergies, including cross-reactivity considerations.
"""

from .models import (
    AntibioticClass,
    CrossReactivityRisk,
    AllergyConflict,
    SafeRecommendation,
)
from .rules import (
    ANTIBIOTIC_CLASSES,
    CROSS_REACTIVITY_RULES,
    ALTERNATIVE_SUGGESTIONS,
    get_antibiotic_class,
    get_cross_reactivity_risk,
    check_allergy_conflict,
    filter_recommendations_by_allergies,
    get_safe_alternatives,
    adjust_recommendation_for_allergies,
)

__all__ = [
    # Models
    "AntibioticClass",
    "CrossReactivityRisk",
    "AllergyConflict",
    "SafeRecommendation",
    # Rules and functions
    "ANTIBIOTIC_CLASSES",
    "CROSS_REACTIVITY_RULES",
    "ALTERNATIVE_SUGGESTIONS",
    "get_antibiotic_class",
    "get_cross_reactivity_risk",
    "check_allergy_conflict",
    "filter_recommendations_by_allergies",
    "get_safe_alternatives",
    "adjust_recommendation_for_allergies",
]
