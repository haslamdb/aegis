"""Cross-module integration tests for AEGIS."""

from datetime import date

from django.test import TestCase
from django.core.management import call_command
from django.utils import timezone

from apps.authentication.models import User, UserRole
from apps.alerts.models import (
    Alert, AlertType, AlertStatus, AlertSeverity,
    AlertAudit, ResolutionReason,
)
from apps.hai_detection.models import (
    HAICandidate, HAIType, CandidateStatus,
)
from apps.mdro.models import MDROCase, MDROTypeChoices
from apps.nhsn_reporting.models import NHSNEvent, HAIEventType
from apps.outbreak_detection.models import (
    OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity,
)


# =============================================================================
# Cross-module model integration
# =============================================================================


class HAIToAlertIntegrationTests(TestCase):
    """HAICandidate confirmation should produce a linked Alert."""

    def test_create_alert_from_hai_candidate(self):
        candidate = HAICandidate.objects.create(
            hai_type=HAIType.CLABSI,
            patient_id='P-001', patient_mrn='MRN-001',
            patient_name='Test Patient', patient_location='G3 PICU',
            culture_id='C-001', culture_date=timezone.now(),
            organism='Staph aureus',
            status=CandidateStatus.CONFIRMED,
        )
        alert = Alert.objects.create(
            alert_type=AlertType.CLABSI,
            source_module='hai_detection',
            source_id=str(candidate.id),
            title=f'CLABSI candidate - {candidate.patient_mrn}',
            summary='Confirmed CLABSI',
            patient_mrn=candidate.patient_mrn,
            patient_name=candidate.patient_name,
            patient_location=candidate.patient_location,
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.source_id, str(candidate.id))
        self.assertEqual(alert.alert_type, AlertType.CLABSI)
        self.assertEqual(alert.patient_mrn, 'MRN-001')

    def test_hai_candidate_to_alert_round_trip(self):
        candidate = HAICandidate.objects.create(
            hai_type=HAIType.CAUTI,
            patient_id='P-002', patient_mrn='MRN-002',
            culture_id='C-002', culture_date=timezone.now(),
            organism='E. coli',
        )
        alert = Alert.objects.create(
            alert_type=AlertType.CAUTI,
            source_module='hai_detection',
            source_id=str(candidate.id),
            title='CAUTI', summary='Test',
            patient_mrn='MRN-002',
        )
        found = Alert.objects.filter(
            source_module='hai_detection',
            source_id=str(candidate.id),
        ).first()
        self.assertIsNotNone(found)
        self.assertEqual(found.alert_type, AlertType.CAUTI)


class MDROToAlertIntegrationTests(TestCase):
    """MDROCase should be linkable to Alert via source_id."""

    def test_create_alert_from_mdro(self):
        mdro = MDROCase.objects.create(
            patient_id='P-010', patient_mrn='MRN-010',
            culture_id='MC-001', culture_date=timezone.now(),
            organism='MRSA', mdro_type=MDROTypeChoices.MRSA,
            unit='A6',
        )
        alert = Alert.objects.create(
            alert_type=AlertType.MDRO_DETECTION,
            source_module='mdro',
            source_id=str(mdro.id),
            title='MRSA detected', summary='New MRSA case',
            patient_mrn=mdro.patient_mrn,
            severity=AlertSeverity.HIGH,
        )
        self.assertEqual(alert.source_module, 'mdro')
        self.assertEqual(alert.patient_mrn, 'MRN-010')

    def test_mdro_alert_query(self):
        mdro = MDROCase.objects.create(
            patient_id='P-011', patient_mrn='MRN-011',
            culture_id='MC-002', culture_date=timezone.now(),
            organism='VRE', mdro_type=MDROTypeChoices.VRE,
        )
        Alert.objects.create(
            alert_type=AlertType.MDRO_DETECTION,
            source_module='mdro', source_id=str(mdro.id),
            title='VRE', summary='Test', patient_mrn='MRN-011',
        )
        alerts = Alert.objects.by_type(AlertType.MDRO_DETECTION)
        self.assertEqual(alerts.count(), 1)


