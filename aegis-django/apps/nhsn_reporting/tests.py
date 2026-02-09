"""
Tests for NHSN Reporting module.

Tests cover:
- Model creation and properties (11 models)
- Enum values (4 TextChoices)
- Config helpers
- CDA document generation (XML structure)
- DIRECT client (config validation)
- Service layer (stats, event creation, CSV export, submission audit)
- Template rendering
- URL resolution
- Alert type integration
"""

from datetime import date, datetime, timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.urls import reverse, resolve
from django.utils import timezone
from django.template.loader import render_to_string

from apps.alerts.models import Alert, AlertType, AlertStatus, AlertSeverity

from .models import (
    NHSNEvent, DenominatorDaily, DenominatorMonthly,
    AUMonthlySummary, AUAntimicrobialUsage, AUPatientLevel,
    ARQuarterlySummary, ARIsolate, ARSusceptibility, ARPhenotypeSummary,
    SubmissionAudit,
    HAIEventType, AntimicrobialRoute, SusceptibilityResult, ResistancePhenotype,
)
from .services import NHSNReportingService
from .cda.generator import BSICDADocument, CDAGenerator, create_bsi_document_from_candidate
from .direct.client import DirectConfig, DirectSubmissionResult


# ============================================================================
# Alert Type Tests
# ============================================================================

class AlertTypeTests(TestCase):
    """Verify NHSN submission alert type exists."""

    def test_nhsn_submission_alert_type_exists(self):
        self.assertEqual(AlertType.NHSN_SUBMISSION, 'nhsn_submission')

    def test_create_nhsn_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.NHSN_SUBMISSION,
            source_module='nhsn_reporting',
            source_id='test-nhsn-1',
            title='NHSN Submission Failed',
            summary='DIRECT submission failed',
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.alert_type, 'nhsn_submission')
        self.assertEqual(alert.status, AlertStatus.PENDING)


# ============================================================================
# Enum Tests
# ============================================================================

class HAIEventTypeTests(TestCase):
    """Test HAIEventType enum."""

    def test_choices(self):
        self.assertEqual(HAIEventType.CLABSI, 'clabsi')
        self.assertEqual(HAIEventType.CAUTI, 'cauti')
        self.assertEqual(HAIEventType.SSI, 'ssi')
        self.assertEqual(HAIEventType.VAE, 'vae')

    def test_label(self):
        self.assertEqual(HAIEventType.CLABSI.label, 'CLABSI')

    def test_choices_count(self):
        self.assertEqual(len(HAIEventType.choices), 4)


class AntimicrobialRouteTests(TestCase):
    """Test AntimicrobialRoute enum."""

    def test_choices(self):
        self.assertEqual(AntimicrobialRoute.IV, 'IV')
        self.assertEqual(AntimicrobialRoute.PO, 'PO')
        self.assertEqual(AntimicrobialRoute.IM, 'IM')
        self.assertEqual(AntimicrobialRoute.TOPICAL, 'TOPICAL')
        self.assertEqual(AntimicrobialRoute.INHALED, 'INHALED')

    def test_choices_count(self):
        self.assertEqual(len(AntimicrobialRoute.choices), 5)


class SusceptibilityResultTests(TestCase):
    """Test SusceptibilityResult enum."""

    def test_choices(self):
        self.assertEqual(SusceptibilityResult.SUSCEPTIBLE, 'S')
        self.assertEqual(SusceptibilityResult.INTERMEDIATE, 'I')
        self.assertEqual(SusceptibilityResult.RESISTANT, 'R')
        self.assertEqual(SusceptibilityResult.NON_SUSCEPTIBLE, 'NS')

    def test_label(self):
        self.assertEqual(SusceptibilityResult.SUSCEPTIBLE.label, 'Susceptible')
        self.assertEqual(SusceptibilityResult.RESISTANT.label, 'Resistant')

    def test_choices_count(self):
        self.assertEqual(len(SusceptibilityResult.choices), 4)


class ResistancePhenotypeTests(TestCase):
    """Test ResistancePhenotype enum."""

    def test_choices(self):
        self.assertEqual(ResistancePhenotype.MRSA, 'MRSA')
        self.assertEqual(ResistancePhenotype.VRE, 'VRE')
        self.assertEqual(ResistancePhenotype.ESBL, 'ESBL')
        self.assertEqual(ResistancePhenotype.CRE, 'CRE')
        self.assertEqual(ResistancePhenotype.CRPA, 'CRPA')
        self.assertEqual(ResistancePhenotype.CRAB, 'CRAB')
        self.assertEqual(ResistancePhenotype.MDR, 'MDR')

    def test_label(self):
        self.assertEqual(ResistancePhenotype.MRSA.label, 'Methicillin-resistant S. aureus')

    def test_choices_count(self):
        self.assertEqual(len(ResistancePhenotype.choices), 9)


