"""Age-based dosing rules for antimicrobial dosing verification.

Flags when antimicrobials are dosed inappropriately for patient age:
- Neonatal-specific dosing (< 28 days)
- Pediatric-specific dosing (28 days - 18 years)
- Age-based contraindications
"""

import logging
from typing import Any

from common.dosing_verification import DoseAlertSeverity, DoseFlagType, DoseFlag
from ..models import PatientContext, MedicationOrder
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


# Age-based dosing rules
# Structure: {
#   "neonatal": {
#       "age_days_max": 28,
#       "dose_mg_kg": X,
#       "interval_by_age": {...},
#       "contraindications": [...],
#   },
#   "infant": {...},
#   "pediatric": {...},
#   "adult": {...},
# }

AGE_BASED_RULES = {
    "ceftriaxone": {
        "neonatal": {
            "contraindications": [
                {
                    "condition": "hyperbilirubinemia",
                    "severity": "critical",
                    "message": "Ceftriaxone contraindicated in neonates with hyperbilirubinemia (displaces bilirubin from albumin)",
                    "source": "AAP Red Book, FDA Black Box Warning",
                },
                {
                    "age_days_max": 28,
                    "severity": "high",
                    "message": "Ceftriaxone generally avoided in first 28 days of life due to bilirubin displacement risk",
                    "source": "AAP Red Book",
                },
            ],
        },
        "pediatric": {
            "dose_mg_kg_day": {"standard": 50, "meningitis": 100},
            "interval_options": ["q24h", "q12h"],
            "max_daily_mg": 4000,
        },
        "severity": "critical",
        "source": "AAP Red Book, IDSA Guidelines",
    },
    "gentamicin": {
        "neonatal": {
            "interval_by_pma_and_pna": {
                # PMA = postmenstrual age, PNA = postnatal age
                "lt_29_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 5, "interval_h": 48},
                    "gt_7_days_pna": {"dose_mg_kg": 4, "interval_h": 36},
                },
                "30_34_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 4.5, "interval_h": 36},
                    "gt_7_days_pna": {"dose_mg_kg": 4, "interval_h": 24},
                },
                "ge_35_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 4, "interval_h": 24},
                    "gt_7_days_pna": {"dose_mg_kg": 4, "interval_h": 24},
                },
            },
            "note": "Neonatal gentamicin dosing by gestational/postnatal age. Monitor levels.",
        },
        "pediatric": {
            "dose_mg_kg": 7,
            "interval": "q24h",
            "note": "Extended-interval dosing for age > 1 month",
        },
        "severity": "high",
        "source": "AAP Red Book, NeoFax 2024",
    },
    "tobramycin": {
        "neonatal": {
            "interval_by_pma_and_pna": {
                "lt_29_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 5, "interval_h": 48},
                    "gt_7_days_pna": {"dose_mg_kg": 4, "interval_h": 36},
                },
                "30_34_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 4.5, "interval_h": 36},
                    "gt_7_days_pna": {"dose_mg_kg": 4, "interval_h": 24},
                },
                "ge_35_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 4, "interval_h": 24},
                    "gt_7_days_pna": {"dose_mg_kg": 4, "interval_h": 24},
                },
            },
            "note": "Neonatal tobramycin dosing by gestational/postnatal age. Monitor levels.",
        },
        "pediatric": {
            "dose_mg_kg": 7,
            "interval": "q24h",
        },
        "severity": "high",
        "source": "AAP Red Book, NeoFax 2024",
    },
    "ampicillin": {
        "neonatal": {
            "interval_by_pma_and_pna": {
                "lt_29_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 50, "interval_h": 12},
                    "gt_7_days_pna": {"dose_mg_kg": 50, "interval_h": 8},
                },
                "30_36_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 50, "interval_h": 12},
                    "gt_7_days_pna": {"dose_mg_kg": 50, "interval_h": 6},
                },
                "ge_37_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 50, "interval_h": 8},
                    "gt_7_days_pna": {"dose_mg_kg": 50, "interval_h": 6},
                },
            },
            "meningitis_dose_mg_kg": 100,
            "note": "Neonatal ampicillin: higher dose for meningitis (100 mg/kg q6-8h)",
        },
        "pediatric": {
            "dose_mg_kg_day": {"standard": 200, "meningitis": 300},
            "interval_options": ["q6h", "q8h"],
        },
        "severity": "high",
        "source": "AAP Red Book, NeoFax 2024",
    },
    "acyclovir": {
        "neonatal": {
            "dose_mg_kg": 20,
            "interval": "q8h",
            "note": "High-dose for neonatal HSV (disseminated, CNS, or SEM disease)",
            "duration_days": {"disseminated_cns": 21, "sem": 14},
        },
        "pediatric": {
            "dose_mg_kg": {"mucocutaneous": 10, "encephalitis": 20},
            "interval": "q8h",
        },
        "severity": "critical",
        "source": "AAP Red Book, IDSA HSV Guidelines",
    },
    "vancomycin": {
        "neonatal": {
            "interval_by_pma_and_pna": {
                "lt_29_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 15, "interval_h": 24},
                    "gt_7_days_pna": {"dose_mg_kg": 15, "interval_h": 18},
                },
                "30_36_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 15, "interval_h": 18},
                    "gt_7_days_pna": {"dose_mg_kg": 15, "interval_h": 12},
                },
                "ge_37_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 15, "interval_h": 12},
                    "gt_7_days_pna": {"dose_mg_kg": 15, "interval_h": 8},
                },
            },
            "note": "Neonatal vancomycin: interval by gestational/postnatal age. Target trough 10-15 mcg/mL.",
        },
        "pediatric": {
            "dose_mg_kg_day": 60,
            "interval_options": ["q6h", "q8h"],
            "target_trough": "10-15",
        },
        "severity": "moderate",
        "source": "AAP Red Book, NeoFax 2024",
    },
    "metronidazole": {
        "neonatal": {
            "interval_by_pma_and_pna": {
                "lt_37_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 7.5, "interval_h": 48},
                    "gt_7_days_pna": {"dose_mg_kg": 7.5, "interval_h": 24},
                },
                "ge_37_weeks_pma": {
                    "0_7_days_pna": {"dose_mg_kg": 7.5, "interval_h": 24},
                    "gt_7_days_pna": {"dose_mg_kg": 7.5, "interval_h": 12},
                },
            },
        },
        "pediatric": {
            "dose_mg_kg": 7.5,
            "interval": "q6h",
        },
        "severity": "moderate",
        "source": "AAP Red Book, NeoFax 2024",
    },
    "fluconazole": {
        "neonatal": {
            "dose_mg_kg": {"prophylaxis": 3, "treatment": 12},
            "interval": "q72h",  # First 2 weeks of life
            "note": "Neonatal fluconazole: q72h for first 2 weeks, then q48h until 4 weeks, then q24h",
        },
        "pediatric": {
            "dose_mg_kg": {"standard": 6, "candidemia": 12},
            "interval": "q24h",
        },
        "severity": "moderate",
        "source": "AAP Red Book, IDSA Candidiasis Guidelines",
    },
    "fluoroquinolone": {
        "pediatric": {
            "contraindications": [
                {
                    "age_years_max": 18,
                    "severity": "high",
                    "message": "Fluoroquinolones generally avoided in children < 18 years due to risk of arthropathy",
                    "exceptions": "May be used for specific indications (e.g., complicated UTI, cystic fibrosis exacerbation) when benefit > risk",
                    "source": "AAP Red Book, FDA Black Box Warning",
                },
            ],
        },
        "severity": "high",
        "source": "AAP Red Book",
    },
    "tetracycline": {
        "pediatric": {
            "contraindications": [
                {
                    "age_years_max": 8,
                    "severity": "high",
                    "message": "Tetracyclines contraindicated in children < 8 years (permanent tooth discoloration, enamel hypoplasia)",
                    "exceptions": "Doxycycline may be used for severe infections (e.g., RMSF) when benefit > risk",
                    "source": "AAP Red Book, FDA Warning",
                },
            ],
        },
        "severity": "high",
        "source": "AAP Red Book",
    },
    "doxycycline": {
        "pediatric": {
            "contraindications": [
                {
                    "age_years_max": 8,
                    "severity": "moderate",
                    "message": "Doxycycline use in children < 8 years: weigh risk of tooth staining vs benefit",
                    "exceptions": "Short courses (< 21 days) have minimal tooth staining risk. Use for severe infections (RMSF, ehrlichiosis).",
                    "source": "AAP Red Book 2021",
                },
            ],
        },
        "severity": "moderate",
        "source": "AAP Red Book",
    },
}


