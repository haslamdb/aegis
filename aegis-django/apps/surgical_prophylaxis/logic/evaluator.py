"""
Surgical prophylaxis compliance evaluator.

Evaluates surgical cases against ASHP guidelines for 7 bundle elements:
1. Indication appropriateness
2. Agent selection
3. Timing (within 60/120 min of incision)
4. Weight-based dosing
5. Intraoperative redosing
6. Post-operative continuation
7. Timely discontinuation
"""

from datetime import timedelta
from typing import Optional

from django.utils import timezone

from apps.surgical_prophylaxis.models import (
    ComplianceStatus,
    ProcedureCategory,
    ProphylaxisEvaluation,
    ProphylaxisMedication,
    SurgicalCase,
)

from .config import Config
from .guidelines import GuidelinesConfig, get_guidelines_config


def _element_result(element_name, status, details, recommendation=None, data=None):
    """Create element result dict matching ProphylaxisEvaluation JSON fields."""
    result = {
        'element_name': element_name,
        'status': status,
        'details': details,
    }
    if recommendation:
        result['recommendation'] = recommendation
    if data:
        result['data'] = data
    return result


class ProphylaxisEvaluator:
    """Evaluates surgical cases for prophylaxis compliance."""

    def __init__(self, config: Optional[GuidelinesConfig] = None):
        self.config = config or get_guidelines_config()

    def evaluate_case(self, case: SurgicalCase) -> dict:
        """
        Evaluate a surgical case for prophylaxis compliance.

        Args:
            case: SurgicalCase model instance with related medications

        Returns:
            dict suitable for creating a ProphylaxisEvaluation
        """
        medications = list(case.medications.all())
        orders = [m for m in medications if m.medication_type == 'order']
        admins = [m for m in medications if m.medication_type == 'administration']

        # Check exclusions
        exclusion = self._check_exclusions(case)
        if exclusion:
            return self._create_excluded_result(case, exclusion)

        # Evaluate each element
        indication = self._evaluate_indication(case, orders, admins)
        agent = self._evaluate_agent_selection(case, admins)
        timing = self._evaluate_timing(case, admins)
        dosing = self._evaluate_dosing(case, admins)
        redosing = self._evaluate_redosing(case, admins)
        postop = self._evaluate_postop_continuation(case, admins)
        discontinuation = self._evaluate_discontinuation(case, admins)

        # Calculate summary
        elements = [indication, agent, timing, dosing, redosing, postop, discontinuation]
        applicable = [
            e for e in elements
            if e['status'] not in (ComplianceStatus.NOT_APPLICABLE, ComplianceStatus.UNABLE_TO_ASSESS, ComplianceStatus.PENDING)
        ]
        met = [e for e in applicable if e['status'] == ComplianceStatus.MET]

        elements_met = len(met)
        elements_total = len(applicable)
        compliance_score = (elements_met / elements_total * 100) if elements_total > 0 else 0
        bundle_compliant = elements_met == elements_total and elements_total > 0

        recommendations = []
        flags = []
        for elem in elements:
            if elem['status'] == ComplianceStatus.NOT_MET:
                if elem.get('recommendation'):
                    recommendations.append(elem['recommendation'])
                flags.append(f"{elem['element_name']}: {elem['status']}")

        return {
            'indication_result': indication,
            'agent_result': agent,
            'timing_result': timing,
            'dosing_result': dosing,
            'redosing_result': redosing,
            'postop_result': postop,
            'discontinuation_result': discontinuation,
            'bundle_compliant': bundle_compliant,
            'compliance_score': compliance_score,
            'elements_met': elements_met,
            'elements_total': elements_total,
            'flags': flags,
            'recommendations': recommendations,
            'excluded': False,
            'exclusion_reason': '',
        }

    def _check_exclusions(self, case: SurgicalCase) -> Optional[str]:
        if case.is_emergency:
            return "Emergency surgery - timing may not be achievable"
        if case.already_on_therapeutic_abx:
            return "Patient already on therapeutic antibiotics"
        if case.documented_infection:
            return "Documented infection - prophylaxis not applicable"
        return None

    def _create_excluded_result(self, case: SurgicalCase, reason: str) -> dict:
        na = lambda name: _element_result(name, ComplianceStatus.NOT_APPLICABLE, reason)
        return {
            'indication_result': na('Indication'),
            'agent_result': na('Agent Selection'),
            'timing_result': na('Pre-op Timing'),
            'dosing_result': na('Dosing'),
            'redosing_result': na('Redosing'),
            'postop_result': na('Post-op Continuation'),
            'discontinuation_result': na('Discontinuation'),
            'bundle_compliant': True,
            'compliance_score': 100.0,
            'elements_met': 0,
            'elements_total': 0,
            'flags': [],
            'recommendations': [],
            'excluded': True,
            'exclusion_reason': reason,
        }

    def _get_requirements(self, case: SurgicalCase):
        for cpt in (case.cpt_codes or []):
            req = self.config.get_procedure_requirements(cpt)
            if req:
                return req
        return None

    def _evaluate_indication(self, case, orders, admins) -> dict:
        requirements = self._get_requirements(case)
        if requirements is None:
            return _element_result(
                'Indication', ComplianceStatus.UNABLE_TO_ASSESS,
                f"CPT codes not in guidelines: {case.cpt_codes}",
                recommendation="Review procedure requirements manually",
            )

        prophylaxis_given = len(admins) > 0 or len(orders) > 0
        prophylaxis_indicated = requirements.prophylaxis_indicated

        if prophylaxis_indicated and prophylaxis_given:
            return _element_result(
                'Indication', ComplianceStatus.MET,
                f"Prophylaxis given for {requirements.procedure_name} (indicated)",
            )
        elif not prophylaxis_indicated and not prophylaxis_given:
            return _element_result(
                'Indication', ComplianceStatus.MET,
                f"Prophylaxis appropriately withheld for {requirements.procedure_name}",
            )
        elif prophylaxis_indicated and not prophylaxis_given:
            return _element_result(
                'Indication', ComplianceStatus.NOT_MET,
                f"No prophylaxis given for {requirements.procedure_name} (prophylaxis indicated)",
                recommendation=f"Prophylaxis recommended: {requirements.first_line_agents}",
            )
        else:
            return _element_result(
                'Indication', ComplianceStatus.NOT_MET,
                f"Prophylaxis given for {requirements.procedure_name} (not indicated per guidelines)",
                recommendation="Consider discontinuing - prophylaxis not routinely indicated for this procedure",
            )

    def _evaluate_agent_selection(self, case, admins) -> dict:
        if not admins:
            requirements = self._get_requirements(case)
            if requirements and not requirements.prophylaxis_indicated:
                return _element_result('Agent Selection', ComplianceStatus.NOT_APPLICABLE, "Prophylaxis not indicated for this procedure")
            return _element_result('Agent Selection', ComplianceStatus.NOT_MET, "No prophylaxis administered", recommendation="Administer recommended prophylaxis")

        requirements = self._get_requirements(case)
        if requirements is None:
            return _element_result('Agent Selection', ComplianceStatus.UNABLE_TO_ASSESS, f"CPT codes not in guidelines: {case.cpt_codes}")

        if case.has_beta_lactam_allergy:
            acceptable_agents = requirements.alternative_agents
        else:
            acceptable_agents = requirements.first_line_agents
            if requirements.mrsa_high_risk_add and case.mrsa_colonized:
                acceptable_agents = acceptable_agents + [requirements.mrsa_high_risk_add]

        agents_given = [a.medication_name.lower() for a in admins]
        acceptable_lower = [a.lower() for a in acceptable_agents]
        matched = any(agent in acceptable_lower for agent in agents_given)

        if matched:
            return _element_result(
                'Agent Selection', ComplianceStatus.MET,
                f"Appropriate agent(s) given: {', '.join(agents_given)}",
                data={'agents_given': agents_given, 'acceptable': acceptable_agents},
            )
        else:
            return _element_result(
                'Agent Selection', ComplianceStatus.NOT_MET,
                f"Agent mismatch: given {', '.join(agents_given)}, expected {', '.join(acceptable_agents)}",
                recommendation=f"Recommended agents: {', '.join(acceptable_agents)}",
                data={'agents_given': agents_given, 'acceptable': acceptable_agents},
            )

    def _evaluate_timing(self, case, admins) -> dict:
        if not admins:
            requirements = self._get_requirements(case)
            if requirements and not requirements.prophylaxis_indicated:
                return _element_result('Pre-op Timing', ComplianceStatus.NOT_APPLICABLE, "Prophylaxis not indicated")
            return _element_result('Pre-op Timing', ComplianceStatus.NOT_MET, "No prophylaxis administered")

        if not case.actual_incision_time:
            return _element_result('Pre-op Timing', ComplianceStatus.PENDING, "Surgery not yet started - incision time not recorded")

        pre_incision = [a for a in admins if a.event_time < case.actual_incision_time]
        if not pre_incision:
            return _element_result(
                'Pre-op Timing', ComplianceStatus.NOT_MET,
                "No pre-operative prophylaxis given before incision",
                recommendation="Administer prophylaxis within 60 min before incision",
            )

        timing_results = []
        all_met = True
        for admin in pre_incision:
            delta = case.actual_incision_time - admin.event_time
            minutes_before = delta.total_seconds() / 60
            med_lower = admin.medication_name.lower()
            max_window = 120 if any(ext in med_lower for ext in Config.EXTENDED_WINDOW_ANTIBIOTICS) else 60

            if 0 < minutes_before <= max_window:
                timing_results.append(f"{admin.medication_name}: {minutes_before:.0f} min before incision (compliant)")
            else:
                timing_results.append(f"{admin.medication_name}: {minutes_before:.0f} min before incision (outside {max_window} min window)")
                all_met = False

        status = ComplianceStatus.MET if all_met else ComplianceStatus.NOT_MET
        return _element_result(
            'Pre-op Timing', status, '; '.join(timing_results),
            recommendation=None if all_met else "Antibiotics should be given within 60 min (120 min for vancomycin) before incision",
        )

    def _evaluate_dosing(self, case, admins) -> dict:
        if not admins:
            requirements = self._get_requirements(case)
            if requirements and not requirements.prophylaxis_indicated:
                return _element_result('Dosing', ComplianceStatus.NOT_APPLICABLE, "Prophylaxis not indicated")
            return _element_result('Dosing', ComplianceStatus.NOT_MET, "No prophylaxis administered")

        if not case.patient_weight_kg:
            return _element_result(
                'Dosing', ComplianceStatus.UNABLE_TO_ASSESS,
                "Patient weight not documented",
                recommendation="Document patient weight for dosing assessment",
            )

        dosing_results = []
        all_met = True
        is_pediatric = case.patient_age_years is not None and case.patient_age_years < 18

        for admin in admins:
            dosing_info = self.config.get_dosing_info(admin.medication_name)
            if not dosing_info:
                dosing_results.append(f"{admin.medication_name}: no dosing data available")
                continue

            if is_pediatric:
                expected = min(
                    case.patient_weight_kg * dosing_info.pediatric_mg_per_kg,
                    dosing_info.pediatric_max_mg,
                )
            else:
                if dosing_info.adult_high_weight_mg and case.patient_weight_kg > dosing_info.adult_high_weight_threshold_kg:
                    expected = dosing_info.adult_high_weight_mg
                else:
                    expected = dosing_info.adult_standard_mg

            if 0.9 * expected <= admin.dose_mg <= 1.1 * expected:
                dosing_results.append(f"{admin.medication_name}: {admin.dose_mg}mg appropriate for {case.patient_weight_kg}kg")
            else:
                dosing_results.append(f"{admin.medication_name}: {admin.dose_mg}mg given, expected ~{expected:.0f}mg")
                all_met = False

        status = ComplianceStatus.MET if all_met else ComplianceStatus.NOT_MET
        return _element_result(
            'Dosing', status, '; '.join(dosing_results),
            recommendation=None if all_met else "Adjust dose based on patient weight",
        )

    def _evaluate_redosing(self, case, admins) -> dict:
        if not admins:
            requirements = self._get_requirements(case)
            if requirements and not requirements.prophylaxis_indicated:
                return _element_result('Redosing', ComplianceStatus.NOT_APPLICABLE, "Prophylaxis not indicated")
            return _element_result('Redosing', ComplianceStatus.NOT_MET, "No prophylaxis administered")

        if not case.surgery_end_time or not case.actual_incision_time:
            return _element_result('Redosing', ComplianceStatus.PENDING, "Surgery still in progress or end time not recorded")

        duration_hours = case.surgery_duration_hours
        if duration_hours is None:
            return _element_result('Redosing', ComplianceStatus.UNABLE_TO_ASSESS, "Unable to calculate surgery duration")

        med_admins: dict[str, list] = {}
        for admin in admins:
            med_name = admin.medication_name.lower()
            med_admins.setdefault(med_name, []).append(admin)

        redose_results = []
        all_met = True

        for med_name, med_list in med_admins.items():
            if any(no_redose in med_name for no_redose in Config.NO_REDOSE_ANTIBIOTICS):
                redose_results.append(f"{med_name}: redosing not required")
                continue

            interval = self.config.get_redose_interval(med_name)
            if interval is None:
                redose_results.append(f"{med_name}: no redosing data")
                continue

            expected_doses = 1 + int(duration_hours / interval)
            actual_doses = len(med_list)

            if actual_doses >= expected_doses:
                redose_results.append(f"{med_name}: {actual_doses} doses for {duration_hours:.1f}h surgery (compliant)")
            else:
                redose_results.append(f"{med_name}: {actual_doses} doses, expected {expected_doses} for {duration_hours:.1f}h")
                all_met = False

        if not redose_results:
            return _element_result('Redosing', ComplianceStatus.NOT_APPLICABLE, "No antibiotics requiring redosing")

        status = ComplianceStatus.MET if all_met else ComplianceStatus.NOT_MET
        return _element_result(
            'Redosing', status, '; '.join(redose_results),
            recommendation=None if all_met else "Redose antibiotics per interval for prolonged surgery",
        )

    def _evaluate_postop_continuation(self, case, admins) -> dict:
        requirements = self._get_requirements(case)
        if requirements is None:
            return _element_result('Post-op Continuation', ComplianceStatus.UNABLE_TO_ASSESS, f"CPT codes not in guidelines: {case.cpt_codes}")

        if not requirements.prophylaxis_indicated:
            return _element_result('Post-op Continuation', ComplianceStatus.NOT_APPLICABLE, "Prophylaxis not indicated for this procedure")

        if not case.surgery_end_time:
            return _element_result('Post-op Continuation', ComplianceStatus.PENDING, "Surgery not yet complete")

        postop_admins = [a for a in admins if a.event_time > case.surgery_end_time]

        # Case 1: Not required and not allowed
        if not requirements.requires_postop_continuation and not requirements.postop_continuation_allowed:
            if not postop_admins:
                return _element_result('Post-op Continuation', ComplianceStatus.MET, "Prophylaxis appropriately stopped after surgery (no post-op continuation required)")
            latest_acceptable = case.surgery_end_time + timedelta(hours=2)
            late_doses = [a for a in postop_admins if a.event_time > latest_acceptable]
            if late_doses:
                return _element_result(
                    'Post-op Continuation', ComplianceStatus.NOT_MET,
                    f"{len(late_doses)} dose(s) given >2h after surgery end (post-op continuation not required)",
                    recommendation="Discontinue prophylaxis - post-op continuation not indicated for this procedure",
                )
            return _element_result('Post-op Continuation', ComplianceStatus.MET, f"{len(postop_admins)} dose(s) shortly after surgery (acceptable)")

        # Case 2: Allowed but not required (e.g., cardiac)
        if not requirements.requires_postop_continuation and requirements.postop_continuation_allowed:
            duration_limit = requirements.postop_duration_hours or requirements.duration_limit_hours
            if not postop_admins:
                return _element_result('Post-op Continuation', ComplianceStatus.MET, f"No post-op doses (continuation optional, up to {duration_limit}h allowed)")
            last_postop_dose = max(a.event_time for a in postop_admins)
            hours_covered = (last_postop_dose - case.surgery_end_time).total_seconds() / 3600
            return _element_result('Post-op Continuation', ComplianceStatus.MET, f"{len(postop_admins)} post-op dose(s) given over {hours_covered:.1f}h (optional continuation, limit {duration_limit}h)")

        # Case 3: Required
        postop_duration = requirements.postop_duration_hours or 24
        postop_interval = requirements.postop_interval_hours

        if not postop_admins:
            return _element_result(
                'Post-op Continuation', ComplianceStatus.NOT_MET,
                f"No post-op doses given (continuation required for {postop_duration}h)",
                recommendation=f"Continue prophylaxis for {postop_duration}h after surgery",
            )

        last_postop_dose = max(a.event_time for a in postop_admins)
        hours_covered = (last_postop_dose - case.surgery_end_time).total_seconds() / 3600

        if postop_interval:
            expected_doses = int(postop_duration / postop_interval)
            actual_doses = len(postop_admins)
            if actual_doses >= expected_doses and hours_covered >= (postop_duration * 0.8):
                return _element_result('Post-op Continuation', ComplianceStatus.MET, f"{actual_doses} post-op doses given over {hours_covered:.1f}h (required: {postop_duration}h Q{postop_interval}H)")
            elif hours_covered >= (postop_duration * 0.8):
                return _element_result('Post-op Continuation', ComplianceStatus.MET, f"Post-op prophylaxis continued for {hours_covered:.1f}h (required: {postop_duration}h)")
            else:
                return _element_result(
                    'Post-op Continuation', ComplianceStatus.NOT_MET,
                    f"Only {hours_covered:.1f}h of post-op coverage ({actual_doses} doses), required {postop_duration}h",
                    recommendation=f"Continue prophylaxis Q{postop_interval}H for {postop_duration}h total",
                )
        else:
            if hours_covered >= (postop_duration * 0.8):
                return _element_result('Post-op Continuation', ComplianceStatus.MET, f"Post-op prophylaxis continued for {hours_covered:.1f}h (required: {postop_duration}h)")
            else:
                return _element_result(
                    'Post-op Continuation', ComplianceStatus.NOT_MET,
                    f"Only {hours_covered:.1f}h of post-op coverage, required {postop_duration}h",
                    recommendation=f"Continue prophylaxis for full {postop_duration}h after surgery",
                )

    def _evaluate_discontinuation(self, case, admins) -> dict:
        if not admins:
            requirements = self._get_requirements(case)
            if requirements and not requirements.prophylaxis_indicated:
                return _element_result('Discontinuation', ComplianceStatus.NOT_APPLICABLE, "Prophylaxis not indicated")
            return _element_result('Discontinuation', ComplianceStatus.NOT_MET, "No prophylaxis administered")

        if not case.surgery_end_time:
            return _element_result('Discontinuation', ComplianceStatus.PENDING, "Surgery not yet complete")

        duration_limit = self.config.get_duration_limit(case.procedure_category)
        last_dose_time = max(a.event_time for a in admins)
        hours_since_surgery = (last_dose_time - case.surgery_end_time).total_seconds() / 3600

        if hours_since_surgery <= duration_limit:
            return _element_result(
                'Discontinuation', ComplianceStatus.MET,
                f"Last dose {hours_since_surgery:.1f}h after surgery end (limit: {duration_limit}h)",
            )
        else:
            return _element_result(
                'Discontinuation', ComplianceStatus.NOT_MET,
                f"Prophylaxis continued {hours_since_surgery:.1f}h after surgery (limit: {duration_limit}h)",
                recommendation=f"Discontinue prophylaxis - exceeded {duration_limit}h limit",
            )
