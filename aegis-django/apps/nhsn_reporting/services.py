"""NHSN Reporting Service — orchestrator for all NHSN reporting operations."""

import logging
from datetime import date, timedelta

from django.db import transaction
from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertStatus, AlertSeverity
from apps.hai_detection.models import HAICandidate, CandidateStatus

from .models import (
    NHSNEvent, HAIEventType,
    DenominatorMonthly,
    AUMonthlySummary, AUAntimicrobialUsage,
    ARQuarterlySummary, ARIsolate, ARSusceptibility, ARPhenotypeSummary,
    SubmissionAudit,
)
from .logic import config as cfg

logger = logging.getLogger(__name__)


class NHSNReportingService:
    """Orchestrator for NHSN reporting operations."""

    def __init__(self):
        self._au_extractor = None
        self._ar_extractor = None
        self._denom_calculator = None

    def _get_au_extractor(self):
        if self._au_extractor is None:
            from .logic.au_extractor import AUDataExtractor
            self._au_extractor = AUDataExtractor()
        return self._au_extractor

    def _get_ar_extractor(self):
        if self._ar_extractor is None:
            from .logic.ar_extractor import ARDataExtractor
            self._ar_extractor = ARDataExtractor()
        return self._ar_extractor

    def _get_denom_calculator(self):
        if self._denom_calculator is None:
            from .logic.denominator import DenominatorCalculator
            self._denom_calculator = DenominatorCalculator()
        return self._denom_calculator

    # ---- HAI Event Operations ----

    def create_nhsn_events(self, from_date=None, to_date=None):
        """Convert confirmed HAICandidates to NHSNEvents."""
        if from_date is None:
            from_date = timezone.now() - timedelta(days=30)
        if to_date is None:
            to_date = timezone.now()

        confirmed = HAICandidate.objects.filter(
            status=CandidateStatus.CONFIRMED,
            nhsn_reported=False,
            culture_date__gte=from_date,
            culture_date__lte=to_date,
        )

        created_count = 0
        for candidate in confirmed:
            hai_type_map = {
                'clabsi': HAIEventType.CLABSI,
                'cauti': HAIEventType.CAUTI,
                'ssi': HAIEventType.SSI,
                'vae': HAIEventType.VAE,
            }
            hai_type = hai_type_map.get(candidate.hai_type, HAIEventType.CLABSI)

            if not NHSNEvent.objects.filter(candidate=candidate).exists():
                NHSNEvent.objects.create(
                    candidate=candidate,
                    event_date=candidate.culture_date.date() if candidate.culture_date else date.today(),
                    hai_type=hai_type,
                    location_code=candidate.patient_location or '',
                    pathogen_code=candidate.organism or '',
                )
                created_count += 1

        logger.info(f"Created {created_count} new NHSN events from {confirmed.count()} confirmed candidates")
        return created_count

    def get_unreported_events(self):
        """Get NHSNEvent records not yet submitted."""
        return NHSNEvent.objects.filter(reported=False).select_related('candidate')

    def mark_submitted(self, event_ids, user='system'):
        """Mark events as reported."""
        now = timezone.now()
        events = NHSNEvent.objects.filter(id__in=event_ids)
        count = events.update(reported=True, reported_at=now)

        # Also mark HAICandidates as NHSN reported
        for event in NHSNEvent.objects.filter(id__in=event_ids, candidate__isnull=False):
            event.candidate.nhsn_reported = True
            event.candidate.nhsn_reported_at = now
            event.candidate.save(update_fields=['nhsn_reported', 'nhsn_reported_at', 'updated_at'])

        self.log_submission('mark_submitted', 'hai', '', user, count)
        return count

    # ---- CDA Generation ----

    def generate_cda_documents(self, event_ids):
        """Generate CDA XML for selected events."""
        from .cda.generator import CDAGenerator, create_bsi_document_from_candidate

        facility_id = cfg.get_facility_id()
        facility_name = cfg.get_facility_name()

        if not facility_id:
            logger.warning("NHSN facility ID not configured")
            return []

        generator = CDAGenerator(facility_id, facility_name)
        events = NHSNEvent.objects.filter(id__in=event_ids).select_related('candidate')

        cda_docs = []
        for event in events:
            if event.candidate:
                bsi_doc = create_bsi_document_from_candidate(
                    event.candidate, facility_id, facility_name
                )
                cda_xml = generator.generate_bsi_document(bsi_doc)
                cda_docs.append(cda_xml)

        return cda_docs

    # ---- DIRECT Submission ----

    def submit_via_direct(self, event_ids, preparer='System'):
        """Submit events via DIRECT protocol and mark as reported."""
        from .direct.client import DirectClient, DirectConfig

        direct_cfg = cfg.get_direct_config()
        config = DirectConfig(**direct_cfg)

        if not config.is_configured():
            missing = config.get_missing_config()
            return {'success': False, 'error': f"DIRECT not configured: {', '.join(missing)}"}

        cda_docs = self.generate_cda_documents(event_ids)
        if not cda_docs:
            return {'success': False, 'error': 'No CDA documents generated'}

        client = DirectClient(config)
        result = client.submit_cda_documents(cda_docs, preparer_name=preparer)

        if result.success:
            self.mark_submitted(event_ids, preparer)
            self.log_submission('direct_submit', 'hai', '', preparer, result.documents_sent,
                                notes=f"Message-ID: {result.message_id}")

        return result.to_dict()

    def test_direct_connection(self):
        """Test DIRECT protocol connectivity."""
        from .direct.client import DirectClient, DirectConfig

        direct_cfg = cfg.get_direct_config()
        config = DirectConfig(**direct_cfg)
        client = DirectClient(config)
        return client.test_connection()

    # ---- CSV Export ----

    def export_csv(self, report_type, period=None, location=None):
        """Export data as CSV string."""
        import io
        import csv

        if report_type == 'au':
            return self._export_au_csv(period, location)
        elif report_type == 'ar':
            return self._export_ar_csv(period, location)
        elif report_type == 'hai':
            return self._export_hai_csv()
        elif report_type == 'denominators':
            return self._export_denominator_csv(period, location)
        return ''

    def _export_au_csv(self, period=None, location=None):
        """Export AU data as CSV."""
        import io
        import csv

        summaries = AUMonthlySummary.objects.all()
        if period:
            summaries = summaries.filter(reporting_month=period)
        if location:
            summaries = summaries.filter(location_code=location)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Month', 'Location', 'Antimicrobial', 'Class', 'Route', 'DOT', 'DDD', 'Patient Days'])

        for summary in summaries.prefetch_related('usage_records'):
            for usage in summary.usage_records.all():
                writer.writerow([
                    summary.reporting_month, summary.location_code,
                    usage.antimicrobial_name, usage.antimicrobial_class,
                    usage.route, usage.days_of_therapy, usage.defined_daily_doses or '',
                    summary.patient_days,
                ])

        return output.getvalue()

    def _export_ar_csv(self, period=None, location=None):
        """Export AR data as CSV."""
        import io
        import csv

        summaries = ARQuarterlySummary.objects.all()
        if period:
            summaries = summaries.filter(reporting_quarter=period)
        if location:
            summaries = summaries.filter(location_code=location)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Quarter', 'Location', 'Organism', 'Specimen Type', 'Antibiotic', 'Interpretation', 'MIC'])

        for summary in summaries.prefetch_related('isolates__susceptibilities'):
            for isolate in summary.isolates.all():
                for susc in isolate.susceptibilities.all():
                    writer.writerow([
                        summary.reporting_quarter, summary.location_code,
                        isolate.organism_name, isolate.specimen_type,
                        susc.antimicrobial_name, susc.interpretation, susc.mic_value,
                    ])

        return output.getvalue()

    def _export_hai_csv(self):
        """Export HAI events as CSV."""
        import io
        import csv

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Event Date', 'HAI Type', 'Location', 'Pathogen', 'Reported', 'Reported At'])

        for event in NHSNEvent.objects.all():
            writer.writerow([
                event.event_date, event.hai_type, event.location_code,
                event.pathogen_code, event.reported,
                event.reported_at.strftime('%Y-%m-%d %H:%M') if event.reported_at else '',
            ])

        return output.getvalue()

    def _export_denominator_csv(self, period=None, location=None):
        """Export denominator data as CSV."""
        import io
        import csv

        denoms = DenominatorMonthly.objects.all()
        if period:
            denoms = denoms.filter(month=period)
        if location:
            denoms = denoms.filter(location_code=location)

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            'Month', 'Location', 'Patient Days', 'Central Line Days',
            'Urinary Catheter Days', 'Ventilator Days',
            'CL Utilization', 'UC Utilization', 'Vent Utilization',
        ])

        for d in denoms:
            writer.writerow([
                d.month, d.location_code, d.patient_days,
                d.central_line_days, d.urinary_catheter_days, d.ventilator_days,
                d.central_line_utilization or '', d.urinary_catheter_utilization or '',
                d.ventilator_utilization or '',
            ])

        return output.getvalue()

    # ---- Statistics ----

    def get_stats(self):
        """Get summary statistics for the dashboard."""
        unreported_events = NHSNEvent.objects.filter(reported=False).count()
        reported_events = NHSNEvent.objects.filter(reported=True).count()
        total_events = unreported_events + reported_events

        au_summaries = AUMonthlySummary.objects.count()
        ar_summaries = ARQuarterlySummary.objects.count()
        denom_months = DenominatorMonthly.objects.count()

        latest_submission = SubmissionAudit.objects.filter(success=True).first()

        # HAI events by type
        from django.db.models import Count
        events_by_type = dict(
            NHSNEvent.objects.values_list('hai_type').annotate(count=Count('id'))
        )

        return {
            'total_events': total_events,
            'unreported_events': unreported_events,
            'reported_events': reported_events,
            'au_summaries': au_summaries,
            'ar_summaries': ar_summaries,
            'denominator_months': denom_months,
            'events_by_type': events_by_type,
            'latest_submission': {
                'action': latest_submission.action,
                'date': latest_submission.created_at.strftime('%Y-%m-%d %H:%M'),
                'type': latest_submission.submission_type,
            } if latest_submission else None,
        }

    # ---- Audit Logging ----

    def log_submission(self, action, submission_type, period, user, count, notes='', details=None):
        """Record a submission audit entry."""
        SubmissionAudit.objects.create(
            action=action,
            submission_type=submission_type,
            reporting_period=period,
            user=user,
            event_count=count,
            success=True,
            notes=notes,
            details=details or {},
        )
