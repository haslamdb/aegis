"""Route verification rules for antimicrobials.

Checks for critical route mismatches like IV vancomycin for C. diff infection.
"""

import logging
from common.dosing_verification import DoseAlertSeverity, DoseFlag, DoseFlagType
from ..models import PatientContext
from ..rules_engine import BaseRuleModule

logger = logging.getLogger(__name__)


# Route rules: drug + indication → required route
ROUTE_RULES = [
    {
        "drug": "vancomycin",
        "indication": "c_difficile",
        "required_route": "PO",
        "forbidden_routes": ["IV", "IM"],
        "severity": DoseAlertSeverity.CRITICAL,
        "message": "IV vancomycin does NOT reach the colon. C. difficile requires PO or rectal vancomycin.",
        "expected": "Vancomycin 125 mg PO q6h (or 500 mg PO q6h for severe CDI)",
        "source": "IDSA/SHEA CDI Guidelines 2021",
    },
    {
        "drug": "nitrofurantoin",
        "contraindicated_indications": ["bacteremia", "pyelonephritis", "sepsis"],
        "severity": DoseAlertSeverity.CRITICAL,
        "message": "Nitrofurantoin achieves therapeutic levels only in urine. Not appropriate for systemic infections.",
        "expected": "Alternative systemic antibiotic (ceftriaxone, ciprofloxacin, etc.)",
        "source": "IDSA UTI Guidelines",
    },
    {
        "drug": "daptomycin",
        "contraindicated_indications": ["pneumonia"],
        "severity": DoseAlertSeverity.CRITICAL,
        "message": "Daptomycin is inactivated by pulmonary surfactant. Not effective for pneumonia.",
        "expected": "Alternative agent (vancomycin, linezolid, ceftaroline)",
        "source": "Daptomycin prescribing information",
    },
    {
        "drug": "tigecycline",
        "contraindicated_indications": ["bacteremia"],
        "severity": DoseAlertSeverity.HIGH,
        "message": "Tigecycline has poor serum levels. Not appropriate as sole agent for bacteremia.",
        "expected": "Alternative or combination therapy",
        "source": "FDA warning 2010, IDSA guidance",
    },
]


class RouteRules(BaseRuleModule):
    """Verify that drug routes are appropriate for the indication."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Check route appropriateness for each medication.

        Args:
            context: Patient clinical context

        Returns:
            List of DoseFlag objects for route mismatches
        """
        flags = []

        # Need an indication to check route rules
        if not context.indication:
            return flags

        indication_lower = context.indication.lower()

        for med in context.antimicrobials:
            drug_lower = med.drug_name.lower()
            route_upper = med.route.upper()

            for rule in ROUTE_RULES:
                # Check if rule applies to this drug
                if rule["drug"] not in drug_lower:
                    continue

                # Check for contraindicated indication
                if "contraindicated_indications" in rule:
                    contraindicated = rule["contraindicated_indications"]
                    if any(ci in indication_lower for ci in contraindicated):
                        flags.append(
                            DoseFlag(
                                flag_type=DoseFlagType.WRONG_ROUTE,
                                severity=rule["severity"],
                                drug=med.drug_name,
                                message=rule["message"],
                                expected=rule["expected"],
                                actual=f"{med.drug_name} {med.dose_value} {med.dose_unit} {route_upper} {med.interval}",
                                rule_source=rule["source"],
                                indication=context.indication,
                                details={
                                    "route": route_upper,
                                    "contraindicated_for": ", ".join(contraindicated),
                                },
                            )
                        )

                # Check for required route (e.g., vanc for CDI must be PO)
                if "indication" in rule and rule["indication"] in indication_lower:
                    required_route = rule.get("required_route", "").upper()
                    forbidden_routes = [r.upper() for r in rule.get("forbidden_routes", [])]

                    # Check if current route is forbidden
                    if route_upper in forbidden_routes or (
                        required_route and route_upper != required_route
                    ):
                        flags.append(
                            DoseFlag(
                                flag_type=DoseFlagType.WRONG_ROUTE,
                                severity=rule["severity"],
                                drug=med.drug_name,
                                message=rule["message"],
                                expected=rule["expected"],
                                actual=f"{med.drug_name} {med.dose_value} {med.dose_unit} {route_upper} {med.interval}",
                                rule_source=rule["source"],
                                indication=context.indication,
                                details={
                                    "current_route": route_upper,
                                    "required_route": required_route,
                                    "forbidden_routes": forbidden_routes,
                                },
                            )
                        )

        return flags