# ============================================================================
# Model Tests
# ============================================================================

class NHSNEventModelTests(TestCase):
    """Test NHSNEvent model."""

    def test_create_event(self):
        event = NHSNEvent.objects.create(
            event_date=date.today(),
            hai_type=HAIEventType.CLABSI,
            location_code='G3-PICU',
            pathogen_code='Staphylococcus aureus',
        )
        self.assertIsNotNone(event.id)
        self.assertFalse(event.reported)
        self.assertIsNone(event.reported_at)
        self.assertIsNone(event.candidate)

    def test_str_pending(self):
        event = NHSNEvent.objects.create(
            event_date=date(2026, 1, 15),
            hai_type=HAIEventType.CLABSI,
        )
        self.assertIn('CLABSI', str(event))
        self.assertIn('Pending', str(event))

    def test_str_reported(self):
        event = NHSNEvent.objects.create(
            event_date=date(2026, 1, 15),
            hai_type=HAIEventType.CAUTI,
            reported=True,
            reported_at=timezone.now(),
        )
        self.assertIn('CAUTI', str(event))
        self.assertIn('Reported', str(event))

    def test_ordering(self):
        e1 = NHSNEvent.objects.create(event_date=date(2026, 1, 1), hai_type=HAIEventType.CLABSI)
        e2 = NHSNEvent.objects.create(event_date=date(2026, 2, 1), hai_type=HAIEventType.CAUTI)
        events = list(NHSNEvent.objects.all())
        self.assertEqual(events[0], e2)  # Most recent first


class DenominatorDailyModelTests(TestCase):
    """Test DenominatorDaily model."""

    def test_create_daily(self):
        daily = DenominatorDaily.objects.create(
            date=date.today(),
            location_code='G3-PICU',
            location_type='ICU',
            patient_days=25,
            central_line_days=15,
            ventilator_days=10,
        )
        self.assertEqual(daily.patient_days, 25)
        self.assertEqual(daily.central_line_days, 15)

    def test_unique_together(self):
        DenominatorDaily.objects.create(
            date=date.today(),
            location_code='G3-PICU',
            patient_days=25,
        )
        with self.assertRaises(Exception):
            DenominatorDaily.objects.create(
                date=date.today(),
                location_code='G3-PICU',
                patient_days=30,
            )

    def test_str(self):
        daily = DenominatorDaily.objects.create(
            date=date(2026, 1, 15),
            location_code='G3-PICU',
            patient_days=25,
        )
        self.assertIn('G3-PICU', str(daily))
        self.assertIn('25', str(daily))


class DenominatorMonthlyModelTests(TestCase):
    """Test DenominatorMonthly model with utilization calculation."""

    def test_create_monthly(self):
        monthly = DenominatorMonthly.objects.create(
            month='2026-01',
            location_code='G3-PICU',
            location_type='ICU',
            patient_days=500,
            central_line_days=250,
            urinary_catheter_days=100,
            ventilator_days=200,
            admissions=45,
        )
        self.assertEqual(monthly.patient_days, 500)
        self.assertIsNone(monthly.central_line_utilization)

    def test_calculate_utilization(self):
        monthly = DenominatorMonthly.objects.create(
            month='2026-01',
            location_code='G3-PICU',
            patient_days=500,
            central_line_days=250,
            urinary_catheter_days=100,
            ventilator_days=200,
        )
        monthly.calculate_utilization()
        self.assertAlmostEqual(monthly.central_line_utilization, 0.5)
        self.assertAlmostEqual(monthly.urinary_catheter_utilization, 0.2)
        self.assertAlmostEqual(monthly.ventilator_utilization, 0.4)

    def test_calculate_utilization_zero_patient_days(self):
        monthly = DenominatorMonthly.objects.create(
            month='2026-01',
            location_code='G3-PICU',
            patient_days=0,
            central_line_days=0,
        )
        monthly.calculate_utilization()
        self.assertIsNone(monthly.central_line_utilization)

    def test_unique_together(self):
        DenominatorMonthly.objects.create(month='2026-01', location_code='G3-PICU')
        with self.assertRaises(Exception):
            DenominatorMonthly.objects.create(month='2026-01', location_code='G3-PICU')


