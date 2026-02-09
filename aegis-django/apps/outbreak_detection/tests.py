"""
Tests for Outbreak Detection module.

Tests cover:
- Enum values (ClusterStatus, ClusterSeverity)
- OutbreakCluster model CRUD and methods
- ClusterCase model linked to clusters
- Cluster severity logic (case_count thresholds)
- Cluster resolve/status transitions
- OutbreakDetectionService (mocked and integration)
- Model __str__ methods
- Alert integration
"""

import uuid
from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.alerts.models import Alert, AlertType, AlertSeverity, AlertStatus

from .models import (
    OutbreakCluster, ClusterCase,
    ClusterStatus, ClusterSeverity,
)
from .services import OutbreakDetectionService


# ============================================================================
# Enum Tests
# ============================================================================

class ClusterStatusEnumTests(TestCase):
    """Test ClusterStatus enum."""

    def test_status_values(self):
        self.assertEqual(ClusterStatus.ACTIVE, 'active')
        self.assertEqual(ClusterStatus.INVESTIGATING, 'investigating')
        self.assertEqual(ClusterStatus.RESOLVED, 'resolved')

    def test_status_count(self):
        self.assertEqual(len(ClusterStatus.choices), 3)

    def test_labels(self):
        self.assertEqual(ClusterStatus.INVESTIGATING.label, 'Under Investigation')


class ClusterSeverityEnumTests(TestCase):
    """Test ClusterSeverity enum."""

    def test_severity_values(self):
        self.assertEqual(ClusterSeverity.LOW, 'low')
        self.assertEqual(ClusterSeverity.MEDIUM, 'medium')
        self.assertEqual(ClusterSeverity.HIGH, 'high')
        self.assertEqual(ClusterSeverity.CRITICAL, 'critical')

    def test_severity_count(self):
        self.assertEqual(len(ClusterSeverity.choices), 4)


# ============================================================================
# OutbreakCluster Model Tests
# ============================================================================

class OutbreakClusterModelTests(TestCase):
    """Test OutbreakCluster model CRUD and methods."""

    def _create_cluster(self, **kwargs):
        defaults = {
            'infection_type': 'mrsa',
            'organism': 'Staphylococcus aureus (MRSA)',
            'unit': 'G3 PICU',
            'case_count': 0,
            'window_days': 14,
        }
        defaults.update(kwargs)
        return OutbreakCluster.objects.create(**defaults)

    def test_create_cluster(self):
        cluster = self._create_cluster()
        self.assertEqual(cluster.infection_type, 'mrsa')
        self.assertEqual(cluster.unit, 'G3 PICU')
        self.assertEqual(cluster.status, ClusterStatus.ACTIVE)
        self.assertEqual(cluster.severity, ClusterSeverity.LOW)
        self.assertIsNotNone(cluster.id)
        self.assertIsInstance(cluster.id, uuid.UUID)

    def test_cluster_str(self):
        cluster = self._create_cluster(case_count=3)
        s = str(cluster)
        self.assertIn('MRSA', s)
        self.assertIn('G3 PICU', s)
        self.assertIn('3 cases', s)
        self.assertIn('Active', s)

    def test_update_severity_low(self):
        cluster = self._create_cluster(case_count=1)
        cluster.update_severity()
        self.assertEqual(cluster.severity, ClusterSeverity.LOW)

    def test_update_severity_medium(self):
        cluster = self._create_cluster(case_count=3)
        cluster.update_severity()
        self.assertEqual(cluster.severity, ClusterSeverity.MEDIUM)

    def test_update_severity_high(self):
        cluster = self._create_cluster(case_count=4)
        cluster.update_severity()
        self.assertEqual(cluster.severity, ClusterSeverity.HIGH)

    def test_update_severity_critical(self):
        cluster = self._create_cluster(case_count=5)
        cluster.update_severity()
        self.assertEqual(cluster.severity, ClusterSeverity.CRITICAL)

    def test_resolve_cluster(self):
        cluster = self._create_cluster()
        cluster.resolve(resolved_by='ip_smith', notes='False alarm')
        cluster.refresh_from_db()
        self.assertEqual(cluster.status, ClusterStatus.RESOLVED)
        self.assertEqual(cluster.resolved_by, 'ip_smith')
        self.assertEqual(cluster.resolution_notes, 'False alarm')
        self.assertIsNotNone(cluster.resolved_at)

    def test_add_case_updates_dates_and_severity(self):
        cluster = self._create_cluster()
        now = timezone.now()
        case = ClusterCase.objects.create(
            cluster=cluster,
            source='mdro',
            source_id='mdro-001',
            patient_id='p1',
            patient_mrn='MRN001',
            event_date=now,
            infection_type='mrsa',
            unit='G3 PICU',
        )
        cluster.add_case(case)
        cluster.refresh_from_db()
        self.assertEqual(cluster.case_count, 1)
        self.assertEqual(cluster.first_case_date, now)
        self.assertEqual(cluster.last_case_date, now)

    def test_add_multiple_cases_updates_date_range(self):
        cluster = self._create_cluster()
        early = timezone.now() - timedelta(days=5)
        late = timezone.now()

        case1 = ClusterCase.objects.create(
            cluster=cluster,
            source='mdro', source_id='mdro-early',
            patient_id='p1', patient_mrn='MRN001',
            event_date=early, infection_type='mrsa', unit='G3 PICU',
        )
        cluster.add_case(case1)

        case2 = ClusterCase.objects.create(
            cluster=cluster,
            source='mdro', source_id='mdro-late',
            patient_id='p2', patient_mrn='MRN002',
            event_date=late, infection_type='mrsa', unit='G3 PICU',
        )
        cluster.add_case(case2)

        cluster.refresh_from_db()
        self.assertEqual(cluster.case_count, 2)
        self.assertEqual(cluster.first_case_date, early)
        self.assertEqual(cluster.last_case_date, late)

    def test_timestamps(self):
        cluster = self._create_cluster()
        self.assertIsNotNone(cluster.created_at)
        self.assertIsNotNone(cluster.updated_at)

    def test_default_window_days(self):
        cluster = OutbreakCluster.objects.create(
            infection_type='vre',
            unit='A6 Hosp Med',
        )
        self.assertEqual(cluster.window_days, 14)