class AlertLifecycleIntegrationTests(TestCase):
    """Full alert lifecycle: create -> acknowledge -> resolve."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='ip_lifecycle', email='ip_life@test.com',
            password='testpass123', role=UserRole.INFECTION_PREVENTIONIST,
        )

    def _create_alert(self, source_id='lifecycle-1'):
        return Alert.objects.create(
            alert_type=AlertType.CLABSI,
            source_module='hai_detection',
            source_id=source_id,
            title='CLABSI Alert', summary='Test lifecycle',
            patient_mrn='MRN-999',
            severity=AlertSeverity.HIGH,
        )

    def test_full_lifecycle(self):
        alert = self._create_alert()
        self.assertEqual(alert.status, AlertStatus.PENDING)

        alert.acknowledge(self.user)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.ACKNOWLEDGED)
        self.assertEqual(alert.acknowledged_by, self.user)
        self.assertIsNotNone(alert.acknowledged_at)

        alert.resolve(self.user, ResolutionReason.ACCEPTED, notes='Confirmed HAI')
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)
        self.assertEqual(alert.resolved_by, self.user)
        self.assertEqual(alert.resolution_reason, ResolutionReason.ACCEPTED)
        self.assertEqual(alert.resolution_notes, 'Confirmed HAI')

    def test_lifecycle_creates_audit_trail(self):
        alert = self._create_alert('lifecycle-audit')
        alert.acknowledge(self.user, ip_address='10.0.0.1')
        alert.resolve(self.user, ResolutionReason.THERAPY_CHANGED)

        # Signal creates audit on every save (CREATED, ACKNOWLEDGED, RESOLVED)
        # plus acknowledge()/resolve() methods call create_audit_entry() explicitly
        audits = alert.audit_log.order_by('performed_at')
        self.assertEqual(audits.count(), 5)
        actions = list(audits.values_list('action', flat=True))
        self.assertIn('CREATED', actions)
        self.assertIn('acknowledged', actions)
        self.assertIn('resolved', actions)

    def test_audit_records_old_status(self):
        alert = self._create_alert('lifecycle-old-status')
        alert.acknowledge(self.user)
        # The explicit create_audit_entry from acknowledge() records old -> new
        audit = alert.audit_log.filter(action='acknowledged').first()
        self.assertEqual(audit.old_status, AlertStatus.PENDING)
        self.assertEqual(audit.new_status, AlertStatus.ACKNOWLEDGED)

    def test_resolve_captures_details(self):
        alert = self._create_alert('lifecycle-details')
        alert.resolve(self.user, ResolutionReason.FALSE_POSITIVE, notes='Not HAI')
        audit = alert.audit_log.first()
        self.assertEqual(audit.details['reason'], ResolutionReason.FALSE_POSITIVE)
        self.assertEqual(audit.details['notes'], 'Not HAI')


class HAIToNHSNIntegrationTests(TestCase):
    """HAICandidate -> NHSNEvent FK linkage."""

    def test_nhsn_event_links_to_hai_candidate(self):
        candidate = HAICandidate.objects.create(
            hai_type=HAIType.CLABSI,
            patient_id='P-020', patient_mrn='MRN-020',
            culture_id='C-020', culture_date=timezone.now(),
            organism='Staph aureus',
            status=CandidateStatus.CONFIRMED,
        )
        event = NHSNEvent.objects.create(
            candidate=candidate,
            event_date=date.today(),
            hai_type=HAIEventType.CLABSI,
            location_code='NICU',
        )
        self.assertEqual(event.candidate, candidate)
        self.assertEqual(candidate.nhsn_events.count(), 1)

    def test_nhsn_event_without_candidate(self):
        event = NHSNEvent.objects.create(
            candidate=None,
            event_date=date.today(),
            hai_type=HAIEventType.CAUTI,
        )
        self.assertIsNone(event.candidate)


class OutbreakClusterIntegrationTests(TestCase):
    """Outbreak cluster with cases from multiple sources."""

    def test_cluster_with_mixed_source_cases(self):
        mdro = MDROCase.objects.create(
            patient_id='P-030', patient_mrn='MRN-030',
            culture_id='MC-030', culture_date=timezone.now(),
            organism='MRSA', mdro_type=MDROTypeChoices.MRSA,
            unit='G3 PICU',
        )
        hai = HAICandidate.objects.create(
            hai_type=HAIType.CLABSI,
            patient_id='P-031', patient_mrn='MRN-031',
            culture_id='C-031', culture_date=timezone.now(),
            organism='MRSA',
        )
        cluster = OutbreakCluster.objects.create(
            infection_type='mrsa', organism='MRSA', unit='G3 PICU',
        )
        ClusterCase.objects.create(
            cluster=cluster, source='mdro', source_id=str(mdro.id),
            patient_id='P-030', patient_mrn='MRN-030',
            event_date=timezone.now(), organism='MRSA',
            infection_type='mrsa', unit='G3 PICU',
        )
        ClusterCase.objects.create(
            cluster=cluster, source='hai', source_id=str(hai.id),
            patient_id='P-031', patient_mrn='MRN-031',
            event_date=timezone.now(), organism='MRSA',
            infection_type='mrsa', unit='G3 PICU',
        )
        self.assertEqual(cluster.cases.count(), 2)
        sources = set(cluster.cases.values_list('source', flat=True))
        self.assertEqual(sources, {'mdro', 'hai'})


class FullWorkflowIntegrationTests(TestCase):
    """End-to-end: HAI detected -> Alert created -> lifecycle -> NHSN event."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='ip_workflow', email='ip_wf@test.com',
            password='testpass123', role=UserRole.INFECTION_PREVENTIONIST,
        )

    def test_full_workflow(self):
        candidate = HAICandidate.objects.create(
            hai_type=HAIType.CLABSI,
            patient_id='P-050', patient_mrn='MRN-050',
            culture_id='C-050', culture_date=timezone.now(),
            organism='Staph aureus', status=CandidateStatus.PENDING,
        )

        alert = Alert.objects.create(
            alert_type=AlertType.CLABSI,
            source_module='hai_detection',
            source_id=str(candidate.id),
            title='Potential CLABSI', summary='Rule-based screening',
            patient_mrn='MRN-050', severity=AlertSeverity.HIGH,
        )

        alert.acknowledge(self.user)
        candidate.status = CandidateStatus.CONFIRMED
        candidate.save(update_fields=['status'])
        alert.resolve(self.user, ResolutionReason.ACCEPTED, notes='Confirmed')

        nhsn_event = NHSNEvent.objects.create(
            candidate=candidate,
            event_date=date.today(),
            hai_type=HAIEventType.CLABSI,
            location_code='PICU',
        )

        alert.refresh_from_db()
        candidate.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)
        self.assertEqual(candidate.status, CandidateStatus.CONFIRMED)
        self.assertEqual(candidate.nhsn_events.count(), 1)
        # Signal creates CREATED + ACKNOWLEDGED + RESOLVED audits,
        # plus acknowledge()/resolve() explicit entries = 5 total
        self.assertEqual(alert.audit_log.count(), 5)