class AUMonthlySummaryModelTests(TestCase):
    """Test AU monthly summary model."""

    def test_create_summary(self):
        summary = AUMonthlySummary.objects.create(
            reporting_month='2026-01',
            location_code='G3-PICU',
            location_type='ICU',
            patient_days=500,
            admissions=45,
        )
        self.assertEqual(summary.patient_days, 500)
        self.assertIsNone(summary.submitted_at)

    def test_unique_together(self):
        AUMonthlySummary.objects.create(reporting_month='2026-01', location_code='G3-PICU')
        with self.assertRaises(Exception):
            AUMonthlySummary.objects.create(reporting_month='2026-01', location_code='G3-PICU')

    def test_str(self):
        summary = AUMonthlySummary.objects.create(
            reporting_month='2026-01',
            location_code='G3-PICU',
        )
        self.assertIn('AU', str(summary))
        self.assertIn('G3-PICU', str(summary))


class AUAntimicrobialUsageModelTests(TestCase):
    """Test AU antimicrobial usage model."""

    def test_create_usage(self):
        summary = AUMonthlySummary.objects.create(
            reporting_month='2026-01',
            location_code='G3-PICU',
            patient_days=500,
        )
        usage = AUAntimicrobialUsage.objects.create(
            summary=summary,
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
            antimicrobial_class='Glycopeptides',
            route=AntimicrobialRoute.IV,
            days_of_therapy=45.0,
            defined_daily_doses=42.5,
            doses_administered=90,
            patients_treated=12,
        )
        self.assertEqual(usage.antimicrobial_name, 'Vancomycin')
        self.assertEqual(usage.route, 'IV')

    def test_cascade_delete(self):
        summary = AUMonthlySummary.objects.create(
            reporting_month='2026-01',
            location_code='G3-PICU',
        )
        AUAntimicrobialUsage.objects.create(
            summary=summary,
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
        )
        self.assertEqual(AUAntimicrobialUsage.objects.count(), 1)
        summary.delete()
        self.assertEqual(AUAntimicrobialUsage.objects.count(), 0)

    def test_related_name(self):
        summary = AUMonthlySummary.objects.create(
            reporting_month='2026-01',
            location_code='G3-PICU',
        )
        AUAntimicrobialUsage.objects.create(
            summary=summary,
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
        )
        self.assertEqual(summary.usage_records.count(), 1)


class AUPatientLevelModelTests(TestCase):
    """Test AU patient-level model."""

    def test_create_patient_level(self):
        record = AUPatientLevel.objects.create(
            patient_id='FHIR-001',
            patient_mrn='MRN123',
            encounter_id='ENC-001',
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
            route=AntimicrobialRoute.IV,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 7),
            total_doses=14,
            days_of_therapy=7.0,
            location_code='G3-PICU',
        )
        self.assertEqual(record.days_of_therapy, 7.0)
        self.assertIn('MRN123', str(record))


class ARQuarterlySummaryModelTests(TestCase):
    """Test AR quarterly summary model."""

    def test_create_summary(self):
        summary = ARQuarterlySummary.objects.create(
            reporting_quarter='2026-Q1',
            location_code='G3-PICU',
            location_type='ICU',
        )
        self.assertIsNotNone(summary.id)
        self.assertIsNone(summary.submitted_at)

    def test_unique_together(self):
        ARQuarterlySummary.objects.create(reporting_quarter='2026-Q1', location_code='G3-PICU')
        with self.assertRaises(Exception):
            ARQuarterlySummary.objects.create(reporting_quarter='2026-Q1', location_code='G3-PICU')

    def test_str(self):
        summary = ARQuarterlySummary.objects.create(
            reporting_quarter='2026-Q1',
            location_code='G3-PICU',
        )
        self.assertIn('AR', str(summary))
        self.assertIn('G3-PICU', str(summary))