# ============================================================================
# ClusterCase Model Tests
# ============================================================================

class ClusterCaseModelTests(TestCase):
    """Test ClusterCase model."""

    def setUp(self):
        self.cluster = OutbreakCluster.objects.create(
            infection_type='cdi',
            unit='A4 GI/Nephro',
        )

    def test_create_case(self):
        case = ClusterCase.objects.create(
            cluster=self.cluster,
            source='cdi',
            source_id='cdi-001',
            patient_id='patient-cdi-1',
            patient_mrn='MRN-CDI1',
            event_date=timezone.now(),
            organism='Clostridioides difficile',
            infection_type='cdi',
            unit='A4 GI/Nephro',
        )
        self.assertEqual(case.cluster, self.cluster)
        self.assertEqual(case.source, 'cdi')
        self.assertIsNotNone(case.added_at)

    def test_case_str(self):
        case = ClusterCase.objects.create(
            cluster=self.cluster,
            source='hai',
            source_id='hai-001',
            patient_id='p1',
            patient_mrn='MRN001',
            event_date=timezone.now(),
            infection_type='clabsi',
            unit='G3 PICU',
        )
        s = str(case)
        self.assertIn('hai:hai-001', s)
        self.assertIn('MRN001', s)
        self.assertIn('clabsi', s)

    def test_unique_source_constraint(self):
        ClusterCase.objects.create(
            cluster=self.cluster,
            source='mdro', source_id='unique-case',
            patient_id='p1', patient_mrn='MRN001',
            event_date=timezone.now(),
            infection_type='mrsa', unit='G3 PICU',
        )
        with self.assertRaises(Exception):
            ClusterCase.objects.create(
                cluster=self.cluster,
                source='mdro', source_id='unique-case',
                patient_id='p2', patient_mrn='MRN002',
                event_date=timezone.now(),
                infection_type='mrsa', unit='G3 PICU',
            )

    def test_cascade_delete(self):
        ClusterCase.objects.create(
            cluster=self.cluster,
            source='mdro', source_id='del-001',
            patient_id='p1', patient_mrn='MRN001',
            event_date=timezone.now(),
            infection_type='mrsa', unit='G3 PICU',
        )
        self.assertEqual(ClusterCase.objects.count(), 1)
        self.cluster.delete()
        self.assertEqual(ClusterCase.objects.count(), 0)


# ============================================================================
# OutbreakDetectionService Tests
# ============================================================================