# =============================================================================
# Management command smoke tests
# =============================================================================


class DemoAlertCommandTests(TestCase):
    """Smoke test create_demo_alerts management command."""

    def test_create_demo_alerts(self):
        call_command('create_demo_alerts', '--count', '2', '--clear', verbosity=0)
        self.assertGreaterEqual(Alert.objects.count(), 2)

    def test_create_demo_alerts_clears_demo_module(self):
        # --clear only deletes alerts with source_module='demo'
        Alert.objects.create(
            alert_type=AlertType.OTHER,
            source_module='demo', source_id='old-demo-1',
            title='Old demo', summary='Old demo alert',
        )
        call_command('create_demo_alerts', '--count', '2', '--clear', verbosity=0)
        old = Alert.objects.filter(source_id='old-demo-1').count()
        self.assertEqual(old, 0)


class DemoHAICommandTests(TestCase):
    """Smoke test create_demo_hai management command."""

    def test_create_demo_hai(self):
        call_command('create_demo_hai', '--count', '2', '--clear', verbosity=0)
        self.assertGreaterEqual(HAICandidate.objects.count(), 2)


class DemoOutbreakCommandTests(TestCase):
    """Smoke test create_demo_outbreaks management command."""

    def test_create_demo_outbreaks(self):
        call_command('create_demo_outbreaks', '--count', '2', '--clear', verbosity=0)
        self.assertGreaterEqual(OutbreakCluster.objects.count(), 1)


class DemoMDROCommandTests(TestCase):
    """Smoke test create_demo_mdro management command."""

    def test_create_demo_mdro(self):
        call_command('create_demo_mdro', '--count', '2', '--clear', verbosity=0)
        self.assertGreaterEqual(MDROCase.objects.count(), 2)
