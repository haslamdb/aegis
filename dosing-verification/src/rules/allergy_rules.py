"""Allergy checking and cross-reactivity rules for antimicrobials.

Checks for direct allergy matches and cross-reactivity patterns.
"""

import logging
from typing import Any
from common.dosing_verification import DoseAlertSeverity, DoseFlag, DoseFlagType
from ..models import PatientContext
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


# Drug class membership for cross-reactivity checking
DRUG_CLASSES = {
    # Beta-lactams
    "penicillins": [
        "penicillin",
        "amoxicillin",
        "ampicillin",
        "piperacillin",
        "ticarcillin",
        "oxacillin",
        "nafcillin",
        "dicloxacillin",
    ],
    "cephalosporins": [
        "cefazolin",
        "cephalexin",
        "cefuroxime",
        "ceftriaxone",
        "ceftazidime",
        "cefepime",
        "ceftaroline",
        "cefiderocol",
    ],
    "carbapenems": [
        "meropenem",
        "imipenem",
        "ertapenem",
        "doripenem",
    ],
    "monobactams": [
        "aztreonam",
    ],
    # Aminoglycosides
    "aminoglycosides": [
        "gentamicin",
        "tobramycin",
        "amikacin",
    ],
    # Fluoroquinolones
    "fluoroquinolones": [
        "ciprofloxacin",
        "levofloxacin",
        "moxifloxacin",
    ],
    # Macrolides
    "macrolides": [
        "azithromycin",
        "clarithromycin",
        "erythromycin",
    ],
    # Tetracyclines
    "tetracyclines": [
        "doxycycline",
        "minocycline",
        "tetracycline",
    ],
    # Glycopeptides
    "glycopeptides": [
        "vancomycin",
        "teicoplanin",
    ],
    # Sulfonamides
    "sulfonamides": [
        "sulfamethoxazole",
        "trimethoprim-sulfamethoxazole",
        "bactrim",
        "septra",
    ],
}


# Cross-reactivity rules
CROSS_REACTIVITY_RULES = [
    {
        "allergy_class": "penicillins",
        "cross_reactive_class": "cephalosporins",
        "risk_level": "low",  # ~1-3% if no anaphylaxis
        "risk_level_anaphylaxis": "moderate",  # ~5-10% if prior anaphylaxis
        "severity": DoseAlertSeverity.HIGH,
        "severity_anaphylaxis": DoseAlertSeverity.CRITICAL,
        "message": "Penicillin allergy with potential cross-reactivity to cephalosporins.",
        "recommendation": "Safe if prior reaction was not anaphylaxis/severe. Consider allergy testing or alternative if severe reaction.",
        "source": "AAAAI Practice Parameter Update 2010",
    },
    {
        "allergy_class": "penicillins",
        "cross_reactive_class": "carbapenems",
        "risk_level": "low",  # ~1%
        "severity": DoseAlertSeverity.MODERATE,
        "message": "Penicillin allergy with low risk cross-reactivity to carbapenems.",
        "recommendation": "Generally safe unless prior severe/anaphylactic reaction.",
        "source": "Clinical literature review",
    },
    {
        "allergy_class": "penicillins",
        "cross_reactive_class": "monobactams",
        "risk_level": "minimal",  # <1%
        "severity": DoseAlertSeverity.MODERATE,
        "message": "Penicillin allergy - aztreonam has minimal cross-reactivity.",
        "recommendation": "Aztreonam is safe even with severe penicillin allergy.",
        "source": "Clinical literature review",
    },
    {
        "allergy_class": "cephalosporins",
        "cross_reactive_class": "penicillins",
        "risk_level": "low",
        "severity": DoseAlertSeverity.MODERATE,
        "message": "Cephalosporin allergy with potential cross-reactivity to penicillins.",
        "recommendation": "Generally safe unless severe reaction to cephalosporin.",
        "source": "Clinical literature review",
    },
    {
        "allergy_class": "cephalosporins",
        "cross_reactive_class": "carbapenems",
        "risk_level": "low",
        "severity": DoseAlertSeverity.MODERATE,
        "message": "Cephalosporin allergy with low cross-reactivity to carbapenems.",
        "recommendation": "Generally safe unless severe reaction.",
        "source": "Clinical literature review",
    },
    {
        "allergy_class": "aminoglycosides",
        "cross_reactive_class": "aminoglycosides",
        "risk_level": "high",  # Within class
        "severity": DoseAlertSeverity.HIGH,
        "message": "Aminoglycoside allergy - high cross-reactivity within class.",
        "recommendation": "Avoid all aminoglycosides if prior allergy.",
        "source": "Class effect",
    },
    {
        "allergy_class": "fluoroquinolones",
        "cross_reactive_class": "fluoroquinolones",
        "risk_level": "high",
        "severity": DoseAlertSeverity.HIGH,
        "message": "Fluoroquinolone allergy - high cross-reactivity within class.",
        "recommendation": "Avoid all fluoroquinolones if prior allergy.",
        "source": "Class effect",
    },
    {
        "allergy_class": "macrolides",
        "cross_reactive_class": "macrolides",
        "risk_level": "high",
        "severity": DoseAlertSeverity.HIGH,
        "message": "Macrolide allergy - high cross-reactivity within class.",
        "recommendation": "Avoid all macrolides if prior allergy.",
        "source": "Class effect",
    },
]