def age_days_to_years(age_years: float | None, age_days: int | None = None) -> float | None:
    """Convert age to years."""
    if age_years is not None:
        return age_years
    if age_days is not None:
        return age_days / 365.25
    return None


def classify_age_group(age_years: float | None) -> str:
    """Classify patient into age group.

    Args:
        age_years: Age in years

    Returns:
        Age group: "neonate", "infant", "child", "adolescent", "adult"
    """
    if age_years is None:
        return "unknown"

    if age_years < (28 / 365.25):  # < 28 days
        return "neonate"
    elif age_years < 2:
        return "infant"
    elif age_years < 12:
        return "child"
    elif age_years < 18:
        return "adolescent"
    else:
        return "adult"


class AgeBasedRules(BaseRuleModule):
    """Check if antimicrobial dosing is appropriate for patient age."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Evaluate age-based dosing for all antimicrobials.

        Args:
            context: Patient clinical context

        Returns:
            List of DoseFlag objects for age-based issues
        """
        flags: list[DoseFlag] = []

        # If no age data, skip
        if context.age_years is None:
            logger.debug(f"No age data for {context.patient_mrn}, skipping age rules")
            return flags

        age_group = classify_age_group(context.age_years)

        # Check each antimicrobial
        for med in context.antimicrobials:
            drug_lower = med.drug_name.lower()

            # Find matching drug in age rules
            drug_key = self._match_drug(drug_lower)
            if not drug_key:
                continue

            rule = AGE_BASED_RULES[drug_key]

            # Check contraindications first
            if "contraindications" in rule.get("neonatal", {}):
                for contraindication in rule["neonatal"]["contraindications"]:
                    flag = self._check_contraindication(
                        med, contraindication, context, drug_key, age_group
                    )
                    if flag:
                        flags.append(flag)

            if "contraindications" in rule.get("pediatric", {}):
                for contraindication in rule["pediatric"]["contraindications"]:
                    flag = self._check_contraindication(
                        med, contraindication, context, drug_key, age_group
                    )
                    if flag:
                        flags.append(flag)

            # Check neonatal dosing
            if age_group == "neonate" and "neonatal" in rule:
                flag = self._check_neonatal_dosing(med, rule["neonatal"], context, drug_key)
                if flag:
                    flags.append(flag)

        return flags

    def _match_drug(self, drug_name: str) -> str | None:
        """Match drug name to age rules key."""
        # Direct match
        if drug_name in AGE_BASED_RULES:
            return drug_name

        # Fuzzy matches
        matches = {
            "ceftriax": "ceftriaxone",
            "gent": "gentamicin",
            "tobra": "tobramycin",
            "amp": "ampicillin",
            "ampic": "ampicillin",
            "acyclo": "acyclovir",
            "vanc": "vancomycin",
            "metro": "metronidazole",
            "flagyl": "metronidazole",
            "flucon": "fluconazole",
            "cipro": "fluoroquinolone",
            "levo": "fluoroquinolone",
            "moxi": "fluoroquinolone",
            "doxy": "doxycycline",
            "tetra": "tetracycline",
        }

        for pattern, key in matches.items():
            if pattern in drug_name:
                return key

        return None

    def _check_contraindication(
        self,
        med: MedicationOrder,
        contraindication: dict,
        context: PatientContext,
        drug_key: str,
        age_group: str,
    ) -> DoseFlag | None:
        """Check if drug is contraindicated for this age.

        Args:
            med: Medication order
            contraindication: Contraindication rule
            context: Patient context
            drug_key: Drug key
            age_group: Patient age group

        Returns:
            DoseFlag if contraindicated, None otherwise
        """
        # Check age threshold
        age_days_max = contraindication.get("age_days_max")
        age_years_max = contraindication.get("age_years_max")

        if age_days_max:
            age_days = context.age_years * 365.25 if context.age_years else None
            if age_days and age_days <= age_days_max:
                return DoseFlag(
                    flag_type=DoseFlagType.CONTRAINDICATED,
                    severity=self._parse_severity(contraindication.get("severity", "high")),
                    drug=med.drug_name,
                    message=contraindication.get("message", f"{med.drug_name} contraindicated in this age group"),
                    expected="Contraindicated",
                    actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                    rule_source=contraindication.get("source", AGE_BASED_RULES[drug_key].get("source", "Pediatric guidelines")),
                    indication=context.indication or "Unknown",
                    details={
                        "age_years": context.age_years,
                        "age_group": age_group,
                        "exceptions": contraindication.get("exceptions", ""),
                    },
                )

        if age_years_max:
            if context.age_years and context.age_years <= age_years_max:
                return DoseFlag(
                    flag_type=DoseFlagType.CONTRAINDICATED,
                    severity=self._parse_severity(contraindication.get("severity", "high")),
                    drug=med.drug_name,
                    message=contraindication.get("message", f"{med.drug_name} contraindicated in this age group"),
                    expected="Contraindicated (or use with extreme caution)",
                    actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                    rule_source=contraindication.get("source", AGE_BASED_RULES[drug_key].get("source", "Pediatric guidelines")),
                    indication=context.indication or "Unknown",
                    details={
                        "age_years": context.age_years,
                        "age_group": age_group,
                        "exceptions": contraindication.get("exceptions", ""),
                    },
                )

        # Check condition-based contraindication (e.g., hyperbilirubinemia)
        condition = contraindication.get("condition")
        if condition:
            # For MVP, flag for review if neonate
            if age_group == "neonate":
                return DoseFlag(
                    flag_type=DoseFlagType.CONTRAINDICATED,
                    severity=self._parse_severity(contraindication.get("severity", "high")),
                    drug=med.drug_name,
                    message=f"{med.drug_name} in neonate: verify no {condition}",
                    expected=f"Contraindicated if {condition} present",
                    actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                    rule_source=contraindication.get("source", AGE_BASED_RULES[drug_key].get("source", "Pediatric guidelines")),
                    indication=context.indication or "Unknown",
                    details={
                        "age_years": context.age_years,
                        "age_group": age_group,
                        "condition": condition,
                    },
                )

        return None

    def _check_neonatal_dosing(
        self,
        med: MedicationOrder,
        neonatal_rule: dict,
        context: PatientContext,
        drug_key: str,
    ) -> DoseFlag | None:
        """Check neonatal dosing appropriateness.

        Args:
            med: Medication order
            neonatal_rule: Neonatal dosing rule
            context: Patient context
            drug_key: Drug key

        Returns:
            DoseFlag if inappropriate, None otherwise
        """
        # Neonatal dosing is complex (gestational age, postnatal age)
        # For MVP, flag for clinical review if interval doesn't match expected range

        interval_rules = neonatal_rule.get("interval_by_pma_and_pna")
        if interval_rules and context.gestational_age_weeks:
            # Determine PMA tier
            pma = context.gestational_age_weeks
            if pma < 29:
                pma_tier = "lt_29_weeks_pma"
            elif pma <= 34:
                pma_tier = "30_34_weeks_pma"
            elif pma <= 36:
                pma_tier = "30_36_weeks_pma"
            else:
                pma_tier = "ge_35_weeks_pma"

            # For MVP, flag for review rather than precise interval check
            if pma_tier in interval_rules:
                expected_note = neonatal_rule.get("note", "Neonatal dosing by gestational/postnatal age")
                return DoseFlag(
                    flag_type=DoseFlagType.AGE_DOSE_MISMATCH,
                    severity=DoseAlertSeverity.MODERATE,
                    drug=med.drug_name,
                    message=f"{med.drug_name} in neonate: verify interval appropriate for gestational age",
                    expected=expected_note,
                    actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                    rule_source=AGE_BASED_RULES[drug_key].get("source", "Neonatal dosing guidelines"),
                    indication=context.indication or "Unknown",
                    details={
                        "age_years": context.age_years,
                        "gestational_age_weeks": context.gestational_age_weeks,
                        "note": expected_note,
                    },
                )

        return None

    def _parse_severity(self, severity: str) -> DoseAlertSeverity:
        """Parse severity string to enum."""
        severity_lower = severity.lower()
        if severity_lower == "critical":
            return DoseAlertSeverity.CRITICAL
        elif severity_lower == "high":
            return DoseAlertSeverity.HIGH
        else:
            return DoseAlertSeverity.MODERATE
