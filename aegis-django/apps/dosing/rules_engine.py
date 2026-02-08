"""Core rules engine for antimicrobial dosing verification.

Copied from dosing-verification/src/rules_engine.py with import path updates.
"""

import logging
import uuid
from datetime import datetime
from typing import Any

from .alert_models import DoseAlertSeverity, DoseAssessment, DoseFlag
from .data_models import PatientContext

logger = logging.getLogger(__name__)


class BaseRuleModule:
    """Base class for rule modules."""

    def evaluate(self, context: PatientContext) -> list[DoseFlag]:
        """Return list of dosing flags for this patient context."""
        raise NotImplementedError


class DosingRulesEngine:
    """Evaluates antimicrobial orders against clinical rules."""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.rules: list[BaseRuleModule] = []
        self._register_rules()

    def _register_rules(self) -> None:
        """Register all rule modules in priority order."""
        from .rules.allergy import AllergyRules
        from .rules.age import AgeBasedRules
        from .rules.interaction import DrugInteractionRules
        from .rules.route import RouteRules
        from .rules.indication import IndicationRules
        from .rules.renal import RenalAdjustmentRules
        from .rules.weight import WeightBasedRules
        from .rules.duration import DurationRules
        from .rules.extended_infusion import ExtendedInfusionRules

        # Register in priority order (most critical first)
        self.rules = [
            AllergyRules(),           # Check allergies first (critical safety)
            AgeBasedRules(),          # Age-based contraindications
            DrugInteractionRules(),   # Drug-drug interactions (critical safety)
            RouteRules(),             # Wrong route
            IndicationRules(),        # Indication-specific dosing
            RenalAdjustmentRules(),   # Renal dose adjustments
            WeightBasedRules(),       # Weight-appropriate dosing
            DurationRules(),          # Duration appropriateness
            ExtendedInfusionRules(),  # Extended infusion candidates
        ]

    def evaluate(self, context: PatientContext) -> DoseAssessment:
        """Run all rules against patient context, return assessment with flags."""
        assessment_id = self._generate_assessment_id()
        flags: list[DoseFlag] = []

        for rule_module in self.rules:
            try:
                module_flags = rule_module.evaluate(context)
                flags.extend(module_flags)
            except Exception as e:
                logger.error(
                    f"Error in {rule_module.__class__.__name__}: {e}", exc_info=True
                )

        flags = self._deduplicate_flags(flags)
        max_severity = self._get_max_severity(flags)

        assessment = DoseAssessment(
            assessment_id=assessment_id,
            patient_id=context.patient_id,
            patient_mrn=context.patient_mrn,
            patient_name=context.patient_name,
            encounter_id=context.encounter_id,
            age_years=context.age_years,
            weight_kg=context.weight_kg,
            height_cm=context.height_cm,
            scr=context.scr,
            gfr=context.gfr,
            is_on_dialysis=context.is_on_dialysis,
            gestational_age_weeks=context.gestational_age_weeks,
            medications_evaluated=[
                {
                    "drug": med.drug_name,
                    "dose": f"{med.dose_value} {med.dose_unit}",
                    "interval": med.interval,
                    "route": med.route,
                    "order_id": med.order_id,
                    "start_date": med.start_date,
                }
                for med in context.antimicrobials
            ],
            indication=context.indication,
            indication_confidence=context.indication_confidence,
            indication_source=context.indication_source,
            flags=flags,
            max_severity=max_severity,
            assessed_at=datetime.now().isoformat(),
            assessed_by="dosing_engine_v1",
            co_medications=[
                {
                    "drug": med.drug_name,
                    "dose": f"{med.dose_value} {med.dose_unit}",
                }
                for med in context.co_medications
            ],
        )

        return assessment

    def _generate_assessment_id(self) -> str:
        return f"DOSE-{uuid.uuid4().hex[:12].upper()}"

    def _deduplicate_flags(self, flags: list[DoseFlag]) -> list[DoseFlag]:
        """Remove duplicate flags (same drug + flag_type), keep highest severity."""
        seen: dict[tuple[str, str], DoseFlag] = {}

        for flag in flags:
            key = (flag.drug, flag.flag_type.value)
            if key not in seen:
                seen[key] = flag
            else:
                existing = seen[key]
                if self._severity_rank(flag.severity) > self._severity_rank(existing.severity):
                    seen[key] = flag

        result = list(seen.values())
        result.sort(key=lambda f: self._severity_rank(f.severity), reverse=True)
        return result

    def _severity_rank(self, severity: DoseAlertSeverity) -> int:
        ranks = {
            DoseAlertSeverity.CRITICAL: 4,
            DoseAlertSeverity.HIGH: 3,
            DoseAlertSeverity.MODERATE: 2,
            DoseAlertSeverity.LOW: 1,
        }
        return ranks.get(severity, 0)

    def _get_max_severity(self, flags: list[DoseFlag]) -> DoseAlertSeverity | None:
        if not flags:
            return None
        max_rank = 0
        max_severity = None
        for flag in flags:
            rank = self._severity_rank(flag.severity)
            if rank > max_rank:
                max_rank = rank
                max_severity = flag.severity
        return max_severity
