"""Weight-based dosing rules for antimicrobial dosing verification.

Flags when weight-based dosing is inappropriate:
- Obesity: Actual vs adjusted body weight considerations
- Pediatric: Weight-appropriate dosing calculations
- Max dose caps exceeded
"""

import logging
from typing import Any

from common.dosing_verification import DoseAlertSeverity, DoseFlagType, DoseFlag
from ..models import PatientContext, MedicationOrder
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


# Weight-based dosing rules
# Structure: {
#   "pediatric": {
#       "dose_mg_kg": X,
#       "dose_mg_kg_day": Y,
#       "max_dose_mg": Z,
#   },
#   "adult": {
#       "dose_mg_kg": X,
#       "max_dose_mg": Z,
#   },
#   "obesity": {
#       "use_adjusted_weight": True/False,
#       "dosing_weight_formula": "adjusted" or "actual" or "ideal",
#   },
# }

WEIGHT_BASED_RULES = {
    "vancomycin": {
        "pediatric": {
            "dose_mg_kg_day": {"min": 40, "max": 60, "target": 45},
            "interval_options": ["q6h", "q8h", "q12h"],
            "max_daily_mg": 4000,
        },
        "adult": {
            "use_auc_dosing": True,
            "target_auc_mic": "400-600",
            "note": "AUC-based dosing preferred. Loading dose 20-35 mg/kg.",
        },
        "obesity": {
            "use_adjusted_weight": True,
            "note": "Use actual body weight for loading dose, adjusted for maintenance if BMI > 30",
        },
        "severity": "moderate",
        "source": "IDSA/ASHP Vancomycin Guidelines 2020",
    },
    "gentamicin": {
        "pediatric": {
            "dose_mg_kg": {"extended_interval": 7, "traditional": 2.5},
            "interval_options": ["q24h", "q8h"],
        },
        "adult": {
            "dose_mg_kg": 7,
            "interval": "q24h",
        },
        "obesity": {
            "use_adjusted_weight": True,
            "dosing_weight_formula": "adjusted",
            "note": "For BMI > 30: Adjusted body weight = IBW + 0.4(TBW - IBW)",
        },
        "severity": "high",
        "source": "Hartford Extended-Interval Nomogram, Sanford Guide 2024",
    },
    "tobramycin": {
        "pediatric": {
            "dose_mg_kg": {"extended_interval": 7, "traditional": 2.5},
            "interval_options": ["q24h", "q8h"],
        },
        "adult": {
            "dose_mg_kg": 7,
            "interval": "q24h",
        },
        "obesity": {
            "use_adjusted_weight": True,
            "dosing_weight_formula": "adjusted",
            "note": "For BMI > 30: Adjusted body weight = IBW + 0.4(TBW - IBW)",
        },
        "severity": "high",
        "source": "Sanford Guide 2024",
    },
    "amikacin": {
        "pediatric": {
            "dose_mg_kg": 15,
            "interval": "q24h",
        },
        "adult": {
            "dose_mg_kg": 15,
            "interval": "q24h",
        },
        "obesity": {
            "use_adjusted_weight": True,
            "dosing_weight_formula": "adjusted",
        },
        "severity": "high",
        "source": "Sanford Guide 2024",
    },
    "daptomycin": {
        "pediatric": {
            "dose_mg_kg": {"age_1_6_years": 10, "age_7_17_years": 7},
            "max_daily_mg": 600,
        },
        "adult": {
            "dose_mg_kg": {"skin_sti": 4, "bacteremia": 6, "endocarditis": 8},
            "max_daily_mg": 800,
        },
        "obesity": {
            "use_adjusted_weight": False,
            "note": "Use actual body weight. No dose cap for endocarditis.",
        },
        "severity": "moderate",
        "source": "Daptomycin prescribing information, IDSA MRSA Guidelines",
    },
    "ceftriaxone": {
        "pediatric": {
            "dose_mg_kg_day": {"standard": 50, "meningitis": 100},
            "max_daily_mg": 4000,
            "interval_options": ["q24h", "q12h"],
        },
        "adult": {
            "dose_mg": {"standard": 1000, "meningitis": 2000},
            "interval": {"standard": "q24h", "meningitis": "q12h"},
            "max_daily_mg": 4000,
        },
        "obesity": {
            "use_adjusted_weight": False,
            "note": "Use actual weight for pediatrics. Fixed adult dosing.",
        },
        "severity": "moderate",
        "source": "IDSA Meningitis Guidelines, Sanford Guide 2024",
    },
    "meropenem": {
        "pediatric": {
            "dose_mg_kg": {"standard": 20, "meningitis": 40},
            "interval": "q8h",
            "max_dose_mg": 2000,
        },
        "adult": {
            "dose_mg": {"standard": 1000, "meningitis": 2000},
            "interval": "q8h",
        },
        "obesity": {
            "use_adjusted_weight": False,
            "note": "Use actual weight for pediatrics. Fixed adult dosing.",
        },
        "severity": "moderate",
        "source": "IDSA Meningitis Guidelines, Sanford Guide 2024",
    },
    "cefepime": {
        "pediatric": {
            "dose_mg_kg": 50,
            "interval": "q8h",
            "max_dose_mg": 2000,
        },
        "adult": {
            "dose_mg": {"standard": 1000, "severe": 2000},
            "interval": "q8h",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "piperacillin_tazobactam": {
        "pediatric": {
            "dose_mg_kg": 100,  # Piperacillin component
            "interval": "q6h",
            "max_dose_mg": 4000,
        },
        "adult": {
            "dose_mg": 4500,  # Piperacillin 4000 + tazobactam 500
            "interval": "q6h",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "acyclovir": {
        "pediatric": {
            "dose_mg_kg": {"mucocutaneous": 10, "encephalitis": 20},
            "interval": "q8h",
            "max_dose_mg": {"mucocutaneous": 800, "encephalitis": 1500},
        },
        "adult": {
            "dose_mg_kg": {"mucocutaneous": 5, "encephalitis": 10},
            "interval": "q8h",
        },
        "obesity": {
            "use_adjusted_weight": True,
            "note": "Use ideal body weight for obese patients",
        },
        "severity": "high",
        "source": "IDSA Encephalitis Guidelines, Sanford Guide 2024",
    },
    "fluconazole": {
        "pediatric": {
            "dose_mg_kg": {"standard": 6, "candidemia_load": 12},
            "interval": "q24h",
            "max_daily_mg": 800,
        },
        "adult": {
            "dose_mg": {"standard": 400, "candidemia_load": 800},
            "interval": "q24h",
        },
        "severity": "moderate",
        "source": "IDSA Candidiasis Guidelines 2016",
    },
}


def calculate_ibw_kg(height_cm: float, sex: str = "male") -> float:
    """Calculate ideal body weight in kg.

    Uses Devine formula:
    - Male: 50 kg + 2.3 kg per inch over 5 feet
    - Female: 45.5 kg + 2.3 kg per inch over 5 feet

    Args:
        height_cm: Height in centimeters
        sex: "male" or "female" (defaults to male)

    Returns:
        Ideal body weight in kg
    """
    height_inches = height_cm / 2.54
    if height_inches <= 60:
        # For very short patients, use fixed minimum
        return 45.5 if sex.lower() == "female" else 50.0

    inches_over_5ft = height_inches - 60
    if sex.lower() == "female":
        return 45.5 + (2.3 * inches_over_5ft)
    else:
        return 50.0 + (2.3 * inches_over_5ft)


def calculate_adjusted_weight_kg(actual_kg: float, ideal_kg: float) -> float:
    """Calculate adjusted body weight for obesity dosing.

    Formula: IBW + 0.4 * (TBW - IBW)

    Args:
        actual_kg: Actual body weight in kg
        ideal_kg: Ideal body weight in kg

    Returns:
        Adjusted body weight in kg
    """
    if actual_kg <= ideal_kg:
        return actual_kg
    return ideal_kg + 0.4 * (actual_kg - ideal_kg)


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    """Calculate BMI.

    Args:
        weight_kg: Weight in kg
        height_cm: Height in cm

    Returns:
        BMI (kg/m^2)
    """
    height_m = height_cm / 100
    return weight_kg / (height_m ** 2)


class WeightBasedRules(BaseRuleModule):
    """Check if antimicrobial dosing is appropriately weight-based."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Evaluate weight-based dosing for all antimicrobials.

        Args:
            context: Patient clinical context

        Returns:
            List of DoseFlag objects for weight-based issues
        """
        flags: list[DoseFlag] = []

        # If no weight data, skip
        if context.weight_kg is None:
            logger.debug(f"No weight data for {context.patient_mrn}, skipping weight rules")
            return flags

        # Determine if pediatric or adult (< 18 years = pediatric)
        is_pediatric = context.age_years is not None and context.age_years < 18

        # Calculate BMI and obesity status if height available
        bmi = None
        is_obese = False
        if context.height_cm:
            bmi = calculate_bmi(context.weight_kg, context.height_cm)
            is_obese = bmi >= 30 if bmi else False

        # Check each antimicrobial
        for med in context.antimicrobials:
            drug_lower = med.drug_name.lower()

            # Find matching drug in weight rules
            drug_key = self._match_drug(drug_lower)
            if not drug_key:
                continue

            rule = WEIGHT_BASED_RULES[drug_key]

            # Select pediatric or adult rule
            if is_pediatric and "pediatric" in rule:
                flag = self._check_pediatric_weight(med, rule["pediatric"], context, drug_key)
                if flag:
                    flags.append(flag)
            elif "adult" in rule:
                flag = self._check_adult_weight(med, rule.get("adult"), context, drug_key, is_obese)
                if flag:
                    flags.append(flag)

            # Check obesity-specific rules
            if is_obese and "obesity" in rule:
                flag = self._check_obesity_dosing(med, rule["obesity"], context, drug_key)
                if flag:
                    flags.append(flag)

        return flags

    def _match_drug(self, drug_name: str) -> str | None:
        """Match drug name to weight rules key."""
        # Direct match
        if drug_name in WEIGHT_BASED_RULES:
            return drug_name

        # Fuzzy matches
        matches = {
            "vanc": "vancomycin",
            "gent": "gentamicin",
            "tobra": "tobramycin",
            "dapto": "daptomycin",
            "ceftriax": "ceftriaxone",
            "mero": "meropenem",
            "pip": "piperacillin_tazobactam",
            "zosyn": "piperacillin_tazobactam",
            "acyclo": "acyclovir",
            "flucon": "fluconazole",
        }

        for pattern, key in matches.items():
            if pattern in drug_name:
                return key

        return None

    def _check_pediatric_weight(
        self,
        med: MedicationOrder,
        peds_rule: dict,
        context: PatientContext,
        drug_key: str,
    ) -> DoseFlag | None:
        """Check pediatric weight-based dosing.

        Args:
            med: Medication order
            peds_rule: Pediatric dosing rule
            context: Patient context
            drug_key: Drug key

        Returns:
            DoseFlag if inappropriate, None otherwise
        """
        # Calculate expected dose per kg if we have weight
        dose_mg_kg_day = peds_rule.get("dose_mg_kg_day")
        dose_mg_kg = peds_rule.get("dose_mg_kg")

        if dose_mg_kg_day:
            # Total daily dose calculation
            if isinstance(dose_mg_kg_day, dict):
                # Context-dependent (e.g., standard vs meningitis)
                # For MVP, use standard or min
                expected_mg_kg_day = dose_mg_kg_day.get("target") or dose_mg_kg_day.get("standard") or dose_mg_kg_day.get("min")
            else:
                expected_mg_kg_day = dose_mg_kg_day

            expected_daily_mg = expected_mg_kg_day * context.weight_kg
            max_daily_mg = peds_rule.get("max_daily_mg")

            # Check if exceeds max dose cap
            if max_daily_mg and med.daily_dose > max_daily_mg:
                return DoseFlag(
                    flag_type=DoseFlagType.MAX_DOSE_EXCEEDED,
                    severity=DoseAlertSeverity.HIGH,
                    drug=med.drug_name,
                    message=f"{med.drug_name} exceeds maximum daily dose for pediatrics",
                    expected=f"Maximum {max_daily_mg} mg/day",
                    actual=f"{med.daily_dose:.0f} mg/day",
                    rule_source=WEIGHT_BASED_RULES[drug_key].get("source", "Pediatric dosing guidelines"),
                    indication=context.indication or "Unknown",
                    details={
                        "weight_kg": context.weight_kg,
                        "age_years": context.age_years,
                        "max_daily_mg": max_daily_mg,
                    },
                )

            # Check if daily dose is significantly different from expected
            # Allow 20% variance
            if med.daily_dose < expected_daily_mg * 0.8:
                return DoseFlag(
                    flag_type=DoseFlagType.WEIGHT_DOSE_MISMATCH,
                    severity=DoseAlertSeverity.MODERATE,
                    drug=med.drug_name,
                    message=f"{med.drug_name} dose may be low for patient weight",
                    expected=f"{expected_mg_kg_day:.0f} mg/kg/day ({expected_daily_mg:.0f} mg/day for {context.weight_kg} kg)",
                    actual=f"{med.daily_dose:.0f} mg/day ({med.daily_dose/context.weight_kg:.1f} mg/kg/day)",
                    rule_source=WEIGHT_BASED_RULES[drug_key].get("source", "Pediatric dosing guidelines"),
                    indication=context.indication or "Unknown",
                    details={
                        "weight_kg": context.weight_kg,
                        "age_years": context.age_years,
                        "expected_mg_kg_day": expected_mg_kg_day,
                    },
                )

        return None

    def _check_adult_weight(
        self,
        med: MedicationOrder,
        adult_rule: dict | None,
        context: PatientContext,
        drug_key: str,
        is_obese: bool,
    ) -> DoseFlag | None:
        """Check adult weight-based dosing.

        Args:
            med: Medication order
            adult_rule: Adult dosing rule
            context: Patient context
            drug_key: Drug key
            is_obese: Whether patient is obese

        Returns:
            DoseFlag if inappropriate, None otherwise
        """
        if not adult_rule:
            return None

        # Check max dose
        max_daily_mg = adult_rule.get("max_daily_mg")
        if max_daily_mg and med.daily_dose > max_daily_mg:
            return DoseFlag(
                flag_type=DoseFlagType.MAX_DOSE_EXCEEDED,
                severity=DoseAlertSeverity.MODERATE,
                drug=med.drug_name,
                message=f"{med.drug_name} exceeds maximum daily dose",
                expected=f"Maximum {max_daily_mg} mg/day",
                actual=f"{med.daily_dose:.0f} mg/day",
                rule_source=WEIGHT_BASED_RULES[drug_key].get("source", "Adult dosing guidelines"),
                indication=context.indication or "Unknown",
                details={
                    "weight_kg": context.weight_kg,
                    "max_daily_mg": max_daily_mg,
                },
            )

        # Check weight-based adult dosing (e.g., aminoglycosides, daptomycin)
        dose_mg_kg = adult_rule.get("dose_mg_kg")
        if dose_mg_kg and isinstance(dose_mg_kg, (int, float)):
            expected_dose = dose_mg_kg * context.weight_kg
            # Allow 20% variance
            if med.dose_value < expected_dose * 0.8 or med.dose_value > expected_dose * 1.2:
                return DoseFlag(
                    flag_type=DoseFlagType.WEIGHT_DOSE_MISMATCH,
                    severity=DoseAlertSeverity.MODERATE,
                    drug=med.drug_name,
                    message=f"{med.drug_name} dose may not be weight-appropriate",
                    expected=f"{dose_mg_kg} mg/kg ({expected_dose:.0f} mg for {context.weight_kg} kg)",
                    actual=f"{med.dose_value:.0f} mg ({med.dose_value/context.weight_kg:.1f} mg/kg)",
                    rule_source=WEIGHT_BASED_RULES[drug_key].get("source", "Weight-based dosing guidelines"),
                    indication=context.indication or "Unknown",
                    details={
                        "weight_kg": context.weight_kg,
                        "expected_mg_kg": dose_mg_kg,
                    },
                )

        return None

    def _check_obesity_dosing(
        self,
        med: MedicationOrder,
        obesity_rule: dict,
        context: PatientContext,
        drug_key: str,
    ) -> DoseFlag | None:
        """Check if obesity dosing considerations are appropriate.

        Args:
            med: Medication order
            obesity_rule: Obesity-specific rule
            context: Patient context
            drug_key: Drug key

        Returns:
            DoseFlag if issue detected, None otherwise
        """
        if not context.height_cm:
            # Can't calculate IBW/ABW without height
            return None

        use_adjusted = obesity_rule.get("use_adjusted_weight", False)

        if use_adjusted:
            # Calculate ideal and adjusted body weight
            ibw = calculate_ibw_kg(context.height_cm, sex="male")  # TODO: Get sex from FHIR
            abw = calculate_adjusted_weight_kg(context.weight_kg, ibw)

            # Flag for review - obesity dosing is complex
            return DoseFlag(
                flag_type=DoseFlagType.WEIGHT_DOSE_MISMATCH,
                severity=DoseAlertSeverity.MODERATE,
                drug=med.drug_name,
                message=f"{med.drug_name} dosing in obesity: verify weight used for calculation",
                expected=f"Use adjusted body weight ({abw:.1f} kg) - {obesity_rule.get('note', '')}",
                actual=f"{med.dose_value:.0f} mg ({med.dose_value/context.weight_kg:.1f} mg/kg actual weight)",
                rule_source=WEIGHT_BASED_RULES[drug_key].get("source", "Obesity dosing guidelines"),
                indication=context.indication or "Unknown",
                details={
                    "actual_weight_kg": context.weight_kg,
                    "ideal_weight_kg": ibw,
                    "adjusted_weight_kg": abw,
                    "bmi": calculate_bmi(context.weight_kg, context.height_cm),
                    "note": obesity_rule.get("note", ""),
                },
            )

        return None
