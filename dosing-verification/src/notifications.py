"""Notification handler for dosing verification alerts."""

import logging
from datetime import datetime
from typing import Any

from common.channels import (
    TeamsWebhookChannel,
    TeamsMessage,
    TeamsAction,
    EmailChannel,
    EmailMessage,
    ReceiptTracker,
    NotificationChannel,
)
from common.dosing_verification import (
    DoseAssessment,
    DoseAlertSeverity,
    DoseFlagType,
    DoseFlag,
)

logger = logging.getLogger(__name__)


class DosingNotificationHandler:
    """Handles tiered notifications for dosing alerts."""

    def __init__(
        self,
        teams_webhook_url: str | None = None,
        email_config: dict | None = None,
        receipt_tracker: ReceiptTracker | None = None,
    ):
        """Initialize notification handler.

        Args:
            teams_webhook_url: Microsoft Teams webhook URL
            email_config: Email configuration dict (smtp_host, smtp_port, from_addr)
            receipt_tracker: Optional receipt tracker for delivery confirmation
        """
        self.teams_channel = None
        self.email_channel = None
        self.receipt_tracker = receipt_tracker

        # Initialize Teams channel if configured
        if teams_webhook_url:
            self.teams_channel = TeamsWebhookChannel(
                webhook_url=teams_webhook_url,
                receipt_tracker=receipt_tracker,
            )

        # Initialize Email channel if configured
        if email_config:
            self.email_channel = EmailChannel(
                smtp_host=email_config.get("smtp_host", "localhost"),
                smtp_port=email_config.get("smtp_port", 587),
                from_addr=email_config.get("from_addr", "asp@example.com"),
                receipt_tracker=receipt_tracker,
            )

    def send_assessment_alert(
        self,
        assessment: DoseAssessment,
        recipient_email: str | None = None,
    ) -> dict[str, bool]:
        """Send tiered notifications for dose assessment.

        Routing logic:
        - CRITICAL/HIGH: Teams + Email
        - MODERATE: Teams only
        - LOW: No immediate notification (return empty)

        Args:
            assessment: DoseAssessment with flags
            recipient_email: Email address for email notifications

        Returns:
            Dict with 'teams' and 'email' success status
        """
        results = {"teams": False, "email": False}

        # No flags = no notification
        if not assessment.flags:
            logger.debug(f"Assessment {assessment.assessment_id} has no flags, skipping notification")
            return results

        # Determine notification tier
        severity = assessment.max_severity
        if severity is None:
            return results

        # LOW severity: no immediate notification
        if severity == DoseAlertSeverity.LOW:
            logger.info(f"Assessment {assessment.assessment_id} is LOW severity, no immediate notification")
            return results

        # MODERATE: Teams only
        if severity == DoseAlertSeverity.MODERATE:
            if self.teams_channel:
                results["teams"] = self._send_teams_notification(assessment)
            return results

        # CRITICAL/HIGH: Teams + Email
        if severity in [DoseAlertSeverity.CRITICAL, DoseAlertSeverity.HIGH]:
            if self.teams_channel:
                results["teams"] = self._send_teams_notification(assessment)
            if self.email_channel and recipient_email:
                results["email"] = self._send_email_notification(assessment, recipient_email)
            return results

        return results

    def _send_teams_notification(self, assessment: DoseAssessment) -> bool:
        """Send Teams notification for assessment.

        Args:
            assessment: DoseAssessment to notify about

        Returns:
            True if sent successfully
        """
        try:
            # Build Teams adaptive card message
            message = self._build_teams_message(assessment)

            # Send via Teams channel
            self.teams_channel.send(message)

            logger.info(
                f"Sent Teams notification for assessment {assessment.assessment_id}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send Teams notification for {assessment.assessment_id}: {e}",
                exc_info=True,
            )
            return False

    def _send_email_notification(
        self, assessment: DoseAssessment, recipient: str
    ) -> bool:
        """Send email notification for assessment.

        Args:
            assessment: DoseAssessment to notify about
            recipient: Email address to send to

        Returns:
            True if sent successfully
        """
        try:
            # Build email message
            message = self._build_email_message(assessment)

            # Send via email channel with recipient
            self.email_channel.send(message, to_addresses=[recipient])

            logger.info(
                f"Sent email notification for assessment {assessment.assessment_id} to {recipient}"
            )
            return True

        except Exception as e:
            logger.error(
                f"Failed to send email notification for {assessment.assessment_id}: {e}",
                exc_info=True,
            )
            return False

    def _build_teams_message(self, assessment: DoseAssessment) -> TeamsMessage:
        """Build Teams adaptive card for assessment.

        Args:
            assessment: DoseAssessment to format

        Returns:
            TeamsMessage ready to send
        """
        # Determine color based on severity
        severity_colors = {
            DoseAlertSeverity.CRITICAL: "Attention",  # Red
            DoseAlertSeverity.HIGH: "Warning",        # Orange
            DoseAlertSeverity.MODERATE: "Good",       # Green
            DoseAlertSeverity.LOW: "Default",         # Gray
        }
        color = severity_colors.get(assessment.max_severity, "Default")

        # Build title
        severity_text = assessment.max_severity.value.upper() if assessment.max_severity else "ALERT"
        title = f"🔔 Dosing Alert: {severity_text} - {assessment.patient_name} (MRN: {assessment.patient_mrn})"

        # Build facts as list of tuples (not dict)
        facts = [
            ("Patient", f"{assessment.patient_name} (MRN: {assessment.patient_mrn})"),
            ("Assessment ID", assessment.assessment_id),
            ("Flags", f"{len(assessment.flags)} dosing issue(s) detected"),
        ]

        # Add flag details to facts
        for i, flag in enumerate(assessment.flags, 1):
            flag_name = DoseFlagType.display_name(flag.flag_type)
            facts.append((
                f"Issue #{i}: {flag_name}",
                f"Drug: {flag.drug} | {flag.message} | Expected: {flag.expected} | Actual: {flag.actual}"
            ))

        # Build patient factors section
        patient_info = []
        if assessment.age_years:
            patient_info.append(f"Age: {assessment.age_years:.0f} years")
        if assessment.weight_kg:
            patient_info.append(f"Weight: {assessment.weight_kg:.1f} kg")
        if assessment.scr:
            patient_info.append(f"SCr: {assessment.scr:.2f}")
        if assessment.gfr:
            patient_info.append(f"GFR: {assessment.gfr:.0f}")
        if assessment.is_on_dialysis:
            patient_info.append("⚠️ On dialysis")
        if assessment.indication:
            patient_info.append(f"Indication: {assessment.indication}")

        # Build text section with patient factors
        patient_facts = " | ".join(patient_info) if patient_info else "No additional factors"
        text = f"**Patient Factors:** {patient_facts}"

        # Build actions
        actions = [
            TeamsAction(
                title="View in Dashboard",
                url=f"https://aegis-asp.com/dosing-verification/assessment/{assessment.assessment_id}",
            ),
            TeamsAction(
                title="Patient Chart",
                url=f"https://aegis-asp.com/patient/{assessment.patient_mrn}",
            ),
        ]

        message = TeamsMessage(
            title=title,
            facts=facts,
            text=text,
            color=color,
            alert_id=assessment.assessment_id,
            actions=actions,
        )

        return message

    def _build_email_message(self, assessment: DoseAssessment) -> EmailMessage:
        """Build email message for assessment.

        Args:
            assessment: DoseAssessment to format

        Returns:
            EmailMessage ready to send
        """
        # Build subject
        severity_text = assessment.max_severity.value.upper() if assessment.max_severity else "ALERT"
        subject = f"[{severity_text}] Dosing Alert: {assessment.patient_name} ({assessment.patient_mrn})"

        # Build HTML body
        html_body = self._build_email_html(assessment)

        # Build plain text body
        text_body = self._build_email_text(assessment)

        message = EmailMessage(
            subject=subject,
            text_body=text_body,
            html_body=html_body,
        )

        return message

    def _build_email_html(self, assessment: DoseAssessment) -> str:
        """Build HTML email body.

        Args:
            assessment: DoseAssessment to format

        Returns:
            HTML string
        """
        # Build flag list
        flag_html = ""
        for i, flag in enumerate(assessment.flags, 1):
            flag_name = DoseFlagType.display_name(flag.flag_type)
            flag_html += f"""
            <div style="margin-bottom: 15px; border-left: 3px solid #dc3545; padding-left: 10px;">
                <strong>Issue #{i}: {flag_name}</strong><br>
                <strong>Drug:</strong> {flag.drug}<br>
                <strong>Issue:</strong> {flag.message}<br>
                <strong>Expected:</strong> {flag.expected}<br>
                <strong>Actual:</strong> {flag.actual}<br>
                <strong>Source:</strong> {flag.rule_source}
            </div>
            """

        # Build patient factors
        patient_info = []
        if assessment.age_years:
            patient_info.append(f"<li>Age: {assessment.age_years:.0f} years</li>")
        if assessment.weight_kg:
            patient_info.append(f"<li>Weight: {assessment.weight_kg:.1f} kg</li>")
        if assessment.scr:
            patient_info.append(f"<li>SCr: {assessment.scr:.2f} mg/dL</li>")
        if assessment.gfr:
            patient_info.append(f"<li>GFR: {assessment.gfr:.0f} mL/min</li>")
        if assessment.is_on_dialysis:
            patient_info.append("<li>⚠️ On dialysis</li>")
        if assessment.indication:
            patient_info.append(f"<li>Indication: {assessment.indication}</li>")

        patient_html = "".join(patient_info) if patient_info else "<li>No additional factors</li>"

        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; }}
                .alert-box {{ background-color: #f8d7da; border: 1px solid #dc3545; padding: 15px; margin-bottom: 20px; }}
                .info-box {{ background-color: #d1ecf1; border: 1px solid #0c5460; padding: 15px; margin-bottom: 20px; }}
            </style>
        </head>
        <body>
            <h2>🔔 Antimicrobial Dosing Alert</h2>

            <div class="alert-box">
                <strong>Severity:</strong> {assessment.max_severity.value.upper() if assessment.max_severity else 'ALERT'}<br>
                <strong>Patient:</strong> {assessment.patient_name} (MRN: {assessment.patient_mrn})<br>
                <strong>Assessment ID:</strong> {assessment.assessment_id}<br>
                <strong>Time:</strong> {assessment.assessed_at}
            </div>

            <h3>Dosing Issues Detected:</h3>
            {flag_html}

            <h3>Patient Factors:</h3>
            <div class="info-box">
                <ul>
                    {patient_html}
                </ul>
            </div>

            <h3>Medications Evaluated:</h3>
            <ul>
            {"".join([f"<li>{med['drug']}: {med['dose']} {med['interval']} {med['route']}</li>" for med in assessment.medications_evaluated])}
            </ul>

            <p><a href="https://aegis-asp.com/dosing-verification/assessment/{assessment.assessment_id}">View in Dashboard</a></p>

            <hr>
            <p style="font-size: 12px; color: #6c757d;">
                This is an automated alert from AEGIS Antimicrobial Dosing Verification.
                Please review and take appropriate action.
            </p>
        </body>
        </html>
        """

        return html

    def _build_email_text(self, assessment: DoseAssessment) -> str:
        """Build plain text email body.

        Args:
            assessment: DoseAssessment to format

        Returns:
            Plain text string
        """
        # Build flag list
        flag_text = ""
        for i, flag in enumerate(assessment.flags, 1):
            flag_name = DoseFlagType.display_name(flag.flag_type)
            flag_text += f"""
Issue #{i}: {flag_name}
  Drug: {flag.drug}
  Issue: {flag.message}
  Expected: {flag.expected}
  Actual: {flag.actual}
  Source: {flag.rule_source}

"""

        # Build patient factors
        patient_info = []
        if assessment.age_years:
            patient_info.append(f"- Age: {assessment.age_years:.0f} years")
        if assessment.weight_kg:
            patient_info.append(f"- Weight: {assessment.weight_kg:.1f} kg")
        if assessment.scr:
            patient_info.append(f"- SCr: {assessment.scr:.2f} mg/dL")
        if assessment.gfr:
            patient_info.append(f"- GFR: {assessment.gfr:.0f} mL/min")
        if assessment.is_on_dialysis:
            patient_info.append("- On dialysis")
        if assessment.indication:
            patient_info.append(f"- Indication: {assessment.indication}")

        patient_text = "\n".join(patient_info) if patient_info else "No additional factors"

        # Build medications list
        meds_text = "\n".join([
            f"- {med['drug']}: {med['dose']} {med['interval']} {med['route']}"
            for med in assessment.medications_evaluated
        ])

        text = f"""
🔔 Antimicrobial Dosing Alert

Severity: {assessment.max_severity.value.upper() if assessment.max_severity else 'ALERT'}
Patient: {assessment.patient_name} (MRN: {assessment.patient_mrn})
Assessment ID: {assessment.assessment_id}
Time: {assessment.assessed_at}

Dosing Issues Detected:
{flag_text}

Patient Factors:
{patient_text}

Medications Evaluated:
{meds_text}

View in Dashboard: https://aegis-asp.com/dosing-verification/assessment/{assessment.assessment_id}

---
This is an automated alert from AEGIS Antimicrobial Dosing Verification.
Please review and take appropriate action.
"""

        return text