class OutbreakDetectionServiceTests(TestCase):
    """Test OutbreakDetectionService."""

    def test_service_init(self):
        service = OutbreakDetectionService()
        self.assertEqual(service.window_days, 14)
        self.assertEqual(service.min_cluster_size, 2)

    def test_get_recent_cases_empty(self):
        service = OutbreakDetectionService()
        cases = service.get_recent_cases()
        self.assertEqual(len(cases), 0)

    def test_run_detection_empty(self):
        service = OutbreakDetectionService()
        result = service.run_detection()
        self.assertEqual(result['cases_analyzed'], 0)
        self.assertEqual(result['new_cases_processed'], 0)
        self.assertEqual(result['clusters_formed'], 0)

    def test_resolve_cluster_nonexistent(self):
        service = OutbreakDetectionService()
        result = service.resolve_cluster(uuid.uuid4(), 'test_user')
        self.assertFalse(result)

    def test_resolve_cluster_success(self):
        cluster = OutbreakCluster.objects.create(
            infection_type='mrsa',
            unit='G3 PICU',
        )
        service = OutbreakDetectionService()
        result = service.resolve_cluster(cluster.id, 'ip_smith', 'Resolved')
        self.assertTrue(result)
        cluster.refresh_from_db()
        self.assertEqual(cluster.status, ClusterStatus.RESOLVED)

    def test_get_stats_empty(self):
        service = OutbreakDetectionService()
        stats = service.get_stats()
        self.assertEqual(stats['active_clusters'], 0)
        self.assertEqual(stats['investigating_clusters'], 0)
        self.assertEqual(stats['resolved_clusters'], 0)

    def test_get_stats_with_clusters(self):
        OutbreakCluster.objects.create(
            infection_type='mrsa', unit='G3 PICU',
            status=ClusterStatus.ACTIVE,
        )
        OutbreakCluster.objects.create(
            infection_type='vre', unit='A6 Hosp Med',
            status=ClusterStatus.INVESTIGATING,
        )
        OutbreakCluster.objects.create(
            infection_type='cdi', unit='A4 GI/Nephro',
            status=ClusterStatus.RESOLVED,
        )
        service = OutbreakDetectionService()
        stats = service.get_stats()
        self.assertEqual(stats['active_clusters'], 1)
        self.assertEqual(stats['investigating_clusters'], 1)
        self.assertEqual(stats['resolved_clusters'], 1)

    def test_update_cluster_status_investigating(self):
        cluster = OutbreakCluster.objects.create(
            infection_type='mrsa', unit='G3 PICU',
            status=ClusterStatus.ACTIVE,
        )
        service = OutbreakDetectionService()
        result = service.update_cluster_status(
            cluster.id, ClusterStatus.INVESTIGATING,
        )
        self.assertTrue(result)
        cluster.refresh_from_db()
        self.assertEqual(cluster.status, ClusterStatus.INVESTIGATING)

    def test_update_cluster_status_not_outbreak(self):
        cluster = OutbreakCluster.objects.create(
            infection_type='mrsa', unit='G3 PICU',
            status=ClusterStatus.ACTIVE,
        )
        service = OutbreakDetectionService()
        result = service.update_cluster_status(
            cluster.id, 'not_outbreak', notes='Unrelated cases',
            updated_by='ip_smith',
        )
        self.assertTrue(result)
        cluster.refresh_from_db()
        self.assertEqual(cluster.status, ClusterStatus.RESOLVED)
        self.assertIn('NOT AN OUTBREAK', cluster.resolution_notes)


# ============================================================================
# Alert Integration Tests
# ============================================================================

class OutbreakAlertIntegrationTests(TestCase):
    """Test outbreak alert type integration."""

    def test_outbreak_cluster_alert_type(self):
        self.assertEqual(AlertType.OUTBREAK_CLUSTER, 'outbreak_cluster')

    def test_create_outbreak_alert(self):
        alert = Alert.objects.create(
            alert_type=AlertType.OUTBREAK_CLUSTER,
            source_module='outbreak_detection',
            source_id='test-cluster-1',
            title='Potential Outbreak: MRSA in G3 PICU',
            summary='3 cases detected within 14 days.',
            severity=AlertSeverity.MEDIUM,
            patient_location='G3 PICU',
        )
        self.assertEqual(alert.alert_type, 'outbreak_cluster')
        self.assertEqual(alert.status, AlertStatus.PENDING)
