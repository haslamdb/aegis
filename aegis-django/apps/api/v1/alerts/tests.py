"""Tests for the Alert API ViewSet."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.authtoken.models import Token

from apps.alerts.models import (
    Alert, AlertAudit, AlertType, AlertStatus, AlertSeverity, ResolutionReason,
)
from apps.authentication.models import User, UserRole


class AlertAPITestBase(TestCase):
    """Base class with user fixtures and helper methods."""

    @classmethod
    def setUpTestData(cls):
        cls.pharmacist = User.objects.create_user(
            username='pharm', email='pharm@test.com', password='testpass123',
            role=UserRole.ASP_PHARMACIST,
        )
        cls.ip_user = User.objects.create_user(
            username='ipuser', email='ip@test.com', password='testpass123',
            role=UserRole.INFECTION_PREVENTIONIST,
        )
        cls.physician = User.objects.create_user(
            username='doc', email='doc@test.com', password='testpass123',
            role=UserRole.PHYSICIAN,
        )
        cls.admin = User.objects.create_user(
            username='admin_user', email='admin@test.com', password='testpass123',
            role=UserRole.ADMIN,
        )
        cls.pharm_token = Token.objects.create(user=cls.pharmacist)
        cls.ip_token = Token.objects.create(user=cls.ip_user)
        cls.doc_token = Token.objects.create(user=cls.physician)
        cls.admin_token = Token.objects.create(user=cls.admin)

    def setUp(self):
        self.client = APIClient()

    def auth_as(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {token.key}')

    def create_alert(self, **overrides):
        defaults = {
            'alert_type': AlertType.DRUG_BUG_MISMATCH,
            'source_module': 'drug_bug',
            'source_id': 'test-001',
            'title': 'Test Alert',
            'summary': 'Test alert summary',
            'patient_mrn': 'MRN001',
            'patient_name': 'Test Patient',
            'severity': AlertSeverity.HIGH,
            'status': AlertStatus.PENDING,
        }
        defaults.update(overrides)
        return Alert.objects.create(**defaults)


class AlertListTests(AlertAPITestBase):
    """GET /api/v1/alerts/ tests."""

    def test_list_requires_auth(self):
        response = self.client.get('/api/v1/alerts/')
        self.assertIn(response.status_code, [401, 403])

    def test_list_returns_alerts(self):
        self.create_alert()
        self.create_alert(source_id='test-002', patient_mrn='MRN002')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['count'], 2)

    def test_list_uses_lightweight_serializer(self):
        self.create_alert()
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/')
        result = response.data['results'][0]
        # List should NOT include details or audit_log
        self.assertNotIn('details', result)
        self.assertNotIn('audit_log', result)
        # But should include core fields
        self.assertIn('title', result)
        self.assertIn('severity', result)

    def test_filter_by_status(self):
        self.create_alert(status=AlertStatus.PENDING, source_id='s1')
        self.create_alert(status=AlertStatus.RESOLVED, source_id='s2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/', {'status': 'pending'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_severity(self):
        self.create_alert(severity=AlertSeverity.CRITICAL, source_id='s1')
        self.create_alert(severity=AlertSeverity.LOW, source_id='s2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/', {'severity': 'critical'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_alert_type(self):
        self.create_alert(alert_type=AlertType.CLABSI, source_id='s1')
        self.create_alert(alert_type=AlertType.SSI, source_id='s2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/', {'alert_type': 'clabsi'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_patient_mrn_icontains(self):
        self.create_alert(patient_mrn='MRN12345', source_id='s1')
        self.create_alert(patient_mrn='MRN99999', source_id='s2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/', {'patient_mrn': '123'})
        self.assertEqual(response.data['count'], 1)

    def test_filter_by_date_range(self):
        old = self.create_alert(source_id='s1')
        old.created_at = timezone.now() - timedelta(days=60)
        old.save(update_fields=['created_at'])
        self.create_alert(source_id='s2')  # recent
        self.auth_as(self.doc_token)
        after = (timezone.now() - timedelta(days=7)).isoformat()
        response = self.client.get('/api/v1/alerts/', {'created_after': after})
        self.assertEqual(response.data['count'], 1)

    def test_pagination(self):
        for i in range(55):
            self.create_alert(source_id=f's{i}')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/')
        self.assertEqual(len(response.data['results']), 50)  # PAGE_SIZE
        self.assertIsNotNone(response.data['next'])


class AlertDetailTests(AlertAPITestBase):
    """GET /api/v1/alerts/{uuid}/ tests."""

    def test_detail_returns_full_data(self):
        alert = self.create_alert(details={'key': 'value'})
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/alerts/{alert.id}/')
        self.assertEqual(response.status_code, 200)
        self.assertIn('details', response.data)
        self.assertIn('audit_log', response.data)
        self.assertEqual(response.data['details'], {'key': 'value'})

    def test_detail_includes_audit_log(self):
        alert = self.create_alert()
        alert.acknowledge(self.pharmacist, ip_address='127.0.0.1')
        self.auth_as(self.doc_token)
        response = self.client.get(f'/api/v1/alerts/{alert.id}/')
        self.assertGreaterEqual(len(response.data['audit_log']), 1)
        actions = [entry['action'] for entry in response.data['audit_log']]
        self.assertIn('acknowledged', actions)

    def test_404_for_nonexistent_alert(self):
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, 404)


class AlertAcknowledgeTests(AlertAPITestBase):
    """POST /api/v1/alerts/{uuid}/acknowledge/ tests."""

    def test_pharmacist_can_acknowledge(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        response = self.client.post(f'/api/v1/alerts/{alert.id}/acknowledge/')
        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.ACKNOWLEDGED)
        self.assertEqual(alert.acknowledged_by, self.pharmacist)

    def test_ip_can_acknowledge(self):
        alert = self.create_alert()
        self.auth_as(self.ip_token)
        response = self.client.post(f'/api/v1/alerts/{alert.id}/acknowledge/')
        self.assertEqual(response.status_code, 200)

    def test_physician_cannot_acknowledge(self):
        alert = self.create_alert()
        self.auth_as(self.doc_token)
        response = self.client.post(f'/api/v1/alerts/{alert.id}/acknowledge/')
        self.assertEqual(response.status_code, 403)

    def test_cannot_acknowledge_resolved_alert(self):
        alert = self.create_alert(status=AlertStatus.RESOLVED)
        self.auth_as(self.pharm_token)
        response = self.client.post(f'/api/v1/alerts/{alert.id}/acknowledge/')
        self.assertEqual(response.status_code, 400)

    def test_acknowledge_creates_audit_entry(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        self.client.post(f'/api/v1/alerts/{alert.id}/acknowledge/')
        self.assertEqual(AlertAudit.objects.filter(alert=alert, action='acknowledged').count(), 1)


class AlertSnoozeTests(AlertAPITestBase):
    """POST /api/v1/alerts/{uuid}/snooze/ tests."""

    def test_snooze_with_valid_hours(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/alerts/{alert.id}/snooze/',
            {'hours': 2},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.SNOOZED)
        self.assertIsNotNone(alert.snoozed_until)

    def test_snooze_rejects_invalid_hours(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/alerts/{alert.id}/snooze/',
            {'hours': 100},  # >72
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_physician_cannot_snooze(self):
        alert = self.create_alert()
        self.auth_as(self.doc_token)
        response = self.client.post(
            f'/api/v1/alerts/{alert.id}/snooze/',
            {'hours': 1},
            format='json',
        )
        self.assertEqual(response.status_code, 403)


class AlertResolveTests(AlertAPITestBase):
    """POST /api/v1/alerts/{uuid}/resolve/ tests."""

    def test_resolve_with_reason(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/alerts/{alert.id}/resolve/',
            {'reason': 'accepted', 'notes': 'Therapy changed per recommendation'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(alert.status, AlertStatus.RESOLVED)
        self.assertEqual(alert.resolution_reason, ResolutionReason.ACCEPTED)
        self.assertEqual(alert.resolution_notes, 'Therapy changed per recommendation')

    def test_resolve_requires_valid_reason(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/alerts/{alert.id}/resolve/',
            {'reason': 'invalid_reason'},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_resolve_creates_audit_entry(self):
        alert = self.create_alert()
        self.auth_as(self.admin_token)
        self.client.post(
            f'/api/v1/alerts/{alert.id}/resolve/',
            {'reason': 'false_positive'},
            format='json',
        )
        audit = AlertAudit.objects.filter(alert=alert, action='resolved').first()
        self.assertIsNotNone(audit)
        self.assertEqual(audit.details['reason'], 'false_positive')


class AlertAddNoteTests(AlertAPITestBase):
    """POST /api/v1/alerts/{uuid}/add_note/ tests."""

    def test_add_note(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/alerts/{alert.id}/add_note/',
            {'note': 'Called attending, will reassess in AM'},
            format='json',
        )
        self.assertEqual(response.status_code, 200)
        alert.refresh_from_db()
        self.assertEqual(len(alert.details['notes']), 1)
        self.assertEqual(alert.details['notes'][0]['text'], 'Called attending, will reassess in AM')

    def test_add_note_requires_text(self):
        alert = self.create_alert()
        self.auth_as(self.pharm_token)
        response = self.client.post(
            f'/api/v1/alerts/{alert.id}/add_note/',
            {'note': ''},
            format='json',
        )
        self.assertEqual(response.status_code, 400)

    def test_add_note_creates_audit(self):
        alert = self.create_alert()
        self.auth_as(self.ip_token)
        self.client.post(
            f'/api/v1/alerts/{alert.id}/add_note/',
            {'note': 'Test note'},
            format='json',
        )
        self.assertEqual(AlertAudit.objects.filter(alert=alert, action='note_added').count(), 1)


class AlertStatsTests(AlertAPITestBase):
    """GET /api/v1/alerts/stats/ tests."""

    def test_stats_returns_aggregates(self):
        self.create_alert(
            status=AlertStatus.PENDING, severity=AlertSeverity.CRITICAL, source_id='s1',
        )
        self.create_alert(
            status=AlertStatus.RESOLVED, severity=AlertSeverity.LOW, source_id='s2',
        )
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/stats/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['total'], 2)
        self.assertIn('by_status', response.data)
        self.assertIn('by_severity', response.data)

    def test_stats_respects_days_param(self):
        old = self.create_alert(source_id='s1')
        old.created_at = timezone.now() - timedelta(days=60)
        old.save(update_fields=['created_at'])
        self.create_alert(source_id='s2')
        self.auth_as(self.doc_token)
        response = self.client.get('/api/v1/alerts/stats/', {'days': 7})
        self.assertEqual(response.data['total'], 1)
