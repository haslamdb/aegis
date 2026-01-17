"""Coverage matching logic.

Determines if a patient's current antibiotic regimen provides
adequate coverage for identified organisms in blood cultures.
"""

from .coverage_rules import (
    OrganismCategory,
    categorize_organism,
    get_antibiotic_name,
    get_coverage_rule,
)
from .models import Antibiotic, CoverageAssessment, CoverageStatus, CultureResult, Patient


def extract_rxnorm_codes(antibiotics: list[Antibiotic]) -> set[str]:
    """Extract RxNorm codes from antibiotic list."""
    codes = set()
    for abx in antibiotics:
        if abx.rxnorm_code:
            codes.add(abx.rxnorm_code)
    return codes


def assess_coverage(
    patient: Patient,
    culture: CultureResult,
    antibiotics: list[Antibiotic],
) -> CoverageAssessment:
    """
    Assess whether current antibiotics provide adequate coverage.

    Args:
        patient: Patient information
        culture: Blood culture result
        antibiotics: List of active antibiotic orders

    Returns:
        CoverageAssessment with status and recommendations
    """
    assessment = CoverageAssessment(
        patient=patient,
        culture=culture,
        current_antibiotics=antibiotics,
    )

    # Categorize the organism
    organism_category = categorize_organism(
        culture.organism or "",
        culture.gram_stain,
    )

    # If we can't categorize, mark as unknown
    if organism_category == OrganismCategory.UNKNOWN:
        assessment.coverage_status = CoverageStatus.UNKNOWN
        assessment.recommendation = "Unable to assess coverage - organism not identified"
        return assessment

    # Get coverage rule
    rule = get_coverage_rule(organism_category)
    if not rule:
        assessment.coverage_status = CoverageStatus.UNKNOWN
        assessment.recommendation = f"No coverage rule defined for {organism_category.value}"
        return assessment

    # Get current antibiotic codes
    current_codes = extract_rxnorm_codes(antibiotics)

    # Check for adequate coverage
    if not current_codes:
        # No antibiotics at all
        assessment.coverage_status = CoverageStatus.INADEQUATE
        assessment.recommendation = rule.recommendation
        assessment.missing_coverage = [
            get_antibiotic_name(code) for code in list(rule.adequate_antibiotics)[:3]
        ]
        return assessment

    # Check if any current antibiotic provides adequate coverage
    adequate_match = current_codes & rule.adequate_antibiotics
    if adequate_match:
        assessment.coverage_status = CoverageStatus.ADEQUATE
        covering_abx = [get_antibiotic_name(code) for code in adequate_match]
        assessment.recommendation = f"Adequate coverage with {', '.join(covering_abx)}"
        return assessment

    # Check if patient is on known inadequate antibiotics
    inadequate_match = current_codes & rule.inadequate_antibiotics
    if inadequate_match:
        assessment.coverage_status = CoverageStatus.INADEQUATE
        assessment.recommendation = rule.recommendation
        inadequate_names = [get_antibiotic_name(code) for code in inadequate_match]
        assessment.missing_coverage = [
            f"Current {', '.join(inadequate_names)} does not cover {organism_category.value}"
        ]
        return assessment

    # Current antibiotics don't match known adequate or inadequate - uncertain
    assessment.coverage_status = CoverageStatus.INADEQUATE
    assessment.recommendation = rule.recommendation
    return assessment


def should_alert(assessment: CoverageAssessment) -> bool:
    """Determine if an alert should be generated."""
    return assessment.coverage_status == CoverageStatus.INADEQUATE