class ARIsolateModelTests(TestCase):
    """Test AR isolate model."""

    def setUp(self):
        self.summary = ARQuarterlySummary.objects.create(
            reporting_quarter='2026-Q1',
            location_code='G3-PICU',
        )

    def test_create_isolate(self):
        isolate = ARIsolate.objects.create(
            summary=self.summary,
            patient_id='FHIR-001',
            patient_mrn='MRN123',
            encounter_id='ENC-001',
            specimen_date=date(2026, 1, 15),
            specimen_type='Blood',
            organism_code='SA',
            organism_name='Staphylococcus aureus',
            location_code='G3-PICU',
        )
        self.assertTrue(isolate.is_first_isolate)
        self.assertFalse(isolate.is_hai_associated)
        self.assertIsNone(isolate.hai_event)

    def test_related_name(self):
        ARIsolate.objects.create(
            summary=self.summary,
            patient_id='FHIR-001',
            patient_mrn='MRN123',
            encounter_id='ENC-001',
            specimen_date=date(2026, 1, 15),
            specimen_type='Blood',
            organism_code='SA',
            organism_name='Staphylococcus aureus',
        )
        self.assertEqual(self.summary.isolates.count(), 1)


class ARSusceptibilityModelTests(TestCase):
    """Test AR susceptibility model."""

    def setUp(self):
        self.summary = ARQuarterlySummary.objects.create(
            reporting_quarter='2026-Q1',
            location_code='G3-PICU',
        )
        self.isolate = ARIsolate.objects.create(
            summary=self.summary,
            patient_id='FHIR-001',
            patient_mrn='MRN123',
            encounter_id='ENC-001',
            specimen_date=date(2026, 1, 15),
            specimen_type='Blood',
            organism_code='SA',
            organism_name='Staphylococcus aureus',
        )

    def test_create_susceptibility(self):
        susc = ARSusceptibility.objects.create(
            isolate=self.isolate,
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
            interpretation=SusceptibilityResult.SUSCEPTIBLE,
            mic_value='<=0.5',
            testing_method='MIC',
            breakpoint_source='CLSI',
        )
        self.assertEqual(susc.interpretation, 'S')

    def test_cascade_delete(self):
        ARSusceptibility.objects.create(
            isolate=self.isolate,
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
            interpretation=SusceptibilityResult.RESISTANT,
        )
        self.assertEqual(ARSusceptibility.objects.count(), 1)
        self.isolate.delete()
        self.assertEqual(ARSusceptibility.objects.count(), 0)

    def test_related_name(self):
        ARSusceptibility.objects.create(
            isolate=self.isolate,
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
            interpretation=SusceptibilityResult.SUSCEPTIBLE,
        )
        self.assertEqual(self.isolate.susceptibilities.count(), 1)


class ARPhenotypeSummaryModelTests(TestCase):
    """Test AR phenotype summary with percentage calculation."""

    def setUp(self):
        self.summary = ARQuarterlySummary.objects.create(
            reporting_quarter='2026-Q1',
            location_code='G3-PICU',
        )

    def test_create_phenotype_summary(self):
        pheno = ARPhenotypeSummary.objects.create(
            summary=self.summary,
            organism_code='SA',
            organism_name='Staphylococcus aureus',
            phenotype=ResistancePhenotype.MRSA,
            total_isolates=20,
            resistant_isolates=8,
        )
        self.assertIsNone(pheno.percent_resistant)

    def test_calculate_percent(self):
        pheno = ARPhenotypeSummary.objects.create(
            summary=self.summary,
            organism_code='SA',
            organism_name='Staphylococcus aureus',
            phenotype=ResistancePhenotype.MRSA,
            total_isolates=20,
            resistant_isolates=8,
        )
        pheno.calculate_percent()
        self.assertAlmostEqual(pheno.percent_resistant, 40.0)

    def test_calculate_percent_zero_isolates(self):
        pheno = ARPhenotypeSummary.objects.create(
            summary=self.summary,
            organism_code='SA',
            organism_name='Staphylococcus aureus',
            phenotype=ResistancePhenotype.MRSA,
            total_isolates=0,
            resistant_isolates=0,
        )
        pheno.calculate_percent()
        self.assertIsNone(pheno.percent_resistant)

    def test_related_name(self):
        ARPhenotypeSummary.objects.create(
            summary=self.summary,
            organism_code='SA',
            organism_name='Staphylococcus aureus',
            phenotype=ResistancePhenotype.MRSA,
            total_isolates=20,
            resistant_isolates=8,
        )
        self.assertEqual(self.summary.phenotypes.count(), 1)


