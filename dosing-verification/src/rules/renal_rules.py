"""Renal adjustment rules for antimicrobial dosing verification.

Flags when antimicrobials are not properly dose-adjusted for renal impairment.
Based on GFR/CrCl thresholds and dialysis status.
"""

import logging
from typing import Any

from common.dosing_verification import DoseAlertSeverity, DoseFlagType, DoseFlag
from ..models import PatientContext, MedicationOrder
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


# Renal adjustment tables by drug
# Structure: {
#   "normal": {dose, interval},  # GFR > 60
#   "gfr_30_60": {dose, interval, dose_reduction},
#   "gfr_10_30": {dose, interval, dose_reduction},
#   "gfr_lt_10": {dose, interval, dose_reduction},
#   "hd": {dose, interval, note},  # Hemodialysis
#   "crrt": {dose, interval, note},  # CRRT
# }

RENAL_ADJUSTMENTS = {
    "vancomycin": {
        "method": "auc_based",
        "note": "AUC-based dosing, renal adjustment inherent. Flag if no levels ordered.",
        "flag_if_no_level": True,
        "severity": "high",
        "hd": {
            "dose_mg_kg": 25,
            "frequency": "per_level",
            "note": "Dose after HD session, check levels",
        },
        "crrt": {
            "note": "Continuous infusion preferred on CRRT. Standard dosing with close level monitoring.",
        },
        "source": "IDSA/ASHP Vancomycin Guidelines 2020",
    },
    "meropenem": {
        "normal": {"dose_mg_kg": 20, "interval_h": 8},
        "gfr_26_50": {"dose_mg_kg": 20, "interval_h": 12},
        "gfr_10_25": {"dose_mg_kg": 10, "interval_h": 12},
        "gfr_lt_10": {"dose_mg_kg": 10, "interval_h": 24},
        "crrt": {
            "dose_mg_kg": 20,
            "interval_h": 8,
            "note": "Full dose on CRRT",
        },
        "hd": {
            "dose_mg_kg": 10,
            "interval_h": 24,
            "note": "Dose after HD session",
        },
        "severity": "high",
        "source": "Sanford Guide 2024",
    },
    "cefepime": {
        "normal": {"dose_mg": 2000, "interval_h": 8},
        "gfr_30_60": {"dose_mg": 2000, "interval_h": 12},
        "gfr_11_29": {"dose_mg": 1000, "interval_h": 12},
        "gfr_lt_11": {"dose_mg": 1000, "interval_h": 24},
        "hd": {
            "dose_mg": 1000,
            "interval_h": 24,
            "note": "Dose after HD. Risk of neurotoxicity if not adjusted.",
        },
        "note": "Neurotoxicity risk (encephalopathy, seizures) if not adjusted for renal function",
        "severity": "critical",
        "source": "FDA prescribing information, Neurology 2012;79:2233",
    },
    "ceftriaxone": {
        "note": "No renal adjustment needed (biliary excretion)",
        "requires_adjustment": False,
    },
    "ceftazidime": {
        "normal": {"dose_mg": 2000, "interval_h": 8},
        "gfr_31_50": {"dose_mg": 1000, "interval_h": 12},
        "gfr_16_30": {"dose_mg": 1000, "interval_h": 24},
        "gfr_6_15": {"dose_mg": 500, "interval_h": 24},
        "gfr_lt_6": {"dose_mg": 500, "interval_h": 48},
        "hd": {
            "dose_mg": 1000,
            "frequency": "after_each_hd",
            "note": "1g after each HD session",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "acyclovir": {
        "normal": {"interval_h": 8},
        "gfr_25_50": {"interval_h": 12},
        "gfr_10_25": {"interval_h": 24},
        "gfr_lt_10": {"dose_reduction": 0.5, "interval_h": 24},
        "hd": {
            "interval_h": 24,
            "frequency": "after_hd",
            "note": "Dose after HD. Risk of nephrotoxicity and neurotoxicity.",
        },
        "note": "Nephrotoxicity risk with high doses or inadequate hydration",
        "severity": "high",
        "source": "Sanford Guide 2024",
    },
    "fluconazole": {
        "gfr_lt_50": {
            "dose_reduction": 0.5,
            "note": "50% dose reduction for CrCl < 50 (after loading dose)",
        },
        "hd": {
            "dose_reduction": 0.5,
            "frequency": "after_hd",
            "note": "50% dose after each HD",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "piperacillin_tazobactam": {
        "normal": {"dose_mg": 4500, "interval_h": 6},
        "gfr_20_40": {"dose_mg": 3375, "interval_h": 6},
        "gfr_lt_20": {"dose_mg": 2250, "interval_h": 6},
        "hd": {
            "dose_mg": 2250,
            "interval_h": 6,
            "note": "Extra 750 mg dose after each HD",
        },
        "crrt": {
            "dose_mg": 4500,
            "interval_h": 6,
            "note": "Full dose on CRRT with extended infusion",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "ciprofloxacin": {
        "normal": {"dose_mg": 400, "interval_h": 12},
        "gfr_lt_30": {
            "dose_reduction": 0.5,
            "interval_h": 12,
            "note": "50% dose reduction for CrCl < 30",
        },
        "hd": {
            "dose_mg": 400,
            "interval_h": 24,
            "note": "Dose after HD",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "levofloxacin": {
        "normal": {"dose_mg": 750, "interval_h": 24},
        "gfr_20_49": {
            "dose_mg": 750,
            "then": {"dose_mg": 500, "interval_h": 24},
            "note": "Initial dose 750 mg, then 500 mg q24h",
        },
        "gfr_10_19": {
            "dose_mg": 750,
            "then": {"dose_mg": 500, "interval_h": 48},
            "note": "Initial dose 750 mg, then 500 mg q48h",
        },
        "gfr_lt_10": {
            "dose_mg": 750,
            "then": {"dose_mg": 250, "interval_h": 48},
            "note": "Initial dose 750 mg, then 250 mg q48h",
        },
        "hd": {
            "dose_mg": 750,
            "then": {"dose_mg": 500, "interval_h": 48},
            "note": "Initial 750 mg, then 500 mg q48h. No supplemental dose after HD.",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "gentamicin": {
        "method": "level_based",
        "note": "Extended-interval dosing with level-based adjustment required",
        "flag_if_no_level": True,
        "extended_interval_cutoffs": {
            "gfr_gt_60": {"dose_mg_kg": 7, "interval_h": 24},
            "gfr_40_60": {"dose_mg_kg": 7, "interval_h": 36},
            "gfr_20_40": {"dose_mg_kg": 7, "interval_h": 48},
            "gfr_lt_20": {
                "note": "Traditional dosing (1-2 mg/kg q8-12h) with close level monitoring"
            },
        },
        "hd": {
            "dose_mg_kg": 1.5,
            "frequency": "after_hd",
            "note": "1.5 mg/kg after each HD, check levels",
        },
        "crrt": {
            "dose_mg_kg": 2.5,
            "interval_h": 24,
            "note": "Loading dose 2.5 mg/kg, then adjust based on levels",
        },
        "severity": "high",
        "source": "IDSA Aminoglycoside Guidelines, Sanford Guide 2024",
    },
    "tobramycin": {
        "method": "level_based",
        "note": "Extended-interval dosing with level-based adjustment required",
        "flag_if_no_level": True,
        "extended_interval_cutoffs": {
            "gfr_gt_60": {"dose_mg_kg": 7, "interval_h": 24},
            "gfr_40_60": {"dose_mg_kg": 7, "interval_h": 36},
            "gfr_20_40": {"dose_mg_kg": 7, "interval_h": 48},
            "gfr_lt_20": {
                "note": "Traditional dosing (1-2 mg/kg q8-12h) with close level monitoring"
            },
        },
        "hd": {
            "dose_mg_kg": 1.5,
            "frequency": "after_hd",
            "note": "1.5 mg/kg after each HD, check levels",
        },
        "severity": "high",
        "source": "IDSA Aminoglycoside Guidelines, Sanford Guide 2024",
    },
    "amikacin": {
        "method": "level_based",
        "note": "Extended-interval dosing with level-based adjustment required",
        "flag_if_no_level": True,
        "extended_interval_cutoffs": {
            "gfr_gt_60": {"dose_mg_kg": 15, "interval_h": 24},
            "gfr_40_60": {"dose_mg_kg": 15, "interval_h": 36},
            "gfr_20_40": {"dose_mg_kg": 15, "interval_h": 48},
        },
        "hd": {
            "dose_mg_kg": 5,
            "frequency": "after_hd",
            "note": "5 mg/kg after each HD, check levels",
        },
        "severity": "high",
        "source": "Sanford Guide 2024",
    },
    "trimethoprim_sulfamethoxazole": {
        "normal": {"dose_tmp_mg_kg": 5, "interval_h": 6},
        "gfr_15_30": {
            "dose_reduction": 0.5,
            "note": "50% dose reduction",
        },
        "gfr_lt_15": {
            "contraindicated": True,
            "note": "Avoid use. Risk of hyperkalemia and bone marrow suppression.",
        },
        "severity": "high",
        "source": "Sanford Guide 2024",
    },
    "cefazolin": {
        "normal": {"dose_mg": 2000, "interval_h": 8},
        "gfr_35_54": {"dose_mg": 2000, "interval_h": 12},
        "gfr_11_34": {"dose_mg": 1000, "interval_h": 12},
        "gfr_lt_11": {"dose_mg": 500, "interval_h": 12},
        "hd": {
            "dose_mg": 1000,
            "frequency": "after_hd",
            "note": "1g after each HD",
        },
        "severity": "moderate",
        "source": "Sanford Guide 2024",
    },
    "nafcillin": {
        "note": "No renal adjustment needed (hepatic metabolism)",
        "requires_adjustment": False,
    },
    "oxacillin": {
        "note": "No renal adjustment needed (hepatic metabolism)",
        "requires_adjustment": False,
    },
}


class RenalAdjustmentRules(BaseRuleModule):
    """Check if antimicrobial dosing is appropriately adjusted for renal function."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Evaluate renal dosing for all antimicrobials.

        Args:
            context: Patient clinical context

        Returns:
            List of DoseFlag objects for renal issues
        """
        flags: list[DoseFlag] = []

        # If no renal function data, skip (can't evaluate)
        if context.gfr is None and context.crcl is None and context.scr is None:
            logger.debug(f"No renal function data for {context.patient_mrn}, skipping renal rules")
            return flags

        # Use GFR if available, otherwise estimate from CrCl
        gfr = context.gfr if context.gfr is not None else context.crcl

        if gfr is None:
            logger.debug(f"Unable to determine GFR/CrCl for {context.patient_mrn}")
            return flags

        # Check each antimicrobial
        for med in context.antimicrobials:
            drug_lower = med.drug_name.lower()

            # Find matching drug in adjustment table
            drug_key = self._match_drug(drug_lower)
            if not drug_key:
                continue

            adjustment = RENAL_ADJUSTMENTS[drug_key]

            # Check if this drug requires adjustment
            if adjustment.get("requires_adjustment") is False:
                continue

            # Check for level-based dosing (aminoglycosides, vancomycin)
            if adjustment.get("method") == "level_based" or adjustment.get("method") == "auc_based":
                if adjustment.get("flag_if_no_level"):
                    # TODO: Check if drug levels are ordered - placeholder for now
                    # For MVP, we'll assume levels are being checked
                    pass

            # Dialysis-specific dosing
            if context.is_on_dialysis:
                dialysis_rule = adjustment.get(context.dialysis_type.lower() if context.dialysis_type else "hd")
                if dialysis_rule:
                    flag = self._check_dialysis_dosing(med, dialysis_rule, context, drug_key)
                    if flag:
                        flags.append(flag)
                continue

            # Standard GFR-based adjustment
            flag = self._check_gfr_adjustment(med, adjustment, gfr, context, drug_key)
            if flag:
                flags.append(flag)

        return flags

    def _match_drug(self, drug_name: str) -> str | None:
        """Match drug name to adjustment table key.

        Args:
            drug_name: Drug name from order (lowercase)

        Returns:
            Matching key in RENAL_ADJUSTMENTS or None
        """
        # Direct match
        if drug_name in RENAL_ADJUSTMENTS:
            return drug_name

        # Fuzzy matches for common variations
        matches = {
            "vanc": "vancomycin",
            "mero": "meropenem",
            "pip": "piperacillin_tazobactam",
            "tazo": "piperacillin_tazobactam",
            "zosyn": "piperacillin_tazobactam",
            "cipro": "ciprofloxacin",
            "levo": "levofloxacin",
            "gent": "gentamicin",
            "tobra": "tobramycin",
            "bactrim": "trimethoprim_sulfamethoxazole",
            "tmp": "trimethoprim_sulfamethoxazole",
            "smx": "trimethoprim_sulfamethoxazole",
            "acyclo": "acyclovir",
            "flucon": "fluconazole",
        }

        for pattern, key in matches.items():
            if pattern in drug_name:
                return key

        return None

    def _check_gfr_adjustment(
        self,
        med: MedicationOrder,
        adjustment: dict,
        gfr: float,
        context: PatientContext,
        drug_key: str,
    ) -> DoseFlag | None:
        """Check if dose is appropriately adjusted for GFR.

        Args:
            med: Medication order
            adjustment: Adjustment rules for this drug
            gfr: Patient's GFR/CrCl
            context: Patient context
            drug_key: Drug key in adjustment table

        Returns:
            DoseFlag if inappropriate, None if appropriate
        """
        # Determine which GFR tier - try most specific match first
        tier = None

        if gfr >= 60:
            tier = self._find_tier(adjustment, ["normal"])
        elif gfr >= 50:
            tier = self._find_tier(adjustment, ["gfr_50_80", "gfr_50_60", "normal"])
        elif gfr >= 40:
            tier = self._find_tier(adjustment, ["gfr_40_60", "gfr_26_50", "gfr_31_50"])
        elif gfr >= 30:
            tier = self._find_tier(adjustment, ["gfr_30_60", "gfr_26_50", "gfr_30_54", "gfr_31_50", "gfr_35_54"])
        elif gfr >= 20:
            tier = self._find_tier(adjustment, ["gfr_20_49", "gfr_20_40", "gfr_26_50", "gfr_10_30", "gfr_10_29", "gfr_16_30"])
        elif gfr >= 10:
            tier = self._find_tier(adjustment, ["gfr_10_30", "gfr_10_29", "gfr_10_25", "gfr_11_34", "gfr_10_19", "gfr_15_30"])
        else:
            tier = self._find_tier(adjustment, ["gfr_lt_10", "gfr_lt_11", "gfr_6_15", "gfr_lt_6"])

        if not tier or tier not in adjustment:
            # No specific adjustment needed or no rule for this tier
            return None

        expected = adjustment[tier]
        severity = adjustment.get("severity", "moderate")

        # Check if contraindicated at this GFR
        if expected.get("contraindicated"):
            return DoseFlag(
                flag_type=DoseFlagType.NO_RENAL_ADJUSTMENT,
                severity=DoseAlertSeverity.CRITICAL,
                drug=med.drug_name,
                message=f"{med.drug_name} is contraindicated at GFR {gfr:.1f}",
                expected=expected.get("note", "Contraindicated"),
                actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                rule_source=adjustment.get("source", "Renal dosing guidelines"),
                indication=context.indication or "Unknown",
                details={
                    "gfr": gfr,
                    "tier": tier,
                    "note": expected.get("note", ""),
                },
            )

        # Compare interval
        expected_interval = expected.get("interval_h")
        if expected_interval and med.frequency_hours < expected_interval:
            # Interval is too frequent (not adjusted)
            return DoseFlag(
                flag_type=DoseFlagType.NO_RENAL_ADJUSTMENT,
                severity=self._parse_severity(severity),
                drug=med.drug_name,
                message=f"{med.drug_name} interval not adjusted for GFR {gfr:.1f}",
                expected=f"{expected.get('dose_mg', expected.get('dose_mg_kg', 'dose'))} mg q{expected_interval}h",
                actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                rule_source=adjustment.get("source", "Renal dosing guidelines"),
                indication=context.indication or "Unknown",
                details={
                    "gfr": gfr,
                    "expected_interval_h": expected_interval,
                    "actual_interval_h": med.frequency_hours,
                    "note": adjustment.get("note", ""),
                },
            )

        # Check dose reduction
        dose_reduction = expected.get("dose_reduction")
        if dose_reduction and dose_reduction < 1.0:
            # Expected dose should be reduced
            # This is a simplified check - full implementation would compare actual vs expected dose
            logger.debug(
                f"{med.drug_name}: GFR {gfr} requires {dose_reduction*100}% dose. "
                f"Actual: {med.dose_value} {med.dose_unit}"
            )
            # For now, flag as needing review
            return DoseFlag(
                flag_type=DoseFlagType.NO_RENAL_ADJUSTMENT,
                severity=self._parse_severity(severity),
                drug=med.drug_name,
                message=f"{med.drug_name} may need dose reduction for GFR {gfr:.1f}",
                expected=f"{int(dose_reduction * 100)}% dose reduction ({expected.get('note', '')})",
                actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
                rule_source=adjustment.get("source", "Renal dosing guidelines"),
                indication=context.indication or "Unknown",
                details={
                    "gfr": gfr,
                    "expected_dose_reduction": dose_reduction,
                    "note": expected.get("note", ""),
                },
            )

        return None

    def _check_dialysis_dosing(
        self,
        med: MedicationOrder,
        dialysis_rule: dict,
        context: PatientContext,
        drug_key: str,
    ) -> DoseFlag | None:
        """Check if dose is appropriate for dialysis patient.

        Args:
            med: Medication order
            dialysis_rule: Dialysis-specific rule
            context: Patient context
            drug_key: Drug key

        Returns:
            DoseFlag if inappropriate, None if appropriate
        """
        # For MVP, just flag that dialysis dosing should be reviewed
        adjustment = RENAL_ADJUSTMENTS[drug_key]
        severity = adjustment.get("severity", "high")

        return DoseFlag(
            flag_type=DoseFlagType.NO_RENAL_ADJUSTMENT,
            severity=self._parse_severity(severity),
            drug=med.drug_name,
            message=f"{med.drug_name} dosing in {context.dialysis_type or 'dialysis'} patient should be reviewed",
            expected=dialysis_rule.get("note", "Dialysis-specific dosing required"),
            actual=f"{med.dose_value} {med.dose_unit} {med.interval}",
            rule_source=adjustment.get("source", "Renal dosing guidelines"),
            indication=context.indication or "Unknown",
            details={
                "dialysis_type": context.dialysis_type,
                "dialysis_note": dialysis_rule.get("note", ""),
            },
        )

    def _find_tier(self, adjustment: dict, possible_keys: list[str]) -> str | None:
        """Find first matching tier key in adjustment dict.

        Args:
            adjustment: Adjustment rules dict
            possible_keys: List of possible tier keys to check

        Returns:
            First matching key or None
        """
        for key in possible_keys:
            if key in adjustment:
                return key
        return None

    def _parse_severity(self, severity: str) -> DoseAlertSeverity:
        """Parse severity string to enum.

        Args:
            severity: Severity string (critical, high, moderate)

        Returns:
            DoseAlertSeverity enum value
        """
        severity_lower = severity.lower()
        if severity_lower == "critical":
            return DoseAlertSeverity.CRITICAL
        elif severity_lower == "high":
            return DoseAlertSeverity.HIGH
        else:
            return DoseAlertSeverity.MODERATE
