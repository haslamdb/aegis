"""
Surgical prophylaxis batch evaluation service.

Orchestrates FHIR data retrieval, case building, compliance evaluation,
and alert creation for retrospective ASHP bundle analysis.
"""

import logging
from datetime import timedelta
from typing import Optional

from django.db.models import Count, Q, Avg
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertSeverity, AlertStatus

from .fhir_client import FHIRClient
from .logic.evaluator import ProphylaxisEvaluator
from .logic.guidelines import GuidelinesConfig, get_guidelines_config
from .models import (
    ComplianceStatus,
    ProcedureCategory,
    ProphylaxisEvaluation,
    ProphylaxisMedication,
    SurgicalCase,
)

logger = logging.getLogger(__name__)


class SurgicalProphylaxisService:
    """Batch evaluation orchestrator for surgical prophylaxis compliance."""

    def __init__(self, fhir_client=None, guidelines=None):
        self.fhir_client = fhir_client or FHIRClient()
        self.guidelines = guidelines or get_guidelines_config()
        self.evaluator = ProphylaxisEvaluator(self.guidelines)

    def check_new_cases(self, hours_back: int = 24, dry_run: bool = False) -> list[dict]:
        """
        Fetch procedures from FHIR, evaluate compliance, create alerts.

        Returns list of evaluation result dicts.
        """
        now = timezone.now()
        date_from = now - timedelta(hours=hours_back)

        procedures = self.fhir_client.get_surgical_procedures(
            date_from=date_from, date_to=now,
        )

        logger.info(f"Found {len(procedures)} procedures to evaluate")

        evaluations = []
        alerts_created = 0

        for procedure in procedures:
            try:
                result = self._process_case(procedure, dry_run=dry_run)
                if result:
                    evaluations.append(result)
                    if result.get('alert_created'):
                        alerts_created += 1
            except Exception as e:
                logger.error(f"Error evaluating procedure {procedure.get('id')}: {e}")
                continue

        logger.info(f"Completed: {len(evaluations)} evaluations, {alerts_created} alerts created")
        return evaluations

    def _process_case(self, procedure: dict, dry_run: bool = False) -> Optional[dict]:
        """Build SurgicalCase, evaluate, save evaluation, create alert if needed."""
        case_data = self.fhir_client.build_surgical_case_data(procedure)

        # Create or update SurgicalCase
        case, created = SurgicalCase.objects.update_or_create(
            case_id=case_data['case_id'],
            defaults=case_data,
        )

        # Evaluate
        eval_result = self.evaluator.evaluate_case(case)

        # Save evaluation
        evaluation = ProphylaxisEvaluation.objects.create(
            case=case,
            evaluation_time=timezone.now(),
            **eval_result,
        )

        result = {
            'case_id': case.case_id,
            'patient_mrn': case.patient_mrn,
            'procedure': case.procedure_description,
            'bundle_compliant': eval_result['bundle_compliant'],
            'compliance_score': eval_result['compliance_score'],
            'excluded': eval_result['excluded'],
            'alert_created': False,
        }

        # Create alert for non-compliant cases
        if not eval_result['bundle_compliant'] and not eval_result['excluded'] and not dry_run:
            alert = self._create_alert(case, evaluation, eval_result)
            if alert:
                evaluation.alert = alert
                evaluation.save(update_fields=['alert', 'updated_at'])
                result['alert_created'] = True

        return result

    def _create_alert(self, case, evaluation, eval_result) -> Optional[Alert]:
        """Create Alert for a non-compliant case."""
        # Check for existing active alert
        existing = Alert.objects.filter(
            alert_type=AlertType.SURGICAL_PROPHYLAXIS,
            source_id=case.case_id,
            status__in=[AlertStatus.PENDING, AlertStatus.ACKNOWLEDGED],
        ).exists()

        if existing:
            logger.info(f"Alert already exists for case {case.case_id}")
            return None

        severity = self._determine_severity(eval_result)

        not_met = []
        for name, result in evaluation.element_results_list:
            if result.get('status') == ComplianceStatus.NOT_MET:
                not_met.append(result)

        element_names = [e.get('element_name', '') for e in not_met]
        title = f"Surgical Prophylaxis: {', '.join(element_names)}"
        summary = (
            f"{case.procedure_description} - "
            f"{eval_result['elements_met']}/{eval_result['elements_total']} elements met. "
            f"Issues: {', '.join(element_names)}"
        )

        details = {
            'case_id': case.case_id,
            'encounter_id': case.encounter_id,
            'procedure': case.procedure_description,
            'procedure_category': case.procedure_category,
            'cpt_codes': case.cpt_codes,
            'compliance_score': eval_result['compliance_score'],
            'elements_met': eval_result['elements_met'],
            'elements_total': eval_result['elements_total'],
            'not_met_elements': [
                {
                    'name': e.get('element_name', ''),
                    'details': e.get('details', ''),
                    'recommendation': e.get('recommendation', ''),
                }
                for e in not_met
            ],
            'recommendations': eval_result['recommendations'],
        }

        alert = Alert.objects.create(
            alert_type=AlertType.SURGICAL_PROPHYLAXIS,
            source_module='surgical_prophylaxis',
            source_id=case.case_id,
            title=title[:500],
            summary=summary,
            details=details,
            patient_mrn=case.patient_mrn,
            patient_name=case.patient_name,
            patient_location=case.location,
            severity=severity,
            status=AlertStatus.PENDING,
        )

        alert.create_audit_entry(action='created', extra_details={'source': 'batch_evaluation'})
        return alert

    def _determine_severity(self, eval_result: dict) -> str:
        indication = eval_result.get('indication_result', {})
        timing = eval_result.get('timing_result', {})
        agent = eval_result.get('agent_result', {})
        dosing = eval_result.get('dosing_result', {})

        if indication.get('status') == ComplianceStatus.NOT_MET:
            return AlertSeverity.CRITICAL

        if timing.get('status') == ComplianceStatus.NOT_MET:
            details = timing.get('details', '').lower()
            if 'after incision' in details:
                return AlertSeverity.CRITICAL
            return AlertSeverity.HIGH

        if (agent.get('status') == ComplianceStatus.NOT_MET or
                dosing.get('status') == ComplianceStatus.NOT_MET):
            return AlertSeverity.HIGH

        return AlertSeverity.MEDIUM

    def get_stats(self) -> dict:
        """Get compliance statistics."""
        now = timezone.now()
        last_30d = now - timedelta(days=30)

        total = SurgicalCase.objects.filter(created_at__gte=last_30d).count()
        evals = ProphylaxisEvaluation.objects.filter(
            case__created_at__gte=last_30d
        )
        compliant = evals.filter(bundle_compliant=True).count()
        excluded = evals.filter(excluded=True).count()
        non_compliant = evals.filter(bundle_compliant=False, excluded=False).count()

        avg_score = evals.exclude(excluded=True).aggregate(
            avg=Avg('compliance_score')
        )['avg'] or 0

        pending_alerts = Alert.objects.filter(
            alert_type=AlertType.SURGICAL_PROPHYLAXIS,
            status=AlertStatus.PENDING,
        ).count()

        assessed = total - excluded
        compliance_rate = (compliant / assessed * 100) if assessed > 0 else 0

        # Per-element compliance rates
        element_rates = {}
        assessed_evals = evals.exclude(excluded=True)
        if assessed_evals.exists():
            for name, field_name in [
                ('Indication', 'indication_result'),
                ('Agent Selection', 'agent_result'),
                ('Pre-op Timing', 'timing_result'),
                ('Dosing', 'dosing_result'),
                ('Redosing', 'redosing_result'),
                ('Post-op Continuation', 'postop_result'),
                ('Discontinuation', 'discontinuation_result'),
            ]:
                all_evals = list(assessed_evals)
                met = sum(1 for e in all_evals if getattr(e, field_name, {}).get('status') == ComplianceStatus.MET)
                applicable = sum(1 for e in all_evals
                               if getattr(e, field_name, {}).get('status') not in (ComplianceStatus.NOT_APPLICABLE, None, ''))
                element_rates[name] = round(met / applicable * 100, 1) if applicable > 0 else 0

        # By category
        by_category = {}
        for cat in ProcedureCategory:
            cat_evals = evals.filter(case__procedure_category=cat.value)
            cat_total = cat_evals.count()
            if cat_total > 0:
                cat_compliant = cat_evals.filter(bundle_compliant=True).count()
                cat_assessed = cat_total - cat_evals.filter(excluded=True).count()
                by_category[cat.label] = {
                    'total': cat_total,
                    'compliant': cat_compliant,
                    'rate': round(cat_compliant / cat_assessed * 100, 1) if cat_assessed > 0 else 0,
                }

        return {
            'total_cases': total,
            'assessed_cases': assessed,
            'compliant_cases': compliant,
            'compliant': compliant,
            'non_compliant_cases': non_compliant,
            'non_compliant': non_compliant,
            'excluded_cases': excluded,
            'excluded': excluded,
            'compliance_rate': round(compliance_rate, 1),
            'avg_score': round(avg_score, 1),
            'avg_compliance_score': round(avg_score, 1),
            'pending_alerts': pending_alerts,
            'element_rates': element_rates,
            'by_category': by_category,
            'period': '30 days',
        }