class SubmissionAuditModelTests(TestCase):
    """Test SubmissionAudit model."""

    def test_create_audit(self):
        audit = SubmissionAudit.objects.create(
            action='csv_export',
            submission_type='au',
            reporting_period='2026-01',
            user='test_user',
            event_count=10,
            success=True,
            notes='Test export',
        )
        self.assertTrue(audit.success)
        self.assertEqual(audit.event_count, 10)

    def test_str_success(self):
        audit = SubmissionAudit.objects.create(
            action='direct_submit',
            submission_type='hai',
            reporting_period='2026-01',
            user='test_user',
            success=True,
        )
        self.assertIn('OK', str(audit))

    def test_str_failure(self):
        audit = SubmissionAudit.objects.create(
            action='direct_submit',
            submission_type='hai',
            reporting_period='2026-01',
            user='test_user',
            success=False,
        )
        self.assertIn('FAIL', str(audit))

    def test_details_jsonfield(self):
        audit = SubmissionAudit.objects.create(
            action='direct_submit',
            submission_type='hai',
            reporting_period='2026-01',
            user='test_user',
            details={'message_id': 'abc-123', 'documents': 3},
        )
        self.assertEqual(audit.details['message_id'], 'abc-123')

    def test_ordering(self):
        a1 = SubmissionAudit.objects.create(action='a', submission_type='au', reporting_period='', user='u')
        a2 = SubmissionAudit.objects.create(action='b', submission_type='au', reporting_period='', user='u')
        audits = list(SubmissionAudit.objects.all())
        self.assertEqual(audits[0], a2)  # Most recent first


# ============================================================================
# Config Tests
# ============================================================================

class ConfigTests(TestCase):
    """Test NHSN config helpers."""

    def test_get_config(self):
        from .logic import config as cfg
        config = cfg.get_config()
        self.assertIsInstance(config, dict)

    def test_is_clarity_configured_default(self):
        from .logic import config as cfg
        # Default is not configured (no Clarity URL set)
        result = cfg.is_clarity_configured()
        self.assertIsInstance(result, bool)

    def test_get_facility_id(self):
        from .logic import config as cfg
        facility_id = cfg.get_facility_id()
        self.assertIsInstance(facility_id, str)

    def test_get_facility_name(self):
        from .logic import config as cfg
        name = cfg.get_facility_name()
        self.assertIsInstance(name, str)

    def test_get_au_location_types(self):
        from .logic import config as cfg
        types = cfg.get_au_location_types()
        self.assertIsInstance(types, list)
        self.assertIn('ICU', types)

    def test_get_ar_specimen_types(self):
        from .logic import config as cfg
        types = cfg.get_ar_specimen_types()
        self.assertIn('Blood', types)

    def test_get_ar_first_isolate_only(self):
        from .logic import config as cfg
        result = cfg.get_ar_first_isolate_only()
        self.assertTrue(result)

    def test_is_direct_configured_default(self):
        from .logic import config as cfg
        # Default is not configured
        self.assertFalse(cfg.is_direct_configured())

    def test_get_direct_config(self):
        from .logic import config as cfg
        direct = cfg.get_direct_config()
        self.assertIn('hisp_smtp_server', direct)
        self.assertIn('hisp_smtp_port', direct)
        self.assertIn('sender_direct_address', direct)


# ============================================================================
# CDA Generator Tests
# ============================================================================

class BSICDADocumentTests(TestCase):
    """Test BSICDADocument dataclass."""

    def test_create_defaults(self):
        doc = BSICDADocument()
        self.assertIsNotNone(doc.document_id)
        self.assertIsNotNone(doc.creation_time)
        self.assertTrue(doc.is_clabsi)
        self.assertEqual(doc.event_type, 'clabsi')

    def test_create_with_data(self):
        doc = BSICDADocument(
            facility_id='CCHMC001',
            facility_name="Cincinnati Children's",
            patient_mrn='MRN123',
            patient_name='Test Patient',
            event_date=date(2026, 1, 15),
            organism='Staphylococcus aureus',
        )
        self.assertEqual(doc.facility_id, 'CCHMC001')
        self.assertEqual(doc.organism, 'Staphylococcus aureus')


