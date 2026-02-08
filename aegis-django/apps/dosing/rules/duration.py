"""Duration rules for antimicrobial dosing verification.

Flags when antimicrobial therapy duration is inappropriately short or long
based on clinical indication and guideline recommendations.
"""

import logging
from datetime import datetime, timedelta
from typing import Any

from ..alert_models import DoseAlertSeverity, DoseFlagType, DoseFlag
from ..data_models import PatientContext, MedicationOrder
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


DURATION_RULES = {
    "uti": {
        "uncomplicated_cystitis": {
            "min_days": 3, "max_days": 7, "typical_days": 5,
            "severity": "moderate",
            "note": "3-7 days for uncomplicated cystitis (women)",
            "source": "IDSA UTI Guidelines 2011",
        },
        "pyelonephritis": {
            "min_days": 7, "max_days": 14, "typical_days": 10,
            "severity": "moderate",
            "note": "7-14 days for pyelonephritis",
            "source": "IDSA UTI Guidelines 2011",
        },
    },
    "pneumonia": {
        "cap": {
            "min_days": 5, "max_days": 7, "typical_days": 5,
            "severity": "moderate",
            "note": "5 days for CAP if clinically stable and afebrile for 48-72h",
            "source": "IDSA/ATS CAP Guidelines 2019",
        },
        "hap_vap": {
            "min_days": 7, "max_days": 14, "typical_days": 7,
            "severity": "moderate",
            "note": "7 days for HAP/VAP (up to 14 days for non-fermenters, MRSA, or slow response)",
            "source": "ATS/IDSA HAP/VAP Guidelines 2016",
        },
    },
    "cellulitis": {
        "min_days": 5, "max_days": 14, "typical_days": 7,
        "severity": "moderate",
        "note": "5-7 days if improving, up to 14 days for severe or slow response",
        "source": "IDSA Skin/Soft Tissue Guidelines 2014",
    },
    "bacteremia": {
        "uncomplicated_gn": {
            "min_days": 7, "max_days": 14, "typical_days": 7,
            "severity": "moderate",
            "note": "7-14 days for uncomplicated Gram-negative bacteremia",
            "source": "IDSA Practice Guidelines",
        },
        "staph_aureus": {
            "min_days": 14, "max_days": 42, "typical_days": 14,
            "severity": "high",
            "note": "14 days minimum for uncomplicated MSSA/MRSA bacteremia, 4-6 weeks for complicated",
            "source": "IDSA MRSA Guidelines 2011",
        },
    },
    "endocarditis": {
        "native_valve": {
            "min_days": 28, "max_days": 42, "typical_days": 28,
            "severity": "high",
            "note": "4-6 weeks for native valve endocarditis",
            "source": "AHA Endocarditis Guidelines 2015",
        },
        "prosthetic_valve": {
            "min_days": 42, "max_days": 56, "typical_days": 42,
            "severity": "high",
            "note": "6-8 weeks for prosthetic valve endocarditis",
            "source": "AHA Endocarditis Guidelines 2015",
        },
    },
    "osteomyelitis": {
        "min_days": 28, "max_days": 42, "typical_days": 42,
        "severity": "moderate",
        "note": "4-6 weeks minimum for osteomyelitis",
        "source": "IDSA Osteomyelitis Guidelines",
    },
    "septic_arthritis": {
        "min_days": 14, "max_days": 28, "typical_days": 21,
        "severity": "moderate",
        "note": "2-4 weeks for septic arthritis",
        "source": "IDSA Joint Infection Guidelines",
    },
    "meningitis": {
        "bacterial": {
            "min_days": 7, "max_days": 21, "typical_days": 10,
            "severity": "high",
            "note": "7 days (N. meningitidis), 10-14 days (S. pneumoniae), 21 days (Gram-negatives, Listeria)",
            "source": "IDSA Meningitis Guidelines 2024",
        },
    },
    "intra_abdominal": {
        "source_controlled": {
            "min_days": 4, "max_days": 7, "typical_days": 4,
            "severity": "moderate",
            "note": "4 days if source controlled, 5-7 days typical",
            "source": "IDSA Intra-abdominal Infection Guidelines 2010",
        },
    },
    "c_difficile": {
        "non_severe": {
            "min_days": 10, "max_days": 14, "typical_days": 10,
            "severity": "moderate",
            "note": "10 days for non-severe CDI (14 days for severe)",
            "source": "IDSA/SHEA CDI Guidelines 2021",
        },
    },
    "candidemia": {
        "min_days": 14, "max_days": 28, "typical_days": 14,
        "severity": "moderate",
        "note": "14 days after first negative blood culture and resolution of symptoms",
        "source": "IDSA Candidiasis Guidelines 2016",
    },
    "surgical_prophylaxis": {
        "min_days": 0, "max_days": 1, "typical_days": 0,
        "severity": "moderate",
        "note": "Single dose pre-op, redose intraoperatively if surgery > 4h. Discontinue within 24h post-op (48h for cardiac)",
        "source": "ASHP/IDSA/SIS Surgical Prophylaxis Guidelines 2013",
    },
}


