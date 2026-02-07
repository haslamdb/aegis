"""Indication-based dosing rules for antimicrobials.

Defines expected dosing for drug-indication pairs based on clinical guidelines.
"""

import logging
from typing import Any
from common.dosing_verification import DoseAlertSeverity, DoseFlag, DoseFlagType
from ..models import PatientContext
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


# Indication-based dosing rules organized by syndrome
INDICATION_DOSE_RULES = {
    # === CNS Infections ===
    "meningitis": {
        "ceftriaxone": {
            "pediatric": {"dose_mg_kg_day": 100, "interval": "q12h", "max_daily_mg": 4000},
            "adult": {"dose_mg": 2000, "interval": "q12h"},
            "severity": DoseAlertSeverity.CRITICAL,
            "source": "IDSA Meningitis Guidelines 2024",
        },
        "meropenem": {
            "pediatric": {"dose_mg_kg_day": 120, "interval": "q8h", "max_daily_mg": 6000},
            "adult": {"dose_mg": 2000, "interval": "q8h"},
            "severity": DoseAlertSeverity.CRITICAL,
            "source": "IDSA Meningitis Guidelines",
        },
        "ampicillin": {
            "pediatric": {"dose_mg_kg_day": 300, "interval": "q6h", "max_daily_mg": 12000},
            "adult": {"dose_mg": 2000, "interval": "q4h"},
            "severity": DoseAlertSeverity.CRITICAL,
            "source": "IDSA Meningitis Guidelines",
        },
        "vancomycin": {
            "pediatric": {"dose_mg_kg_day": 60, "interval": "q6h", "trough_target": "15-20"},
            "adult": {"auc_mic_target": "400-600", "trough_target": "15-20"},
            "severity": DoseAlertSeverity.CRITICAL,
            "source": "IDSA/ASHP Vancomycin Guidelines 2020",
        },
    },
    "encephalitis": {
        "acyclovir": {
            "pediatric": {"dose_mg_kg": 20, "interval": "q8h"},
            "adult": {"dose_mg_kg": 10, "interval": "q8h"},
            "severity": DoseAlertSeverity.CRITICAL,
            "source": "IDSA Encephalitis Guidelines 2023",
            "note": "HSV encephalitis requires 10 mg/kg q8h (30 mg/kg/day), NOT standard 5 mg/kg dosing",
        },
    },
    # === Endocarditis ===
    "endocarditis": {
        "gentamicin": {
            "pediatric": {"dose_mg_kg": 1, "interval": "q8h"},
            "adult": {"dose_mg_kg": 1, "interval": "q8h"},
            "severity": DoseAlertSeverity.CRITICAL,
            "source": "AHA Endocarditis Guidelines 2015",
            "note": "Synergy dosing (NOT extended-interval). 1 mg/kg q8h, not 5-7 mg/kg q24h",
            "flag_if_extended_interval": True,
        },
        "ampicillin": {
            "pediatric": {"dose_mg_kg_day": 300, "interval": "q4-6h"},
            "adult": {"dose_mg": 2000, "interval": "q4h", "daily_max_mg": 12000},
            "severity": DoseAlertSeverity.HIGH,
            "source": "AHA Endocarditis Guidelines",
        },
        "daptomycin": {
            "adult": {"dose_mg_kg": 8, "interval": "q24h", "range_mg_kg": [8, 10]},
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA MRSA Guidelines (endocarditis dose: 8-10 mg/kg, NOT 4-6)",
        },
    },
    # === C. difficile ===
    "c_difficile": {
        "vancomycin": {
            "pediatric": {"dose_mg_kg": 10, "interval": "q6h", "route": "PO", "max_dose_mg": 125},
            "adult": {"dose_mg": 125, "interval": "q6h", "route": "PO"},
            "adult_severe": {"dose_mg": 500, "interval": "q6h", "route": "PO"},
            "severity": DoseAlertSeverity.CRITICAL,
            "source": "IDSA/SHEA CDI Guidelines 2021",
            "note": "MUST be PO or rectal. IV vancomycin does NOT reach colon.",
            "route_critical": True,
        },
        "fidaxomicin": {
            "adult": {"dose_mg": 200, "interval": "q12h", "route": "PO", "duration_days": 10},
            "severity": DoseAlertSeverity.MODERATE,
            "source": "IDSA/SHEA CDI Guidelines 2021",
        },
        "metronidazole": {
            "note": "No longer first-line per IDSA 2021. Flag if used alone.",
            "severity": DoseAlertSeverity.MODERATE,
            "source": "IDSA/SHEA CDI Guidelines 2021",
        },
    },
    # === Invasive Fungal Infections ===
    "invasive_candidiasis": {
        "fluconazole": {
            "adult": {
                "loading_dose_mg": 800,
                "maintenance_dose_mg": 400,
                "interval": "q24h",
                "requires_loading": True,
            },
            "pediatric": {
                "loading_dose_mg_kg": 12,
                "maintenance_dose_mg_kg": 6,
                "interval": "q24h",
                "requires_loading": True,
            },
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Candidiasis Guidelines 2016",
            "note": "Loading dose 800 mg (12 mg/kg) on day 1, then 400 mg (6 mg/kg) daily",
        },
        "caspofungin": {
            "adult": {"loading_dose_mg": 70, "maintenance_dose_mg": 50, "interval": "q24h"},
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Candidiasis Guidelines 2016",
        },
        "micafungin": {
            "adult": {"dose_mg": 100, "interval": "q24h"},
            "pediatric": {"dose_mg_kg": 2, "interval": "q24h"},
            "severity": DoseAlertSeverity.MODERATE,
            "source": "IDSA Candidiasis Guidelines 2016",
        },
    },
    "invasive_aspergillosis": {
        "voriconazole": {
            "adult": {
                "loading_dose_mg_kg": 6,
                "maintenance_dose_mg_kg": 4,
                "interval_loading": "q12h",
                "interval_maintenance": "q12h",
                "requires_tdm": True,
                "target_trough_mcg_ml": [1.0, 5.5],
            },
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Aspergillosis Guidelines 2016",
            "note": "Loading: 6 mg/kg q12h x 2 doses. Maintenance: 4 mg/kg q12h. Requires TDM (target trough 1-5.5 mcg/mL)",
        },
        "isavuconazole": {
            "adult": {
                "loading_dose_mg": 372,
                "interval_loading": "q8h",
                "loading_doses": 6,
                "maintenance_dose_mg": 372,
                "interval_maintenance": "q24h",
            },
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Aspergillosis Guidelines 2016",
        },
        "amphotericin_b_lipid": {
            "adult": {"dose_mg_kg": 5, "interval": "q24h"},
            "pediatric": {"dose_mg_kg": 5, "interval": "q24h"},
            "severity": DoseAlertSeverity.MODERATE,
            "source": "IDSA Aspergillosis Guidelines",
            "note": "Liposomal amphotericin B 5 mg/kg/day (NOT conventional 1 mg/kg)",
        },
    },
    # === Osteomyelitis ===
    "osteomyelitis": {
        "nafcillin": {
            "pediatric": {"dose_mg_kg_day": 200, "interval": "q6h", "max_daily_mg": 12000},
            "adult": {"dose_mg": 2000, "interval": "q4h"},
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Osteomyelitis Guidelines",
            "note": "Prolonged high-dose therapy for bone penetration",
        },
        "cefazolin": {
            "adult": {"dose_mg": 2000, "interval": "q8h"},
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Osteomyelitis Guidelines",
        },
        "daptomycin": {
            "adult": {"dose_mg_kg": 8, "interval": "q24h"},
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Osteomyelitis Guidelines",
            "note": "Higher dose 8-10 mg/kg for bone infection",
        },
    },
    # === Pneumonia ===
    "pneumonia": {
        "piperacillin_tazobactam": {
            "adult": {
                "dose_mg": 4500,
                "interval": "q6h",
                "extended_infusion_hours": 4,
                "recommend_extended": True,
            },
            "severity": DoseAlertSeverity.MODERATE,
            "source": "Time-dependent beta-lactam PK/PD",
            "note": "Consider extended infusion over 4 hours for severe pneumonia",
        },
        "meropenem": {
            "adult": {
                "dose_mg": 2000,
                "interval": "q8h",
                "extended_infusion_hours": 3,
                "recommend_extended": True,
            },
            "severity": DoseAlertSeverity.MODERATE,
            "source": "IDSA HAP/VAP Guidelines",
            "note": "Extended infusion over 3 hours optimizes time > MIC",
        },
    },
    # === Necrotizing Fasciitis ===
    "necrotizing_fasciitis": {
        "clindamycin": {
            "adult": {"dose_mg": 900, "interval": "q8h"},
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Skin/Soft Tissue Guidelines",
            "note": "High-dose clindamycin for toxin suppression in GAS necrotizing fasciitis",
        },
        "penicillin": {
            "adult": {"dose_mg": 4000000, "dose_unit": "units", "interval": "q4h"},
            "severity": DoseAlertSeverity.HIGH,
            "source": "IDSA Skin/Soft Tissue Guidelines",
            "note": "High-dose penicillin G for GAS necrotizing fasciitis",
        },
    },
}


