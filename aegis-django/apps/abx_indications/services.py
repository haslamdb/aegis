"""ABX Indication Monitoring service layer.

Orchestrates the indication extraction workflow:
1. Poll FHIR for new antibiotic orders
2. Fetch clinical notes for each patient
3. Extract indication via LLM
4. Check against CCHMC guidelines
5. Create alerts for red flags or off-guideline usage
6. Auto-accept old candidates past the threshold

Adapted from antimicrobial_usage BroadSpectrumMonitorService pattern.
"""

import logging
from datetime import timedelta

from django.db.models import Count
from django.utils import timezone

from apps.alerts.models import Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity

from .fhir_client import FHIRClient, get_fhir_client
from .logic.config import Config
from .logic.extractor import IndicationExtractor
from .logic.guidelines import CCHMCGuidelinesEngine, get_guidelines_engine, AgentCategory
from .models import (
    IndicationCandidate,
    CandidateStatus,
)

logger = logging.getLogger(__name__)


class IndicationMonitorService:
    """Monitors antibiotic orders for indication documentation and guideline concordance."""

    def __init__(
        self,
        fhir_client: FHIRClient | None = None,
        extractor: IndicationExtractor | None = None,
        guidelines: CCHMCGuidelinesEngine | None = None,
    ):
        self.fhir_client = fhir_client or get_fhir_client()
        self.extractor = extractor or IndicationExtractor()
        self.guidelines = guidelines or get_guidelines_engine()

    def check_new_orders(self) -> list[IndicationCandidate]:
        """Poll FHIR for new antibiotic orders and process them.

        Fetches recent MedicationRequests, skips those already tracked,
        then runs indication extraction + guideline check for each new one.

        Returns:
            List of newly created IndicationCandidate records.
        """
        orders = self.fhir_client.get_recent_medication_requests()
        logger.info(f"Found {len(orders)} active medication orders")

        new_candidates = []
        for order in orders:
            fhir_id = order["fhir_id"]

            # Deduplication: skip if already tracked
            if IndicationCandidate.objects.filter(medication_request_id=fhir_id).exists():
                continue

            try:
                candidate = self._process_order(order)
                if candidate:
                    new_candidates.append(candidate)
            except Exception as e:
                logger.error(f"Failed to process order {fhir_id}: {e}")

        logger.info(f"Created {len(new_candidates)} new indication candidates")
        return new_candidates

    def check_new_alerts(self) -> list[tuple[IndicationCandidate, Alert]]:
        """Create alerts for candidates that warrant ASP attention.

        Looks at pending candidates and creates alerts for:
        - Red flags (no indication, viral illness, ASB, never appropriate)
        - Off-guideline agent choices

        Returns:
            List of (candidate, alert) tuples for newly created alerts.
        """
        # Find pending candidates without alerts
        candidates = IndicationCandidate.objects.filter(
            status=CandidateStatus.PENDING,
            alert__isnull=True,
        )

        new_alerts = []
        for candidate in candidates:
            alert_type = self._determine_alert_type(candidate)
            if alert_type is None:
                continue

            try:
                alert = self._create_alert(candidate, alert_type)
                candidate.status = CandidateStatus.ALERTED
                candidate.alert = alert
                candidate.save(update_fields=['status', 'alert', 'updated_at'])
                new_alerts.append((candidate, alert))
            except Exception as e:
                logger.error(
                    f"Failed to create alert for candidate {candidate.pk}: {e}"
                )

        logger.info(f"Created {len(new_alerts)} new alerts")
        return new_alerts

    def _process_order(self, order: dict) -> IndicationCandidate | None:
        """Process a single medication order through the full pipeline.

        1. Fetch patient info + clinical notes
        2. Run LLM indication extraction
        3. Check extracted indication against CCHMC guidelines
        4. Save IndicationCandidate record

        Args:
            order: Medication order dict from FHIR client.

        Returns:
            Created IndicationCandidate, or None on failure.
        """
        patient_id = order["patient_id"]

        # Get patient demographics and encounter context
        patient_info = self.fhir_client.get_patient_encounter_info(patient_id)

        # Get clinical notes for LLM extraction
        notes_data = self.fhir_client.get_recent_notes(patient_id)
        note_texts = [n["content"] for n in notes_data if n.get("content")]

        if not note_texts:
            logger.warning(
                f"No clinical notes for patient {patient_id}, "
                f"order {order['fhir_id']} - marking as undocumented"
            )

        # Run LLM extraction
        extraction = self.extractor.extract(
            notes=note_texts or ["No clinical notes available."],
            antibiotic=order["medication_name"],
            order_date=order["start_date"].isoformat() if order.get("start_date") else None,
        )

        # Check against CCHMC guidelines
        guideline_result = None
        if extraction.guideline_disease_ids:
            guideline_result = self.guidelines.check_agent_by_disease_ids(
                disease_ids=extraction.guideline_disease_ids,
                prescribed_agent=order["medication_name"],
                patient_age_months=patient_info.get("age_months"),
            )

        # Build candidate record
        candidate = IndicationCandidate.objects.create(
            # Patient
            patient_id=patient_id,
            patient_mrn=patient_info.get("mrn", ""),
            patient_name=patient_info.get("patient_name", ""),
            patient_location=patient_info.get("location", ""),
            # Medication
            medication_request_id=order["fhir_id"],
            medication_name=order["medication_name"],
            rxnorm_code=order.get("rxnorm_code", ""),
            order_date=order.get("start_date") or timezone.now(),
            location=patient_info.get("location", ""),
            service=patient_info.get("service", ""),
            # Extraction results
            clinical_syndrome=extraction.primary_indication,
            clinical_syndrome_display=extraction.primary_indication_display,
            syndrome_category=extraction.indication_category,
            syndrome_confidence=extraction.indication_confidence,
            therapy_intent=extraction.therapy_intent,
            supporting_evidence=extraction.supporting_evidence,
            evidence_quotes=extraction.evidence_quotes,
            guideline_disease_ids=extraction.guideline_disease_ids,
            # Red flags
            indication_not_documented=extraction.indication_not_documented or not note_texts,
            likely_viral=extraction.likely_viral,
            asymptomatic_bacteriuria=extraction.asymptomatic_bacteriuria,
            never_appropriate=extraction.never_appropriate,
            # Guideline match
            cchmc_disease_matched=guideline_result.disease_matched if guideline_result else "",
            cchmc_agent_category=(
                guideline_result.current_agent_category.value
                if guideline_result
                else ""
            ),
            cchmc_first_line_agents=(
                guideline_result.first_line_agents
                if guideline_result
                else None
            ),
            cchmc_recommendation=(
                guideline_result.recommendation
                if guideline_result
                else ""
            ),
        )

        logger.info(
            f"Created candidate: {order['medication_name']} for "
            f"{patient_info.get('mrn', patient_id)} -> "
            f"{extraction.primary_indication_display} "
            f"({extraction.indication_confidence})"
        )

        return candidate

    def _determine_alert_type(self, candidate: IndicationCandidate) -> str | None:
        """Determine which alert type (if any) should be created.

        Priority order:
        1. Never-appropriate indication (highest priority)
        2. No indication documented
        3. Off-guideline agent
        4. No alert needed

        Returns:
            AlertType value string, or None if no alert warranted.
        """
        if candidate.never_appropriate:
            return AlertType.ABX_NEVER_APPROPRIATE

        if candidate.indication_not_documented:
            return AlertType.ABX_NO_INDICATION

        if candidate.likely_viral:
            return AlertType.ABX_NEVER_APPROPRIATE

        if candidate.asymptomatic_bacteriuria:
            return AlertType.ABX_NEVER_APPROPRIATE

        if candidate.cchmc_agent_category == AgentCategory.OFF_GUIDELINE.value:
            return AlertType.ABX_OFF_GUIDELINE

        return None

    def _create_alert(
        self,
        candidate: IndicationCandidate,
        alert_type: str,
    ) -> Alert:
        """Create an Alert + AlertAudit for a candidate.

        Args:
            candidate: The indication candidate triggering the alert.
            alert_type: AlertType choice value.

        Returns:
            Created Alert instance.
        """
        # Determine severity
        if alert_type == AlertType.ABX_NEVER_APPROPRIATE:
            severity = AlertSeverity.CRITICAL
            priority = 95
        elif alert_type == AlertType.ABX_NO_INDICATION:
            severity = AlertSeverity.HIGH
            priority = 85
        elif alert_type == AlertType.ABX_OFF_GUIDELINE:
            severity = AlertSeverity.MEDIUM
            priority = 70
        else:
            severity = AlertSeverity.INFO
            priority = 50

        # Build title
        type_labels = {
            AlertType.ABX_NEVER_APPROPRIATE: "Never Appropriate",
            AlertType.ABX_NO_INDICATION: "No Indication",
            AlertType.ABX_OFF_GUIDELINE: "Off Guideline",
        }
        label = type_labels.get(alert_type, "Review")

        title = f"ABX Indication: {label} - {candidate.medication_name}"

        # Build summary
        if candidate.clinical_syndrome_display:
            summary = (
                f"{candidate.medication_name} for "
                f"{candidate.clinical_syndrome_display} "
                f"({candidate.get_syndrome_confidence_display()})"
            )
        else:
            summary = f"{candidate.medication_name} - indication not documented"

        alert = Alert.objects.create(
            alert_type=alert_type,
            source_module='abx_indications',
            source_id=candidate.medication_request_id,
            title=title,
            summary=summary,
            details={
                'medication_name': candidate.medication_name,
                'rxnorm_code': candidate.rxnorm_code,
                'medication_request_id': candidate.medication_request_id,
                'clinical_syndrome': candidate.clinical_syndrome,
                'clinical_syndrome_display': candidate.clinical_syndrome_display,
                'syndrome_confidence': candidate.syndrome_confidence,
                'therapy_intent': candidate.therapy_intent,
                'supporting_evidence': candidate.supporting_evidence,
                'guideline_disease_ids': candidate.guideline_disease_ids,
                'cchmc_disease_matched': candidate.cchmc_disease_matched,
                'cchmc_agent_category': candidate.cchmc_agent_category,
                'cchmc_first_line_agents': candidate.cchmc_first_line_agents,
                'cchmc_recommendation': candidate.cchmc_recommendation,
                'red_flags': {
                    'indication_not_documented': candidate.indication_not_documented,
                    'likely_viral': candidate.likely_viral,
                    'asymptomatic_bacteriuria': candidate.asymptomatic_bacteriuria,
                    'never_appropriate': candidate.never_appropriate,
                },
                'location': candidate.location,
                'service': candidate.service,
                'patient_name': candidate.patient_name,
                'patient_mrn': candidate.patient_mrn,
                'patient_fhir_id': candidate.patient_id,
            },
            patient_id=candidate.patient_id,
            patient_mrn=candidate.patient_mrn,
            patient_name=candidate.patient_name,
            patient_location=candidate.patient_location,
            severity=severity,
            priority_score=priority,
        )

        AlertAudit.objects.create(
            alert=alert,
            action='created',
            old_status=None,
            new_status=AlertStatus.PENDING,
            details={'source': 'abx_indication_monitor'},
        )

        return alert

    def auto_accept_old(self) -> int:
        """Auto-accept candidates older than the configured threshold.

        Candidates with first-line or alternative agents that have been
        pending beyond AUTO_ACCEPT_HOURS are automatically accepted to
        reduce pharmacist workload.

        Returns:
            Number of candidates auto-accepted.
        """
        threshold = timezone.now() - timedelta(hours=Config.AUTO_ACCEPT_HOURS)

        # Only auto-accept candidates that are:
        # - Still pending
        # - Not flagged (no red flags)
        # - Agent is first-line or alternative (not off-guideline)
        candidates = IndicationCandidate.objects.filter(
            status=CandidateStatus.PENDING,
            created_at__lt=threshold,
            indication_not_documented=False,
            likely_viral=False,
            asymptomatic_bacteriuria=False,
            never_appropriate=False,
        ).exclude(
            cchmc_agent_category=AgentCategory.OFF_GUIDELINE.value,
        )

        count = candidates.update(status=CandidateStatus.AUTO_ACCEPTED)
        if count:
            logger.info(f"Auto-accepted {count} candidates older than {Config.AUTO_ACCEPT_HOURS}h")

        return count

    def get_stats(self) -> dict:
        """Get current indication monitoring statistics.

        Returns:
            Dict with counts by status, syndrome, agent category, etc.
        """
        all_qs = IndicationCandidate.objects.all()
        active_qs = all_qs.filter(
            status__in=[CandidateStatus.PENDING, CandidateStatus.ALERTED],
        )

        today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # By status
        by_status = {}
        for row in all_qs.values('status').annotate(count=Count('id')):
            by_status[row['status']] = row['count']

        # By syndrome category
        by_category = {}
        for row in active_qs.values('syndrome_category').annotate(count=Count('id')):
            by_category[row['syndrome_category']] = row['count']

        # By agent category
        by_agent = {}
        for row in active_qs.values('cchmc_agent_category').annotate(count=Count('id')):
            by_agent[row['cchmc_agent_category']] = row['count']

        # By medication
        by_medication = {}
        for row in active_qs.values('medication_name').annotate(count=Count('id')):
            by_medication[row['medication_name']] = row['count']

        # Red flag counts
        red_flags = {
            'no_indication': active_qs.filter(indication_not_documented=True).count(),
            'likely_viral': active_qs.filter(likely_viral=True).count(),
            'asymptomatic_bacteriuria': active_qs.filter(asymptomatic_bacteriuria=True).count(),
            'never_appropriate': active_qs.filter(never_appropriate=True).count(),
        }

        # Alert counts
        alert_qs = Alert.objects.filter(
            alert_type__in=[
                AlertType.ABX_NO_INDICATION,
                AlertType.ABX_NEVER_APPROPRIATE,
                AlertType.ABX_OFF_GUIDELINE,
            ],
        )
        active_alerts = alert_qs.filter(
            status__in=[
                AlertStatus.PENDING,
                AlertStatus.SENT,
                AlertStatus.ACKNOWLEDGED,
                AlertStatus.IN_PROGRESS,
                AlertStatus.SNOOZED,
            ],
        ).count()

        reviewed_today = all_qs.filter(
            status=CandidateStatus.REVIEWED,
            updated_at__gte=today_start,
        ).count()

        return {
            'total_candidates': all_qs.count(),
            'active_count': active_qs.count(),
            'pending_count': active_qs.filter(status=CandidateStatus.PENDING).count(),
            'alerted_count': active_qs.filter(status=CandidateStatus.ALERTED).count(),
            'reviewed_today': reviewed_today,
            'auto_accepted': all_qs.filter(status=CandidateStatus.AUTO_ACCEPTED).count(),
            'active_alerts': active_alerts,
            'by_status': by_status,
            'by_category': by_category,
            'by_agent_category': by_agent,
            'by_medication': by_medication,
            'red_flags': red_flags,
        }