def days_on_therapy(med: MedicationOrder) -> int | None:
    if not med.start_date:
        return None
    try:
        start = datetime.fromisoformat(med.start_date.replace('Z', '+00:00'))
        now = datetime.now(start.tzinfo) if start.tzinfo else datetime.now()
        days = (now - start).days
        return max(0, days)
    except Exception as e:
        logger.warning(f"Failed to parse start_date {med.start_date}: {e}")
        return None


class DurationRules(BaseRuleModule):
    """Check if antimicrobial therapy duration is appropriate for indication."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        flags: list[DoseFlag] = []

        if not context.indication:
            return flags

        indication_lower = context.indication.lower().replace(" ", "_")

        if indication_lower in DURATION_RULES:
            rules = DURATION_RULES[indication_lower]
        else:
            matched_key = self._match_indication(indication_lower)
            if matched_key:
                rules = DURATION_RULES[matched_key]
            else:
                return flags

        for med in context.antimicrobials:
            days = days_on_therapy(med)
            if days is None:
                continue

            if isinstance(rules, dict) and self._has_nested_rules(rules):
                subrules = next(iter(rules.values()))
            else:
                subrules = rules

            if not isinstance(subrules, dict) or "min_days" not in subrules:
                continue

            min_days = subrules.get("min_days", 0)
            max_days = subrules.get("max_days", 999)
            typical_days = subrules.get("typical_days", min_days)
            severity = subrules.get("severity", "moderate")
            note = subrules.get("note", "")
            source = subrules.get("source", "Clinical guidelines")

            if days < min_days:
                flags.append(DoseFlag(
                    flag_type=DoseFlagType.DURATION_INSUFFICIENT,
                    severity=self._parse_severity(severity),
                    drug=med.drug_name,
                    message=f"{med.drug_name} for {context.indication}: duration too short ({days} days)",
                    expected=f"Minimum {min_days} days (typical: {typical_days} days)",
                    actual=f"{days} days on therapy",
                    rule_source=source,
                    indication=context.indication,
                    details={
                        "days_on_therapy": days,
                        "min_days": min_days,
                        "typical_days": typical_days,
                        "note": note,
                    },
                ))
            elif days > max_days + 3:
                flags.append(DoseFlag(
                    flag_type=DoseFlagType.DURATION_EXCESSIVE,
                    severity=DoseAlertSeverity.MODERATE,
                    drug=med.drug_name,
                    message=f"{med.drug_name} for {context.indication}: duration excessive ({days} days)",
                    expected=f"Maximum {max_days} days (typical: {typical_days} days)",
                    actual=f"{days} days on therapy",
                    rule_source=source,
                    indication=context.indication,
                    details={
                        "days_on_therapy": days,
                        "max_days": max_days,
                        "typical_days": typical_days,
                        "note": note,
                    },
                ))

        return flags

    def _match_indication(self, indication):
        matches = {
            "urinary_tract_infection": "uti",
            "community_acquired_pneumonia": "pneumonia",
            "hospital_acquired_pneumonia": "pneumonia",
            "ventilator_associated_pneumonia": "pneumonia",
            "skin_infection": "cellulitis",
            "soft_tissue_infection": "cellulitis",
            "blood_stream_infection": "bacteremia",
            "bloodstream_infection": "bacteremia",
            "sepsis": "bacteremia",
            "bone_infection": "osteomyelitis",
            "joint_infection": "septic_arthritis",
            "abdominal_infection": "intra_abdominal",
            "peritonitis": "intra_abdominal",
            "fungemia": "candidemia",
            "prophylaxis": "surgical_prophylaxis",
        }

        for pattern, key in matches.items():
            if pattern in indication:
                return key

        for key in DURATION_RULES.keys():
            if key in indication or indication in key:
                return key

        return None

    def _has_nested_rules(self, rules):
        first_val = next(iter(rules.values()), None)
        if isinstance(first_val, dict) and ("min_days" in first_val or "typical_days" in first_val):
            return True
        return False

    def _parse_severity(self, severity):
        severity_lower = severity.lower()
        if severity_lower == "critical":
            return DoseAlertSeverity.CRITICAL
        elif severity_lower == "high":
            return DoseAlertSeverity.HIGH
        else:
            return DoseAlertSeverity.MODERATE