class CDAGeneratorTests(TestCase):
    """Test CDA XML document generation."""

    def setUp(self):
        self.generator = CDAGenerator('CCHMC001', "Cincinnati Children's")

    def test_generate_bsi_document(self):
        doc = BSICDADocument(
            facility_id='CCHMC001',
            facility_name="Cincinnati Children's",
            patient_mrn='MRN123',
            patient_name='John Smith',
            event_date=date(2026, 1, 15),
            event_type='clabsi',
            organism='Staphylococcus aureus',
            location_code='G3-PICU',
        )
        xml = self.generator.generate_bsi_document(doc)
        self.assertIn('ClinicalDocument', xml)
        self.assertIn('BSI Event Report', xml)
        self.assertIn('MRN123', xml)

    def test_xml_contains_patient_name(self):
        doc = BSICDADocument(
            patient_mrn='MRN123',
            patient_name='Jane Doe',
            event_date=date(2026, 1, 15),
        )
        xml = self.generator.generate_bsi_document(doc)
        self.assertIn('Jane', xml)
        self.assertIn('Doe', xml)

    def test_xml_contains_organism(self):
        doc = BSICDADocument(
            patient_mrn='MRN123',
            event_date=date(2026, 1, 15),
            organism='Escherichia coli',
        )
        xml = self.generator.generate_bsi_document(doc)
        self.assertIn('Escherichia coli', xml)

    def test_xml_contains_location(self):
        doc = BSICDADocument(
            patient_mrn='MRN123',
            event_date=date(2026, 1, 15),
            location_code='G3-PICU',
        )
        xml = self.generator.generate_bsi_document(doc)
        self.assertIn('G3-PICU', xml)

    def test_xml_contains_loinc(self):
        doc = BSICDADocument(
            patient_mrn='MRN123',
            event_date=date(2026, 1, 15),
        )
        xml = self.generator.generate_bsi_document(doc)
        self.assertIn('2.16.840.1.113883.6.1', xml)  # LOINC OID

    def test_generate_batch(self):
        docs = [
            BSICDADocument(patient_mrn=f'MRN{i}', event_date=date(2026, 1, i + 1))
            for i in range(3)
        ]
        results = self.generator.generate_batch(docs)
        self.assertEqual(len(results), 3)
        for xml in results:
            self.assertIn('ClinicalDocument', xml)


# ============================================================================
# DIRECT Client Tests
# ============================================================================

class DirectConfigTests(TestCase):
    """Test DirectConfig dataclass."""

    def test_not_configured_by_default(self):
        config = DirectConfig()
        self.assertFalse(config.is_configured())

    def test_configured_when_all_set(self):
        config = DirectConfig(
            hisp_smtp_server='smtp.hisp.example.com',
            hisp_smtp_username='user',
            hisp_smtp_password='pass',
            sender_direct_address='sender@hisp.example.com',
            nhsn_direct_address='nhsn@cdc.gov',
        )
        self.assertTrue(config.is_configured())

    def test_missing_config(self):
        config = DirectConfig(hisp_smtp_server='smtp.example.com')
        missing = config.get_missing_config()
        self.assertIn('HISP SMTP username', missing)
        self.assertIn('HISP SMTP password', missing)
        self.assertIn('Sender DIRECT address', missing)
        self.assertIn('NHSN DIRECT address', missing)
        self.assertNotIn('HISP SMTP server', missing)


class DirectSubmissionResultTests(TestCase):
    """Test DirectSubmissionResult dataclass."""

    def test_default_failure(self):
        result = DirectSubmissionResult()
        self.assertFalse(result.success)
        self.assertEqual(result.documents_sent, 0)

    def test_to_dict(self):
        result = DirectSubmissionResult(
            success=True,
            message_id='msg-123',
            documents_sent=3,
        )
        d = result.to_dict()
        self.assertTrue(d['success'])
        self.assertEqual(d['message_id'], 'msg-123')
        self.assertEqual(d['documents_sent'], 3)
        self.assertIn('timestamp', d)


# ============================================================================
# Service Tests
# ============================================================================

class NHSNServiceStatsTests(TestCase):
    """Test NHSNReportingService.get_stats()."""

    def setUp(self):
        self.service = NHSNReportingService()
        # Create sample data
        NHSNEvent.objects.create(event_date=date.today(), hai_type=HAIEventType.CLABSI, reported=False)
        NHSNEvent.objects.create(event_date=date.today(), hai_type=HAIEventType.CAUTI, reported=True, reported_at=timezone.now())
        AUMonthlySummary.objects.create(reporting_month='2026-01', location_code='G3-PICU')
        ARQuarterlySummary.objects.create(reporting_quarter='2026-Q1', location_code='G3-PICU')
        DenominatorMonthly.objects.create(month='2026-01', location_code='G3-PICU')
        SubmissionAudit.objects.create(
            action='csv_export', submission_type='au', reporting_period='2026-01', user='test',
        )

    def test_stats_counts(self):
        stats = self.service.get_stats()
        self.assertEqual(stats['total_events'], 2)
        self.assertEqual(stats['unreported_events'], 1)
        self.assertEqual(stats['reported_events'], 1)
        self.assertEqual(stats['au_summaries'], 1)
        self.assertEqual(stats['ar_summaries'], 1)
        self.assertEqual(stats['denominator_months'], 1)

    def test_stats_events_by_type(self):
        stats = self.service.get_stats()
        self.assertIn('clabsi', stats['events_by_type'])

    def test_stats_latest_submission(self):
        stats = self.service.get_stats()
        self.assertIsNotNone(stats['latest_submission'])
        self.assertEqual(stats['latest_submission']['action'], 'csv_export')


