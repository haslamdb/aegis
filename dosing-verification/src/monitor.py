"""Dosing Verification real-time monitoring service.

Polls FHIR server for active antimicrobial orders and checks dosing appropriateness
based on indication, patient factors, allergies, and drug-drug interactions.

Generates tiered alerts (CRITICAL, HIGH, MODERATE) when dosing issues are detected.
"""

import logging
import time
from datetime import datetime, timedelta

from common.dosing_verification import DoseAlertStore
from common.dosing_verification.models import DoseAlertSeverity, DoseAlertStatus
from common.alert_store import AlertStore, AlertType
from common.channels import EmailChannel, TeamsWebhookChannel, TeamsMessage, EmailMessage

from .models import PatientContext
from .rules_engine import DosingRulesEngine
from .fhir_client import DosingFHIRClient

logger = logging.getLogger(__name__)


class DosingVerificationMonitor:
    """Real-time monitor for antimicrobial dosing verification."""

    def __init__(
        self,
        fhir_client: DosingFHIRClient | None = None,
        dose_alert_store: DoseAlertStore | None = None,
        alert_store: AlertStore | None = None,
        rules_engine: DosingRulesEngine | None = None,
        send_notifications: bool = True,
    ):
        """Initialize the monitor.

        Args:
            fhir_client: FHIR client for data fetching
            dose_alert_store: Store for dosing alerts
            alert_store: Main alert store for cross-module integration
            rules_engine: Rules engine for dosing evaluation
            send_notifications: Whether to send email/Teams notifications
        """
        self.fhir = fhir_client or DosingFHIRClient()
        self.dose_store = dose_alert_store or DoseAlertStore()
        self.alert_store = alert_store or AlertStore()
        self.rules_engine = rules_engine or DosingRulesEngine()
        self.send_notifications = send_notifications

        # Initialize notification channels
        if send_notifications:
            try:
                self.email = EmailChannel()
                self.teams = TeamsWebhookChannel()
            except Exception as e:
                logger.warning(f"Failed to initialize notification channels: {e}")
                self.email = None
                self.teams = None
        else:
            self.email = None
            self.teams = None

        self.processed_patients: set[str] = set()  # In-memory cache
        self.alerts_generated = 0

    def check_patient(self, patient_mrn: str, lookback_hours: int = 24) -> tuple[bool, list[str]]:
        """
        Check a single patient for dosing issues.

        Args:
            patient_mrn: Patient MRN to evaluate
            lookback_hours: Hours to look back for recent orders

        Returns:
            Tuple of (alert_generated, list of alert_ids)
        """
        logger.info(f"Checking patient {patient_mrn}")

        # Build patient context from FHIR
        try:
            context = self.fhir.build_patient_context(patient_mrn)
        except Exception as e:
            logger.error(f"Failed to build context for {patient_mrn}: {e}")
            return False, []

        if not context:
            logger.warning(f"No context available for {patient_mrn}")
            return False, []

        if not context.antimicrobials:
            logger.debug(f"No active antimicrobials for {patient_mrn}")
            return False, []

        # Run rules engine
        try:
            assessment = self.rules_engine.evaluate(context)
        except Exception as e:
            logger.error(f"Rules engine failed for {patient_mrn}: {e}")
            return False, []

        # Generate alerts for each flag
        alert_ids = []
        if assessment.flags:
            logger.info(f"Found {len(assessment.flags)} dosing flags for {patient_mrn}")
            for flag in assessment.flags:
                # Check if already alerted for this drug + flag type
                if not self.dose_store.check_if_alerted(
                    patient_mrn=patient_mrn,
                    drug=flag.drug,
                    flag_type=flag.flag_type.value
                ):
                    alert_id = self._create_alert(context, flag, assessment)
                    if alert_id:
                        alert_ids.append(alert_id)
                        self.alerts_generated += 1
                else:
                    logger.debug(f"Already alerted for {patient_mrn} - {flag.drug} - {flag.flag_type.value}")

        return len(alert_ids) > 0, alert_ids

    def _create_alert(self, context: PatientContext, flag, assessment) -> str | None:
        """Create and save alert for a dosing flag."""
        try:
            # Build patient factors JSON
            patient_factors_json = {
                "age_years": context.age_years,
                "weight_kg": context.weight_kg,
                "height_cm": context.height_cm,
                "scr": context.scr,
                "gfr": context.gfr,
                "is_on_dialysis": context.is_on_dialysis,
                "gestational_age_weeks": context.gestational_age_weeks,
            }

            # Build assessment details JSON
            assessment_details_json = {
                "assessment_id": assessment.assessment_id,
                "flags": [f.to_dict() for f in assessment.flags],
                "max_severity": assessment.max_severity.value if assessment.max_severity else None,
                "medications_evaluated": assessment.medications_evaluated,
                "indication": assessment.indication,
                "indication_confidence": assessment.indication_confidence,
            }

            # Save to dose alert store
            saved = self.dose_store.save_alert(
                assessment_id=assessment.assessment_id,
                patient_id=context.patient_id,
                patient_mrn=context.patient_mrn,
                patient_name=context.patient_name,
                flag=flag,
                patient_factors=patient_factors_json,
                assessment_details=assessment_details_json,
                encounter_id=context.encounter_id,
            )
            logger.info(f"Created alert {saved.id} for {context.patient_name} ({context.patient_mrn})")

            # Also save to main AlertStore for cross-module integration (CRITICAL and HIGH only)
            if flag.severity in [DoseAlertSeverity.CRITICAL, DoseAlertSeverity.HIGH]:
                try:
                    self.alert_store.save_alert(
                        alert_type=AlertType.DOSING_ALERT,
                        source_id=saved.id,
                        severity=flag.severity.value,
                        patient_id=context.patient_id,
                        patient_mrn=context.patient_mrn,
                        patient_name=context.patient_name,
                        title=f"Dosing Alert: {flag.drug} - {flag.flag_type.value.replace('_', ' ').title()}",
                        summary=flag.message,
                        content=flag.to_dict(),
                    )
                    logger.info(f"Also saved to main AlertStore for ASP queue visibility")
                except Exception as e:
                    logger.warning(f"Failed to save to main AlertStore: {e}")

            # Send notifications based on severity
            if self.send_notifications:
                self._send_notifications(saved, flag, context)

            return saved.id

        except Exception as e:
            logger.error(f"Failed to create alert: {e}", exc_info=True)
            return None

    def _send_notifications(self, alert, flag, context):
        """Send notifications based on severity tier."""
        try:
            # CRITICAL: Teams + Email
            if flag.severity == DoseAlertSeverity.CRITICAL:
                self._send_teams_notification(alert, flag, context)
                self._send_email_notification(alert, flag, context)
                self.dose_store.mark_sent(alert.id)
                logger.info(f"Sent CRITICAL notifications for {alert.id}")

            # HIGH: Email only
            elif flag.severity == DoseAlertSeverity.HIGH:
                self._send_email_notification(alert, flag, context)
                self.dose_store.mark_sent(alert.id)
                logger.info(f"Sent HIGH email notification for {alert.id}")

            # MODERATE: Dashboard only (no notification)
            else:
                logger.info(f"MODERATE alert {alert.id} - dashboard only")

        except Exception as e:
            logger.error(f"Failed to send notifications: {e}")

    def _send_teams_notification(self, alert, flag, context):
        """Send Teams notification for critical alerts."""
        if not self.teams:
            return

        try:
            message = TeamsMessage(
                title=f"🚨 CRITICAL DOSING ALERT: {flag.drug}",
                text=flag.message,
                theme_color="FF0000",  # Red for critical
                facts={
                    "Patient": f"{context.patient_name} ({context.patient_mrn})",
                    "Drug": flag.drug,
                    "Issue": flag.flag_type.value.replace("_", " ").title(),
                    "Current": flag.actual,
                    "Expected": flag.expected,
                    "Source": flag.rule_source,
                },
                actions=[
                    {
                        "@type": "OpenUri",
                        "name": "View Alert Details",
                        "targets": [{
                            "os": "default",
                            "uri": f"https://aegis-asp.com/dosing-verification/alert/{alert.id}"
                        }]
                    }
                ]
            )

            self.teams.send(message)
            logger.info(f"Sent Teams notification for {alert.id}")

        except Exception as e:
            logger.error(f"Failed to send Teams notification: {e}")

    def _send_email_notification(self, alert, flag, context):
        """Send email notification for critical/high alerts."""
        if not self.email:
            return

        try:
            severity_color = {
                "critical": "#DC3545",  # Red
                "high": "#FFC107",      # Amber
                "moderate": "#17A2B8",  # Blue
            }

            html_body = f"""
<html>
<head>
<style>
    body {{ font-family: Arial, sans-serif; }}
    .header {{ background-color: {severity_color.get(flag.severity.value, '#17A2B8')}; color: white; padding: 15px; }}
    .content {{ padding: 20px; }}
    .section {{ margin-bottom: 15px; }}
    .label {{ font-weight: bold; }}
    .alert-box {{ background-color: #f8f9fa; border-left: 4px solid {severity_color.get(flag.severity.value, '#17A2B8')}; padding: 15px; margin: 10px 0; }}
    .button {{ background-color: #007BFF; color: white; padding: 10px 20px; text-decoration: none; border-radius: 4px; display: inline-block; margin-top: 15px; }}
</style>
</head>
<body>
    <div class="header">
        <h2>DOSING ALERT: {flag.severity.value.upper()}</h2>
    </div>
    <div class="content">
        <div class="alert-box">
            <h3>{flag.drug} - {flag.flag_type.value.replace('_', ' ').title()}</h3>
            <p>{flag.message}</p>
        </div>

        <div class="section">
            <span class="label">Patient:</span> {context.patient_name} (MRN: {context.patient_mrn})
        </div>

        <div class="section">
            <span class="label">Current Dosing:</span> {flag.actual}<br>
            <span class="label">Expected Dosing:</span> {flag.expected}
        </div>

        <div class="section">
            <span class="label">Clinical Indication:</span> {flag.indication or 'Not specified'}<br>
            <span class="label">Guideline Source:</span> {flag.rule_source}
        </div>

        <div class="section">
            <span class="label">Patient Factors:</span><br>
            Age: {context.age_years:.1f} years | Weight: {context.weight_kg:.1f} kg<br>
            {'eGFR: ' + str(int(context.gfr)) + ' mL/min' if context.gfr else ''}
            {' | On dialysis' if context.is_on_dialysis else ''}
        </div>

        <a href="https://aegis-asp.com/dosing-verification/alert/{alert.id}" class="button">
            Review Alert in AEGIS
        </a>

        <p style="margin-top: 30px; font-size: 12px; color: #6c757d;">
            This is an automated alert from the AEGIS Dosing Verification Module.<br>
            Alert ID: {alert.id} | Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}
        </p>
    </div>
</body>
</html>
"""

            message = EmailMessage(
                to=["asp-team@example.com"],  # Configure in settings
                subject=f"[AEGIS] {flag.severity.value.upper()} Dosing Alert - {flag.drug} - {context.patient_name}",
                html=html_body,
            )

            self.email.send(message)
            logger.info(f"Sent email notification for {alert.id}")

        except Exception as e:
            logger.error(f"Failed to send email notification: {e}")

    def run_once(self, lookback_hours: int = 24) -> dict:
        """
        Single pass: evaluate all patients with active antimicrobials.

        Args:
            lookback_hours: Hours to look back for recent orders

        Returns:
            Dict with summary statistics
        """
        logger.info(f"Starting dosing verification scan (lookback: {lookback_hours}h)")
        start_time = time.time()

        # Get patients with active antimicrobial orders
        try:
            patients = self.fhir.get_patients_with_active_antimicrobials(lookback_hours=lookback_hours)
        except Exception as e:
            logger.error(f"Failed to fetch patients: {e}")
            return {"error": str(e)}

        logger.info(f"Found {len(patients)} patients with active antimicrobials")

        # Check each patient
        patients_checked = 0
        alerts_created = 0

        for patient_mrn in patients:
            try:
                alert_generated, alert_ids = self.check_patient(patient_mrn, lookback_hours)
                patients_checked += 1
                if alert_generated:
                    alerts_created += len(alert_ids)
            except Exception as e:
                logger.error(f"Error checking patient {patient_mrn}: {e}")

        elapsed = time.time() - start_time

        summary = {
            "timestamp": datetime.now().isoformat(),
            "lookback_hours": lookback_hours,
            "patients_found": len(patients),
            "patients_checked": patients_checked,
            "alerts_created": alerts_created,
            "elapsed_seconds": round(elapsed, 2),
        }

        logger.info(
            f"Scan complete: {patients_checked} patients checked, "
            f"{alerts_created} alerts created in {elapsed:.1f}s"
        )

        return summary

    def run_continuous(self, interval_minutes: int = 15, lookback_hours: int = 24):
        """
        Run continuous monitoring loop.

        Args:
            interval_minutes: Minutes between scans
            lookback_hours: Hours to look back for recent orders
        """
        logger.info(f"Starting continuous monitoring (interval: {interval_minutes}m, lookback: {lookback_hours}h)")

        while True:
            try:
                summary = self.run_once(lookback_hours)
                logger.info(f"Scan summary: {summary}")

                # Auto-accept old alerts (>72 hours)
                try:
                    auto_accepted = self.dose_store.auto_accept_old(hours=72)
                    if auto_accepted > 0:
                        logger.info(f"Auto-accepted {auto_accepted} old alerts")
                except Exception as e:
                    logger.warning(f"Auto-accept failed: {e}")

            except Exception as e:
                logger.error(f"Error in monitoring loop: {e}", exc_info=True)

            # Sleep until next scan
            logger.info(f"Sleeping {interval_minutes} minutes until next scan")
            time.sleep(interval_minutes * 60)

    def auto_accept_old_alerts(self, hours: int = 72) -> int:
        """Auto-accept alerts older than specified hours without human resolution.

        Args:
            hours: Hours after which to auto-accept. Default 72.

        Returns:
            Number of alerts auto-accepted.
        """
        return self.dose_store.auto_accept_old(hours=hours)
