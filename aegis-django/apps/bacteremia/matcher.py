"""Coverage assessment logic for Bacteremia Monitoring.

Uses the clinical knowledge base from apps.asp_alerts.coverage_rules to
determine if a patient's current antibiotics provide adequate coverage
for the organism identified in a blood culture.
"""

from apps.asp_alerts.coverage_rules import (
    categorize_organism,
    get_coverage_rule,
    OrganismCategory,
)

from .data_models import (
    Antibiotic,
    CoverageAssessment,
    CoverageStatus,
    CultureResult,
    Patient,
)


def extract_rxnorm_codes(antibiotics: list[Antibiotic]) -> set[str]:
    """Extract the set of RxNorm codes from a list of antibiotics."""
    return {
        abx.rxnorm_code
        for abx in antibiotics
        if abx.rxnorm_code
    }


def assess_coverage(
    patient: Patient,
    culture: CultureResult,
    antibiotics: list[Antibiotic],
) -> CoverageAssessment:
    """
    Assess whether current antibiotics cover the blood culture organism.

    Uses organism categorization and coverage rules to determine if any
    current antibiotic provides adequate coverage.
    """
    # Categorize the organism
    category = categorize_organism(
        culture.organism or "",
        culture.gram_stain,
    )

    # If unknown organism, can't assess
    if category == OrganismCategory.UNKNOWN:
        return CoverageAssessment(
            patient=patient,
            culture=culture,
            current_antibiotics=antibiotics,
            coverage_status=CoverageStatus.UNKNOWN,
            organism_category=category.value,
            recommendation="Unable to assess coverage - organism not categorized",
        )

    # Get coverage rule for this organism category
    rule = get_coverage_rule(category)
    if not rule:
        return CoverageAssessment(
            patient=patient,
            culture=culture,
            current_antibiotics=antibiotics,
            coverage_status=CoverageStatus.UNKNOWN,
            organism_category=category.value,
            recommendation="No coverage rule defined for this organism category",
        )

    # Check if any current antibiotic is in the adequate set
    current_codes = extract_rxnorm_codes(antibiotics)

    if not current_codes:
        # No antibiotics at all
        return CoverageAssessment(
            patient=patient,
            culture=culture,
            current_antibiotics=antibiotics,
            coverage_status=CoverageStatus.INADEQUATE,
            organism_category=category.value,
            recommendation=rule.recommendation,
            missing_coverage=[rule.recommendation],
        )

    # Check for adequate coverage
    adequate_overlap = current_codes & rule.adequate_antibiotics
    if adequate_overlap:
        return CoverageAssessment(
            patient=patient,
            culture=culture,
            current_antibiotics=antibiotics,
            coverage_status=CoverageStatus.ADEQUATE,
            organism_category=category.value,
            recommendation="Current therapy provides adequate coverage",
        )

    # No adequate coverage found
    return CoverageAssessment(
        patient=patient,
        culture=culture,
        current_antibiotics=antibiotics,
        coverage_status=CoverageStatus.INADEQUATE,
        organism_category=category.value,
        recommendation=rule.recommendation,
        missing_coverage=[rule.recommendation],
    )


def should_alert(assessment: CoverageAssessment) -> bool:
    """Determine if an alert should be generated for this assessment."""
    return assessment.coverage_status == CoverageStatus.INADEQUATE