class NHSNServiceMarkSubmittedTests(TestCase):
    """Test NHSNReportingService.mark_submitted()."""

    def setUp(self):
        self.service = NHSNReportingService()

    def test_mark_submitted(self):
        e1 = NHSNEvent.objects.create(event_date=date.today(), hai_type=HAIEventType.CLABSI)
        e2 = NHSNEvent.objects.create(event_date=date.today(), hai_type=HAIEventType.CAUTI)
        count = self.service.mark_submitted([e1.id, e2.id], 'test_user')
        self.assertEqual(count, 2)
        e1.refresh_from_db()
        e2.refresh_from_db()
        self.assertTrue(e1.reported)
        self.assertTrue(e2.reported)
        self.assertIsNotNone(e1.reported_at)

    def test_mark_submitted_creates_audit(self):
        e1 = NHSNEvent.objects.create(event_date=date.today(), hai_type=HAIEventType.CLABSI)
        self.service.mark_submitted([e1.id], 'test_user')
        audit = SubmissionAudit.objects.first()
        self.assertEqual(audit.action, 'mark_submitted')
        self.assertEqual(audit.user, 'test_user')


class NHSNServiceCSVExportTests(TestCase):
    """Test NHSNReportingService CSV export."""

    def setUp(self):
        self.service = NHSNReportingService()
        # AU data
        summary = AUMonthlySummary.objects.create(
            reporting_month='2026-01',
            location_code='G3-PICU',
            patient_days=500,
        )
        AUAntimicrobialUsage.objects.create(
            summary=summary,
            antimicrobial_code='VAN',
            antimicrobial_name='Vancomycin',
            antimicrobial_class='Glycopeptides',
            route=AntimicrobialRoute.IV,
            days_of_therapy=45.0,
        )
        # HAI event
        NHSNEvent.objects.create(
            event_date=date(2026, 1, 15),
            hai_type=HAIEventType.CLABSI,
            location_code='G3-PICU',
            pathogen_code='Staphylococcus aureus',
        )

    def test_export_au_csv(self):
        csv_data = self.service.export_csv('au')
        self.assertIn('Vancomycin', csv_data)
        self.assertIn('Glycopeptides', csv_data)
        self.assertIn('DOT', csv_data)

    def test_export_au_csv_with_filter(self):
        csv_data = self.service.export_csv('au', period='2026-01')
        self.assertIn('Vancomycin', csv_data)

    def test_export_hai_csv(self):
        csv_data = self.service.export_csv('hai')
        self.assertIn('clabsi', csv_data)
        self.assertIn('Staphylococcus aureus', csv_data)

    def test_export_denominator_csv(self):
        DenominatorMonthly.objects.create(
            month='2026-01',
            location_code='G3-PICU',
            patient_days=500,
            central_line_days=250,
        )
        csv_data = self.service.export_csv('denominators')
        self.assertIn('G3-PICU', csv_data)
        self.assertIn('500', csv_data)


class NHSNServiceLogSubmissionTests(TestCase):
    """Test NHSNReportingService audit logging."""

    def test_log_submission(self):
        service = NHSNReportingService()
        service.log_submission('csv_export', 'au', '2026-01', 'test_user', 10, notes='Test')
        audit = SubmissionAudit.objects.first()
        self.assertEqual(audit.action, 'csv_export')
        self.assertEqual(audit.submission_type, 'au')
        self.assertEqual(audit.reporting_period, '2026-01')
        self.assertEqual(audit.user, 'test_user')
        self.assertEqual(audit.event_count, 10)


# ============================================================================
# Template Tests
# ============================================================================

