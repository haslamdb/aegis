"""
Tests for Antimicrobial Usage Alerts module.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from django.template.loader import render_to_string

from apps.alerts.models import Alert, AlertType, AlertStatus, AlertSeverity

from .data_models import Patient, MedicationOrder, UsageAssessment
from .services import BroadSpectrumMonitorService


class DataModelTests(TestCase):
    """Test data model dataclasses."""

    def test_medication_order_duration(self):
        """MedicationOrder.duration_hours calculates from start_date."""
        start = timezone.now() - timedelta(hours=96)
        order = MedicationOrder(
            fhir_id='test-1',
            patient_id='P-1',
            medication_name='Meropenem',
            start_date=start,
        )
        self.assertAlmostEqual(order.duration_hours, 96.0, delta=0.1)
        self.assertAlmostEqual(order.duration_days, 4.0, delta=0.01)

    def test_medication_order_no_start_date(self):
        """MedicationOrder.duration_hours returns None without start_date."""
        order = MedicationOrder(
            fhir_id='test-2',
            patient_id='P-1',
            medication_name='Vancomycin',
        )
        self.assertIsNone(order.duration_hours)
        self.assertIsNone(order.duration_days)


class ServiceStatsTests(TestCase):
    """Test BroadSpectrumMonitorService.get_stats()."""

    def setUp(self):
        """Create test alerts."""
        Alert.objects.create(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            source_module='antimicrobial_usage',
            source_id='test-1',
            title='Test Alert 1',
            summary='Meropenem > 72h',
            details={'medication_name': 'Meropenem', 'duration_hours': 96},
            severity=AlertSeverity.HIGH,
            status=AlertStatus.PENDING,
        )
        Alert.objects.create(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            source_module='antimicrobial_usage',
            source_id='test-2',
            title='Test Alert 2',
            summary='Vancomycin > 144h',
            details={'medication_name': 'Vancomycin', 'duration_hours': 168},
            severity=AlertSeverity.CRITICAL,
            status=AlertStatus.PENDING,
        )
        Alert.objects.create(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            source_module='antimicrobial_usage',
            source_id='test-3',
            title='Test Alert 3',
            summary='Resolved',
            details={'medication_name': 'Meropenem', 'duration_hours': 80},
            severity=AlertSeverity.HIGH,
            status=AlertStatus.RESOLVED,
            resolved_at=timezone.now(),
        )

    def test_get_stats(self):
        """get_stats returns correct counts."""
        service = BroadSpectrumMonitorService.__new__(BroadSpectrumMonitorService)
        service.threshold_hours = 72
        stats = service.get_stats()

        self.assertEqual(stats['active_count'], 2)
        self.assertEqual(stats['critical_count'], 1)
        self.assertEqual(stats['high_count'], 1)
        self.assertEqual(stats['resolved_today'], 1)
        self.assertIn('Meropenem', stats['by_medication'])
        self.assertIn('Vancomycin', stats['by_medication'])


class TemplateRenderTests(TestCase):
    """Test that templates render without errors."""

    def test_base_template(self):
        html = render_to_string('antimicrobial_usage/base.html')
        self.assertIn('Antimicrobial Usage Alerts', html)
        self.assertIn('#00796B', html)

    def test_help_template(self):
        html = render_to_string('antimicrobial_usage/help.html')
        self.assertIn('Meropenem', html)
        self.assertIn('Vancomycin', html)
        self.assertIn('72 hours', html)
        self.assertIn('144 hours', html)
        self.assertIn('De-escalation', html)


class AlertTypeTests(TestCase):
    """Verify BROAD_SPECTRUM_USAGE alert type exists."""

    def test_alert_type_exists(self):
        self.assertEqual(AlertType.BROAD_SPECTRUM_USAGE, 'broad_spectrum_usage')

    def test_create_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            source_module='antimicrobial_usage',
            source_id='test-create',
            title='Test',
            summary='Test alert',
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.alert_type, 'broad_spectrum_usage')
        self.assertEqual(alert.get_alert_type_display(), 'Broad Spectrum Usage')


# ===========================================================================
# Additional tests - expand beyond existing 7
# ===========================================================================

class PatientDataModelTests(TestCase):
    """Test Patient dataclass."""

    def test_patient_basic_fields(self):
        patient = Patient(
            fhir_id='P-1', mrn='MRN-1', name='Test Patient',
        )
        self.assertEqual(patient.fhir_id, 'P-1')
        self.assertIsNone(patient.location)

    def test_patient_all_fields(self):
        patient = Patient(
            fhir_id='P-1', mrn='MRN-1', name='Test Patient',
            birth_date='2020-01-01', gender='female',
            location='PICU G3', department='Critical Care',
        )
        self.assertEqual(patient.location, 'PICU G3')
        self.assertEqual(patient.department, 'Critical Care')


class UsageAssessmentDataModelTests(TestCase):
    """Test UsageAssessment dataclass."""

    def test_usage_assessment_creation(self):
        patient = Patient(fhir_id='P-1', mrn='MRN-1', name='Test')
        order = MedicationOrder(
            fhir_id='MR-1', patient_id='P-1',
            medication_name='Meropenem',
            start_date=timezone.now() - timedelta(hours=96),
        )
        assessment = UsageAssessment(
            patient=patient,
            medication=order,
            duration_hours=96.0,
            threshold_hours=72.0,
            exceeds_threshold=True,
            recommendation='Consider de-escalation',
        )
        self.assertTrue(assessment.exceeds_threshold)
        self.assertEqual(assessment.severity, 'high')

    def test_usage_assessment_below_threshold(self):
        patient = Patient(fhir_id='P-1', mrn='MRN-1', name='Test')
        order = MedicationOrder(
            fhir_id='MR-1', patient_id='P-1',
            medication_name='Vancomycin',
            start_date=timezone.now() - timedelta(hours=48),
        )
        assessment = UsageAssessment(
            patient=patient,
            medication=order,
            duration_hours=48.0,
            threshold_hours=72.0,
            exceeds_threshold=False,
            recommendation='Continue monitoring',
        )
        self.assertFalse(assessment.exceeds_threshold)


class MedicationOrderEdgeCaseTests(TestCase):
    """Test MedicationOrder edge cases."""

    def test_very_recent_order(self):
        """Order started a few seconds ago should have tiny duration."""
        order = MedicationOrder(
            fhir_id='MR-1', patient_id='P-1',
            medication_name='Meropenem',
            start_date=timezone.now() - timedelta(seconds=30),
        )
        self.assertAlmostEqual(order.duration_hours, 0.0, delta=0.02)

    def test_duration_days_property(self):
        """Duration in days should be duration_hours / 24."""
        start = timezone.now() - timedelta(hours=48)
        order = MedicationOrder(
            fhir_id='MR-1', patient_id='P-1',
            medication_name='Meropenem',
            start_date=start,
        )
        self.assertAlmostEqual(order.duration_days, 2.0, delta=0.01)


class ServiceRecommendationTests(TestCase):
    """Test recommendation generation logic."""

    def test_recommendation_high_alert(self):
        service = BroadSpectrumMonitorService.__new__(BroadSpectrumMonitorService)
        service.threshold_hours = 72
        order = MedicationOrder(
            fhir_id='MR-1', patient_id='P-1',
            medication_name='Meropenem',
            start_date=timezone.now() - timedelta(hours=80),
        )
        rec = service._generate_recommendation(order, 80.0)
        self.assertIn('Meropenem', rec)
        self.assertIn('72', rec)

    def test_recommendation_critical_double_threshold(self):
        service = BroadSpectrumMonitorService.__new__(BroadSpectrumMonitorService)
        service.threshold_hours = 72
        order = MedicationOrder(
            fhir_id='MR-1', patient_id='P-1',
            medication_name='Vancomycin',
            start_date=timezone.now() - timedelta(hours=168),
        )
        rec = service._generate_recommendation(order, 168.0)
        self.assertIn('Vancomycin', rec)
        self.assertIn('Urgent', rec)


class ServiceDeduplicationTests(TestCase):
    """Test that service properly deduplicates alerts."""

    def test_stats_only_counts_active(self):
        """Resolved alerts should not count in active_count."""
        Alert.objects.create(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            source_module='antimicrobial_usage',
            source_id='dedup-1',
            title='Active',
            summary='Active alert',
            severity=AlertSeverity.HIGH,
            status=AlertStatus.PENDING,
        )
        Alert.objects.create(
            alert_type=AlertType.BROAD_SPECTRUM_USAGE,
            source_module='antimicrobial_usage',
            source_id='dedup-2',
            title='Resolved',
            summary='Old alert',
            severity=AlertSeverity.HIGH,
            status=AlertStatus.RESOLVED,
            resolved_at=timezone.now() - timedelta(days=2),
        )

        service = BroadSpectrumMonitorService.__new__(BroadSpectrumMonitorService)
        service.threshold_hours = 72
        stats = service.get_stats()
        self.assertEqual(stats['active_count'], 1)
