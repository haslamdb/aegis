"""
Dosing Verification Service.

Encapsulates the dosing check pipeline so it can be called from
both the management command (CLI) and Celery tasks.
"""

import logging

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity
from .fhir_client import DosingFHIRClient
from .rules_engine import DosingRulesEngine
from .alert_models import DoseAlertSeverity, DoseFlagType
from .views import FLAG_TYPE_TO_ALERT_TYPE

logger = logging.getLogger(__name__)

# Map DoseAlertSeverity to AlertSeverity
SEVERITY_MAP = {
    DoseAlertSeverity.CRITICAL: AlertSeverity.CRITICAL,
    DoseAlertSeverity.HIGH: AlertSeverity.HIGH,
    DoseAlertSeverity.MODERATE: AlertSeverity.MEDIUM,
    DoseAlertSeverity.LOW: AlertSeverity.LOW,
}


class DosingMonitorService:
    """Service for dosing verification checks."""

    def run_check(self, hours=24):
        """
        Run a single dosing verification check.

        Args:
            hours: Look back window in hours.

        Returns:
            Dict with keys: total_flags, alerts_created, alerts_skipped, errors.
        """
        result = {
            'total_flags': 0,
            'alerts_created': 0,
            'alerts_skipped': 0,
            'errors': [],
        }

        try:
            client = DosingFHIRClient()
        except Exception as e:
            logger.error(f"Failed to initialize FHIR client: {e}")
            result['errors'].append({'stage': 'init_fhir', 'error': str(e)})
            return result

        engine = DosingRulesEngine()

        try:
            patients = client.get_patients_with_active_antimicrobials(hours=hours)
        except Exception as e:
            logger.error(f"Failed to fetch patients from FHIR: {e}")
            result['errors'].append({'stage': 'fetch_patients', 'error': str(e)})
            return result

        logger.info(f"Found {len(patients)} patients with active antimicrobials")

        for patient_id in patients:
            try:
                context = client.build_patient_context(patient_id)
                if not context:
                    continue

                assessment = engine.evaluate(context)

                if not assessment.flags:
                    continue

                result['total_flags'] += len(assessment.flags)

                for flag in assessment.flags:
                    # Determine alert type from flag type
                    flag_value = flag.flag_type.value if hasattr(flag.flag_type, 'value') else flag.flag_type
                    alert_type = FLAG_TYPE_TO_ALERT_TYPE.get(flag_value, AlertType.DOSING_INDICATION)

                    # Build source_id for deduplication
                    source_id = f'{patient_id}-{flag_value}-{flag.drug}'

                    # Check for existing active alert (deduplication)
                    existing = Alert.objects.filter(
                        source_module='dosing_verification',
                        source_id=source_id,
                        status__in=[
                            AlertStatus.PENDING,
                            AlertStatus.SENT,
                            AlertStatus.ACKNOWLEDGED,
                            AlertStatus.IN_PROGRESS,
                        ],
                    ).exists()

                    if existing:
                        result['alerts_skipped'] += 1
                        continue

                    # Map severity
                    severity_value = flag.severity.value if hasattr(flag.severity, 'value') else flag.severity
                    try:
                        dose_severity = DoseAlertSeverity(severity_value)
                    except (ValueError, KeyError):
                        dose_severity = DoseAlertSeverity.MODERATE
                    django_severity = SEVERITY_MAP.get(dose_severity, AlertSeverity.MEDIUM)

                    # Build details JSONField
                    details = {
                        'drug': flag.drug,
                        'flag_type': flag_value,
                        'flag_type_display': DoseFlagType.display_name(flag_value),
                        'indication': flag.indication or '',
                        'expected_dose': flag.expected,
                        'actual_dose': flag.actual,
                        'rule_source': flag.rule_source,
                        'patient_factors': assessment.to_alert_content().get('patient_factors', {}),
                        'assessment': assessment.to_dict(),
                        'medications': assessment.medications_evaluated,
                        'flags': [f.to_dict() for f in assessment.flags],
                    }

                    if flag.details:
                        details['flag_details'] = flag.details

                    # Priority score
                    if django_severity == AlertSeverity.CRITICAL:
                        priority = 95
                    elif django_severity == AlertSeverity.HIGH:
                        priority = 75
                    elif django_severity == AlertSeverity.MEDIUM:
                        priority = 50
                    else:
                        priority = 25

                    alert = Alert.objects.create(
                        alert_type=alert_type,
                        source_module='dosing_verification',
                        source_id=source_id,
                        title=f'Dosing: {DoseFlagType.display_name(flag_value)} - {flag.drug}',
                        summary=flag.message,
                        details=details,
                        patient_id=assessment.patient_id,
                        patient_mrn=assessment.patient_mrn,
                        patient_name=assessment.patient_name,
                        severity=django_severity,
                        priority_score=priority,
                    )

                    AlertAudit.objects.create(
                        alert=alert,
                        action='created',
                        old_status=None,
                        new_status=AlertStatus.PENDING,
                        details={'source': 'dosing_verification_monitor'},
                    )

                    result['alerts_created'] += 1

            except Exception as e:
                logger.warning(f'Error processing patient {patient_id}: {e}')
                result['errors'].append({
                    'patient_id': patient_id,
                    'error': str(e),
                })
                continue

        logger.info(
            f"Dosing check complete: {result['total_flags']} flags, "
            f"{result['alerts_created']} alerts created, "
            f"{result['alerts_skipped']} duplicates skipped"
        )
        return result