class TemplateRenderTests(TestCase):
    """Test template rendering (render_to_string avoids UserSession NOT NULL)."""

    def test_base_template(self):
        html = render_to_string('nhsn_reporting/base.html', {})
        self.assertIn('NHSN', html)

    def test_dashboard_template(self):
        html = render_to_string('nhsn_reporting/dashboard.html', {
            'stats': {
                'total_events': 5,
                'unreported_events': 2,
                'reported_events': 3,
                'au_summaries': 10,
                'ar_summaries': 4,
                'denominator_months': 12,
                'events_by_type': {'clabsi': 3, 'cauti': 2},
                'latest_submission': None,
            },
            'recent_submissions': [],
            'clarity_configured': False,
            'direct_configured': False,
        })
        self.assertIn('Dashboard', html)

    def test_au_detail_template(self):
        html = render_to_string('nhsn_reporting/au_detail.html', {
            'summaries': [],
            'months': [],
            'locations': [],
            'month_filter': '',
            'location_filter': '',
        })
        self.assertIn('Antimicrobial', html)

    def test_ar_detail_template(self):
        html = render_to_string('nhsn_reporting/ar_detail.html', {
            'summaries': [],
            'quarters': [],
            'locations': [],
            'quarter_filter': '',
            'location_filter': '',
        })
        self.assertIn('Resistance', html)

    def test_hai_events_template(self):
        html = render_to_string('nhsn_reporting/hai_events.html', {
            'events': [],
            'status_filter': '',
            'unreported_count': 0,
            'reported_count': 0,
        })
        self.assertIn('HAI', html)

    def test_denominators_template(self):
        html = render_to_string('nhsn_reporting/denominators.html', {
            'denominators': [],
            'months': [],
            'locations': [],
            'month_filter': '',
            'location_filter': '',
        })
        self.assertIn('Denominator', html)

    def test_submission_template(self):
        html = render_to_string('nhsn_reporting/submission.html', {
            'audit_log': [],
            'unreported_events': [],
            'unreported_count': 0,
            'direct_configured': False,
        })
        self.assertIn('Submission', html)

    def test_help_template(self):
        html = render_to_string('nhsn_reporting/help.html', {})
        self.assertIn('NHSN', html)


# ============================================================================
# URL Tests
# ============================================================================

class URLTests(TestCase):
    """Test URL resolution."""

    def test_dashboard_url(self):
        url = reverse('nhsn_reporting:dashboard')
        self.assertEqual(url, '/nhsn-reporting/')

    def test_au_detail_url(self):
        url = reverse('nhsn_reporting:au_detail')
        self.assertEqual(url, '/nhsn-reporting/au/')

    def test_ar_detail_url(self):
        url = reverse('nhsn_reporting:ar_detail')
        self.assertEqual(url, '/nhsn-reporting/ar/')

    def test_hai_events_url(self):
        url = reverse('nhsn_reporting:hai_events')
        self.assertEqual(url, '/nhsn-reporting/hai/')

    def test_denominators_url(self):
        url = reverse('nhsn_reporting:denominators')
        self.assertEqual(url, '/nhsn-reporting/denominators/')

    def test_submission_url(self):
        url = reverse('nhsn_reporting:submission')
        self.assertEqual(url, '/nhsn-reporting/submission/')

    def test_help_url(self):
        url = reverse('nhsn_reporting:help')
        self.assertEqual(url, '/nhsn-reporting/help/')

    def test_api_stats_url(self):
        url = reverse('nhsn_reporting:api_stats')
        self.assertEqual(url, '/nhsn-reporting/api/stats/')

    def test_api_au_export_url(self):
        url = reverse('nhsn_reporting:api_au_export')
        self.assertEqual(url, '/nhsn-reporting/api/au/export/')

    def test_api_ar_export_url(self):
        url = reverse('nhsn_reporting:api_ar_export')
        self.assertEqual(url, '/nhsn-reporting/api/ar/export/')

    def test_api_hai_export_url(self):
        url = reverse('nhsn_reporting:api_hai_export')
        self.assertEqual(url, '/nhsn-reporting/api/hai/export/')

    def test_api_mark_submitted_url(self):
        url = reverse('nhsn_reporting:api_mark_submitted')
        self.assertEqual(url, '/nhsn-reporting/api/hai/mark-submitted/')

    def test_api_direct_submit_url(self):
        url = reverse('nhsn_reporting:api_direct_submit')
        self.assertEqual(url, '/nhsn-reporting/api/hai/direct/')

    def test_api_test_direct_url(self):
        url = reverse('nhsn_reporting:api_test_direct')
        self.assertEqual(url, '/nhsn-reporting/api/hai/test-direct/')

    def test_dashboard_resolves_to_view(self):
        match = resolve('/nhsn-reporting/')
        self.assertEqual(match.func.__name__, 'dashboard')

    def test_au_resolves_to_view(self):
        match = resolve('/nhsn-reporting/au/')
        self.assertEqual(match.func.__name__, 'au_detail')