class AllergyRules(BaseRuleModule):
    """Check for drug allergies and cross-reactivity."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Check medication orders against patient allergies.

        Args:
            context: Patient clinical context

        Returns:
            List of DoseFlag objects for allergy issues
        """
        flags = []

        if not context.allergies:
            return flags

        for med in context.antimicrobials:
            # Check direct matches
            direct_match_flag = self._check_direct_match(med, context.allergies, context)
            if direct_match_flag:
                flags.append(direct_match_flag)
                continue  # Don't also flag cross-reactivity for direct match

            # Check cross-reactivity
            cross_react_flags = self._check_cross_reactivity(med, context.allergies, context)
            flags.extend(cross_react_flags)

        return flags

    def _check_direct_match(
        self, med: Any, allergies: list[dict], context: PatientContext
    ) -> DoseFlag | None:
        """Check for direct allergy to the ordered drug.

        Args:
            med: MedicationOrder
            allergies: List of allergy dicts
            context: Patient context

        Returns:
            DoseFlag if direct match found, else None
        """
        drug_lower = med.drug_name.lower()

        for allergy in allergies:
            substance = allergy.get("substance", "").lower()

            # Check for direct match
            if substance in drug_lower or drug_lower in substance:
                severity_str = allergy.get("severity", "unknown")
                reaction = allergy.get("reaction", "unknown")

                # Critical if severe/anaphylaxis
                if any(
                    term in severity_str.lower()
                    for term in ["severe", "anaphyl", "critical"]
                ):
                    severity = DoseAlertSeverity.CRITICAL
                else:
                    severity = DoseAlertSeverity.HIGH

                return DoseFlag(
                    flag_type=DoseFlagType.ALLERGY_CONTRAINDICATED,
                    severity=severity,
                    drug=med.drug_name,
                    message=f"Patient has documented allergy to {substance}. Ordered: {med.drug_name}.",
                    expected="Alternative antibiotic without allergy",
                    actual=f"{med.drug_name} {med.dose_value} {med.dose_unit} {med.route} {med.interval}",
                    rule_source="Patient allergy record",
                    indication=context.indication or "unknown",
                    details={
                        "allergen": substance,
                        "severity": severity_str,
                        "reaction": reaction,
                    },
                )

        return None

    def _check_cross_reactivity(
        self, med: Any, allergies: list[dict], context: PatientContext
    ) -> list[DoseFlag]:
        """Check for cross-reactivity with patient allergies.

        Args:
            med: MedicationOrder
            allergies: List of allergy dicts
            context: Patient context

        Returns:
            List of DoseFlag objects for cross-reactivity
        """
        flags = []
        drug_lower = med.drug_name.lower()

        # Find what class this drug belongs to
        drug_classes = self._get_drug_classes(drug_lower)

        if not drug_classes:
            return flags

        # Check each allergy
        for allergy in allergies:
            allergen = allergy.get("substance", "").lower()
            severity_str = allergy.get("severity", "unknown").lower()
            reaction = allergy.get("reaction", "unknown")

            # Find what class the allergen belongs to
            allergen_classes = self._get_drug_classes(allergen)

            if not allergen_classes:
                continue

            # Check cross-reactivity rules
            for allergen_class in allergen_classes:
                for drug_class in drug_classes:
                    # Find matching cross-reactivity rule
                    rule = self._find_cross_reactivity_rule(
                        allergen_class, drug_class
                    )

                    if not rule:
                        continue

                    # Determine severity based on prior reaction
                    is_severe_reaction = any(
                        term in severity_str
                        for term in ["severe", "anaphyl", "critical"]
                    )

                    if is_severe_reaction and "severity_anaphylaxis" in rule:
                        alert_severity = rule["severity_anaphylaxis"]
                    else:
                        alert_severity = rule["severity"]

                    flags.append(
                        DoseFlag(
                            flag_type=DoseFlagType.ALLERGY_CROSS_REACTIVITY,
                            severity=alert_severity,
                            drug=med.drug_name,
                            message=rule["message"],
                            expected=rule["recommendation"],
                            actual=f"{med.drug_name} {med.dose_value} {med.dose_unit} {med.route} {med.interval}",
                            rule_source=rule["source"],
                            indication=context.indication or "unknown",
                            details={
                                "allergen": allergen,
                                "allergen_class": allergen_class,
                                "drug_class": drug_class,
                                "risk_level": rule["risk_level"],
                                "prior_severity": severity_str,
                                "prior_reaction": reaction,
                            },
                        )
                    )

        return flags

    def _get_drug_classes(self, drug_name: str) -> list[str]:
        """Get all classes a drug belongs to.

        Args:
            drug_name: Drug name (lowercase)

        Returns:
            List of class names
        """
        classes = []

        for class_name, members in DRUG_CLASSES.items():
            if any(member in drug_name for member in members):
                classes.append(class_name)

        return classes

    def _find_cross_reactivity_rule(
        self, allergen_class: str, drug_class: str
    ) -> dict | None:
        """Find cross-reactivity rule for allergy class + drug class.

        Args:
            allergen_class: Class of the allergen
            drug_class: Class of the ordered drug

        Returns:
            Rule dict if found, else None
        """
        for rule in CROSS_REACTIVITY_RULES:
            if (
                rule["allergy_class"] == allergen_class
                and rule["cross_reactive_class"] == drug_class
            ):
                return rule

        return None
