"""Weight-based dosing rules for antimicrobial dosing verification.

Flags when weight-based dosing is inappropriate:
- Obesity: Actual vs adjusted body weight considerations
- Pediatric: Weight-appropriate dosing calculations
- Max dose caps exceeded
"""

import logging
from typing import Any

from ..alert_models import DoseAlertSeverity, DoseFlagType, DoseFlag
from ..data_models import PatientContext, MedicationOrder
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


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
        "pediatric": {"dose_mg_kg": 15, "interval": "q24h"},
        "adult": {"dose_mg_kg": 15, "interval": "q24h"},
        "obesity": {"use_adjusted_weight": True, "dosing_weight_formula": "adjusted"},
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
        "pediatric": {"dose_mg_kg": 50, "interval": "q8h", "max_dose_mg": 2000},
        "adult": {"dose_mg": {"standard": 1000, "severe": 2000}, "interval": "q8h"},
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "piperacillin_tazobactam": {
        "pediatric": {"dose_mg_kg": 100, "interval": "q6h", "max_dose_mg": 4000},
        "adult": {"dose_mg": 4500, "interval": "q6h"},
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "acyclovir": {
        "pediatric": {
            "dose_mg_kg": {"mucocutaneous": 10, "encephalitis": 20},
            "interval": "q8h",
            "max_dose_mg": {"mucocutaneous": 800, "encephalitis": 1500},
        },
        "adult": {"dose_mg_kg": {"mucocutaneous": 5, "encephalitis": 10}, "interval": "q8h"},
        "obesity": {"use_adjusted_weight": True, "note": "Use ideal body weight for obese patients"},
        "severity": "high",
        "source": "IDSA Encephalitis Guidelines, Sanford Guide 2024",
    },
    "fluconazole": {
        "pediatric": {
            "dose_mg_kg": {"standard": 6, "candidemia_load": 12},
            "interval": "q24h",
            "max_daily_mg": 800,
        },
        "adult": {"dose_mg": {"standard": 400, "candidemia_load": 800}, "interval": "q24h"},
        "severity": "moderate",
        "source": "IDSA Candidiasis Guidelines 2016",
    },
}


def calculate_ibw_kg(height_cm: float, sex: str = "male") -> float:
    height_inches = height_cm / 2.54
    if height_inches <= 60:
        return 45.5 if sex.lower() == "female" else 50.0
    inches_over_5ft = height_inches - 60
    if sex.lower() == "female":
        return 45.5 + (2.3 * inches_over_5ft)
    else:
        return 50.0 + (2.3 * inches_over_5ft)


def calculate_adjusted_weight_kg(actual_kg: float, ideal_kg: float) -> float:
    if actual_kg <= ideal_kg:
        return actual_kg
    return ideal_kg + 0.4 * (actual_kg - ideal_kg)


def calculate_bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100
    return weight_kg / (height_m ** 2)


class WeightBasedRules(BaseRuleModule):
    """Check if antimicrobial dosing is appropriately weight-based."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        flags: list[DoseFlag] = []

        if context.weight_kg is None:
            return flags

        is_pediatric = context.age_years is not None and context.age_years < 18

        bmi = None
        is_obese = False
        if context.height_cm:
            bmi = calculate_bmi(context.weight_kg, context.height_cm)
            is_obese = bmi >= 30 if bmi else False

        for med in context.antimicrobials:
            drug_lower = med.drug_name.lower()

            drug_key = self._match_drug(drug_lower)
            if not drug_key:
                continue

            rule = WEIGHT_BASED_RULES[drug_key]

            if is_pediatric and "pediatric" in rule:
                flag = self._check_pediatric_weight(med, rule["pediatric"], context, drug_key)
                if flag:
                    flags.append(flag)
            elif "adult" in rule:
                flag = self._check_adult_weight(med, rule.get("adult"), context, drug_key, is_obese)
                if flag:
                    flags.append(flag)

            if is_obese and "obesity" in rule:
                flag = self._check_obesity_dosing(med, rule["obesity"], context, drug_key)
                if flag:
                    flags.append(flag)

        return flags

    def _match_drug(self, drug_name: str) -> str | None:
        if drug_name in WEIGHT_BASED_RULES:
            return drug_name

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

    def _check_pediatric_weight(self, med, peds_rule, context, drug_key):
        dose_mg_kg_day = peds_rule.get("dose_mg_kg_day")

        if dose_mg_kg_day:
            if isinstance(dose_mg_kg_day, dict):
                expected_mg_kg_day = dose_mg_kg_day.get("target") or dose_mg_kg_day.get("standard") or dose_mg_kg_day.get("min")
            else:
                expected_mg_kg_day = dose_mg_kg_day

            expected_daily_mg = expected_mg_kg_day * context.weight_kg
            max_daily_mg = peds_rule.get("max_daily_mg")

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

    def _check_adult_weight(self, med, adult_rule, context, drug_key, is_obese):
        if not adult_rule:
            return None

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
                details={"weight_kg": context.weight_kg, "max_daily_mg": max_daily_mg},
            )

        dose_mg_kg = adult_rule.get("dose_mg_kg")
        if dose_mg_kg and isinstance(dose_mg_kg, (int, float)):
            expected_dose = dose_mg_kg * context.weight_kg
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
                    details={"weight_kg": context.weight_kg, "expected_mg_kg": dose_mg_kg},
                )

        return None

    def _check_obesity_dosing(self, med, obesity_rule, context, drug_key):
        if not context.height_cm:
            return None

        use_adjusted = obesity_rule.get("use_adjusted_weight", False)

        if use_adjusted:
            ibw = calculate_ibw_kg(context.height_cm, sex="male")
            abw = calculate_adjusted_weight_kg(context.weight_kg, ibw)

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