class IndicationRules(BaseRuleModule):
    """Check indication-specific dosing requirements."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Evaluate dosing against indication-specific rules.

        Args:
            context: Patient clinical context

        Returns:
            List of DoseFlag objects for dosing mismatches
        """
        flags = []

        # Need an indication to check
        if not context.indication:
            return flags

        indication_lower = context.indication.lower()

        # Find matching indication in rules
        matching_rules = None
        for indication_key in INDICATION_DOSE_RULES:
            if indication_key in indication_lower:
                matching_rules = INDICATION_DOSE_RULES[indication_key]
                break

        if not matching_rules:
            # No specific rules for this indication
            return flags

        # Check each antimicrobial
        for med in context.antimicrobials:
            drug_lower = med.drug_name.lower()

            # Find matching drug rule
            drug_rule = None
            for drug_key in matching_rules:
                if drug_key in drug_lower:
                    drug_rule = matching_rules[drug_key]
                    break

            if not drug_rule:
                # No specific rule for this drug
                continue

            # Determine if pediatric or adult
            is_pediatric = context.age_years is not None and context.age_years < 18

            # Get expected dosing
            if is_pediatric and "pediatric" in drug_rule:
                expected_dosing = drug_rule["pediatric"]
                age_group = "pediatric"
            elif not is_pediatric and "adult" in drug_rule:
                expected_dosing = drug_rule["adult"]
                age_group = "adult"
            else:
                # No specific rule for this age group
                continue

            # Check if we have enough data to evaluate
            if not context.weight_kg and "dose_mg_kg_day" in expected_dosing:
                # Can't check weight-based dosing without weight
                continue

            # Check dosing
            flag = self._check_dosing(
                med=med,
                expected=expected_dosing,
                drug_rule=drug_rule,
                context=context,
                age_group=age_group,
            )

            if flag:
                flags.append(flag)

        return flags

    def _check_dosing(
        self,
        med: Any,
        expected: dict,
        drug_rule: dict,
        context: PatientContext,
        age_group: str,
    ) -> DoseFlag | None:
        """Check if medication dosing matches expected.

        Args:
            med: MedicationOrder
            expected: Expected dosing dict
            drug_rule: Full drug rule dict
            context: Patient context
            age_group: "pediatric" or "adult"

        Returns:
            DoseFlag if mismatch found, else None
        """
        # Check weight-based dosing (pediatric)
        if "dose_mg_kg_day" in expected and context.weight_kg:
            expected_daily_dose = expected["dose_mg_kg_day"] * context.weight_kg

            # Check against max if specified
            if "max_daily_mg" in expected:
                expected_daily_dose = min(expected_daily_dose, expected["max_daily_mg"])

            # Compare to actual daily dose
            actual_daily_dose = med.daily_dose

            # Allow 10% tolerance
            tolerance = 0.10
            lower_bound = expected_daily_dose * (1 - tolerance)
            upper_bound = expected_daily_dose * (1 + tolerance)

            if actual_daily_dose < lower_bound:
                return DoseFlag(
                    flag_type=DoseFlagType.SUBTHERAPEUTIC_DOSE,
                    severity=drug_rule.get("severity", DoseAlertSeverity.HIGH),
                    drug=med.drug_name,
                    message=f"Subtherapeutic dose for {context.indication}. BBB penetration requires higher dosing.",
                    expected=f"{expected['dose_mg_kg_day']} mg/kg/day divided {expected['interval']} (={expected_daily_dose:.0f} mg/day for {context.weight_kg} kg patient)",
                    actual=f"{med.daily_dose:.0f} mg/day ({med.dose_value} {med.dose_unit} {med.interval})",
                    rule_source=drug_rule["source"],
                    indication=context.indication,
                    details={
                        "expected_mg_kg_day": expected["dose_mg_kg_day"],
                        "actual_mg_kg_day": actual_daily_dose / context.weight_kg,
                        "patient_weight_kg": context.weight_kg,
                    },
                )

            elif actual_daily_dose > upper_bound:
                return DoseFlag(
                    flag_type=DoseFlagType.SUPRATHERAPEUTIC_DOSE,
                    severity=DoseAlertSeverity.HIGH,
                    drug=med.drug_name,
                    message=f"Dose exceeds recommended maximum for {context.indication}.",
                    expected=f"{expected['dose_mg_kg_day']} mg/kg/day (max {expected.get('max_daily_mg', 'N/A')} mg/day)",
                    actual=f"{med.daily_dose:.0f} mg/day ({med.dose_value} {med.dose_unit} {med.interval})",
                    rule_source=drug_rule["source"],
                    indication=context.indication,
                    details={
                        "expected_mg_kg_day": expected["dose_mg_kg_day"],
                        "actual_mg_kg_day": actual_daily_dose / context.weight_kg,
                    },
                )

        # Check fixed adult dosing
        elif "dose_mg" in expected:
            expected_dose = expected["dose_mg"]
            actual_dose = med.dose_value

            # Convert to same units if needed
            if med.dose_unit == "g":
                actual_dose = actual_dose * 1000

            tolerance = 0.10
            lower_bound = expected_dose * (1 - tolerance)
            upper_bound = expected_dose * (1 + tolerance)

            if actual_dose < lower_bound:
                return DoseFlag(
                    flag_type=DoseFlagType.SUBTHERAPEUTIC_DOSE,
                    severity=drug_rule.get("severity", DoseAlertSeverity.HIGH),
                    drug=med.drug_name,
                    message=f"Subtherapeutic dose for {context.indication}.",
                    expected=f"{expected_dose} mg {expected['interval']}",
                    actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                    rule_source=drug_rule["source"],
                    indication=context.indication,
                )

            elif actual_dose > upper_bound:
                return DoseFlag(
                    flag_type=DoseFlagType.SUPRATHERAPEUTIC_DOSE,
                    severity=DoseAlertSeverity.MODERATE,
                    drug=med.drug_name,
                    message=f"Dose exceeds recommended for {context.indication}.",
                    expected=f"{expected_dose} mg {expected['interval']}",
                    actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                    rule_source=drug_rule["source"],
                    indication=context.indication,
                )

        # Check interval
        expected_interval = expected.get("interval", "")
        if expected_interval and med.interval != expected_interval:
            # Handle interval ranges like "q4-6h"
            if "-" in expected_interval:
                # Parse range
                parts = expected_interval.replace("q", "").replace("h", "").split("-")
                if len(parts) == 2:
                    min_hours = int(parts[0])
                    max_hours = int(parts[1])
                    if not (min_hours <= med.frequency_hours <= max_hours):
                        return DoseFlag(
                            flag_type=DoseFlagType.WRONG_INTERVAL,
                            severity=DoseAlertSeverity.MODERATE,
                            drug=med.drug_name,
                            message=f"Dosing interval outside recommended range for {context.indication}.",
                            expected=expected_interval,
                            actual=med.interval,
                            rule_source=drug_rule["source"],
                            indication=context.indication,
                        )

        return None
