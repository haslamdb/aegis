"""Tests for the Outbreak Detection API ViewSet."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.authentication.models import User, UserRole
from apps.outbreak_detection.models import (
    OutbreakCluster, ClusterCase, ClusterStatus, ClusterSeverity,
)


class OutbreakAPITestBase(TestCase):
    """Base class with user fixtures and helper methods."""

    @classmethod
    def setUpTestData(cls):
        cls.ip_user = User.objects.create_user(
            username='ip_ob', email='ip_ob@test.com', password='testpass123',
            role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.pharmacist = User.objects.create_user(
            username='pharm_ob', email='pharm_ob@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.physician = User.objects.create_user(
            username='doc_ob', email='doc_ob@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.admin = User.objects.create_user(
            username='admin_ob', email='admin_ob@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.ip_token = Token.objects.create(user=cls.ip_user)
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.doc_token = Token.objects.create(user=cls.physician)
        cls.admin_token = Token.objects.create(user=cls.admin)

    def setUp(self):
        self.client = APIClient()

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_cluster(self, **overrides):
        defaults = {
            'infection_type': 'mrsa',
            'organism': 'MRSA',
            'unit': 'G3 PICU',
            'case_count': 3,
            'status': ClusterStatus.ACTIVE,
            'severity': ClusterSeverity.MEDIUM,
            'first_case_date': timezone.now() - timedelta(days=7),
            'last_case_date': timezone.now() - timedelta(days=1),
        }
        defaults.update(overrides)
        return OutbreakCluster.objects.create(**defaults)

    def add_case(self, cluster, **overrides):
        defaults = {
            'cluster': cluster,
            'source': 'mdro',
            'source_id': f'MDRO-{ClusterCase.objects.count() + 1:04d}',
            'patient_id': 'PAT-001',
            'patient_mrn': 'MRN001',
            'event_date': timezone.now() - timedelta(days=2),
            'organism': 'MRSA',
            'infection_type': 'mrsa',
            'unit': 'G3 PICU',
        }
        defaults.update(overrides)
        return ClusterCase.objects.create(**defaults)


class OutbreakClusterListTests(OutbreakAPITestBase):
    """GET /api/v1/outbreaks/clusters/ tests."""

    def test_list_requires_auth(self):
        response = self.client.get('/api/v1/outbreaks/clusters/')
        self.assertIn(response.status_code, [401, 403])

    def test_list_returns_clusters(self):
        self.create_cluster()
        self.create_cluster(unit='G6 CICU', infection_type='vre')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_list_uses_lightweight_serializer(self):
        self.create_cluster()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/')
        result = response.data['results'][0]
        self.assertNotIn('cases', result)
        self.assertIn('infection_type', result)
        self.assertIn('severity', result)

    def test_filter_by_status(self):
        self.create_cluster(status=ClusterStatus.ACTIVE)
        self.create_cluster(status=ClusterStatus.RESOLVED, unit='A6')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/', {'status': 'active'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_severity(self):
        self.create_cluster(severity=ClusterSeverity.CRITICAL)
        self.create_cluster(severity=ClusterSeverity.LOW, unit='A7')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/', {'severity': 'critical'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_infection_type(self):
        self.create_cluster(infection_type='mrsa')
        self.create_cluster(infection_type='vre', unit='A5')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/', {'infection_type': 'mrsa'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_unit(self):
        self.create_cluster(unit='G3 PICU')
        self.create_cluster(unit='G6 CICU', infection_type='vre')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/', {'unit': 'PICU'})
        self.assertEqual(response.data['count'], 1)


class OutbreakClusterDetailTests(OutbreakAPITestBase):
    """GET /api/v1/outbreaks/clusters/{uuid}/ tests."""

    def test_detail_returns_full_data(self):
        cluster = self.create_cluster()
        self.add_case(cluster)
        self.add_case(cluster, source_id='MDRO-ALT', patient_mrn='MRN002')
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/outbreaks/clusters/{cluster.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('cases', response.data)
        self.assertEqual(len(response.data['cases']), 2)

    def test_detail_includes_resolution_info(self):
        cluster = self.create_cluster(
            status=ClusterStatus.RESOLVED,
            resolved_by='Dr. IP',
            resolution_notes='Outbreak contained',
            resolved_at=timezone.now(),
        )
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/outbreaks/clusters/{cluster.id}/')
        self.assertEqual(response.data['resolved_by'], 'Dr. IP')
        self.assertEqual(response.data['resolution_notes'], 'Outbreak contained')

    def test_404_for_nonexistent_cluster(self):
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, 404)


class OutbreakUpdateStatusTests(OutbreakAPITestBase):
    """POST /api/v1/outbreaks/clusters/{uuid}/update_status/ tests."""

    def test_ip_can_update_status(self):
        cluster = self.create_cluster(status=ClusterStatus.ACTIVE)
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/outbreaks/clusters/{cluster.id}/update_status/',
            {'status': 'investigating', 'notes': 'Beginning investigation'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        cluster.refresh_from_db()
        self.assertEqual(cluster.status, ClusterStatus.INVESTIGATING)

    def test_admin_can_update_status(self):
        cluster = self.create_cluster(status=ClusterStatus.INVESTIGATING)
        self.auth_as(self.admin_token)
        response = self.client.post(
            f'/api/v1/outbreaks/clusters/{cluster.id}/update_status/',
            {'status': 'resolved', 'notes': 'Outbreak contained'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        cluster.refresh_from_db()
        self.assertEqual(cluster.status, ClusterStatus.RESOLVED)
        self.assertIsNotNone(cluster.resolved_at)

    def test_physician_cannot_update_status(self):
        cluster = self.create_cluster()
        self.auth_as(self.doc_token)
        response = self.client.post(
            f'/api/v1/outbreaks/clusters/{cluster.id}/update_status/',
            {'status': 'investigating'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_pharmacist_cannot_update_status(self):
        cluster = self.create_cluster()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/outbreaks/clusters/{cluster.id}/update_status/',
            {'status': 'investigating'},
            format='json',
        )
        self.assertEqual(response.status_code, 403)

    def test_update_requires_status_field(self):
        cluster = self.create_cluster()
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/outbreaks/clusters/{cluster.id}/update_status/',
            {},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_update_rejects_invalid_status(self):
        cluster = self.create_cluster()
        self.auth_as(self.ip_token)
        response = self.client.post(
            f'/api/v1/outbreaks/clusters/{cluster.id}/update_status/',
            {'status': 'invalid_status'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_resolve_sets_resolved_by(self):
        cluster = self.create_cluster()
        self.auth_as(self.ip_token)
        self.client.post(
            f'/api/v1/outbreaks/clusters/{cluster.id}/update_status/',
            {'status': 'resolved', 'notes': 'Contained'},
            format='json',
        )
        cluster.refresh_from_db()
        self.assertEqual(cluster.resolved_by, self.ip_user.username)
        self.assertEqual(cluster.resolution_notes, 'Contained')


class OutbreakStatsTests(OutbreakAPITestBase):
    """GET /api/v1/outbreaks/clusters/stats/ tests."""

    def test_stats_returns_aggregates(self):
        self.create_cluster(status=ClusterStatus.ACTIVE, severity=ClusterSeverity.HIGH)
        self.create_cluster(
            status=ClusterStatus.RESOLVED, severity=ClusterSeverity.LOW,
            unit='A6', infection_type='cdi',
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('active_clusters', response.data)
        self.assertIn('by_status', response.data)
        self.assertIn('by_severity', response.data)
        self.assertIn('by_infection_type', response.data)
        self.assertEqual(response.data['active_clusters'], 1)

    def test_stats_respects_days_param(self):
        old = self.create_cluster()
        old.created_at = timezone.now() - timedelta(days=60)
        old.save(update_fields=['created_at'])
        self.create_cluster(unit='A7', infection_type='vre')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/outbreaks/clusters/stats/', {'days': 7})
        self.assertEqual(response.data['total_recent'], 1)
