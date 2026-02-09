"""
Tests for Alerts models, enums, manager, and lifecycle methods.

Tests cover:
- Enum tests: AlertType, AlertStatus, AlertSeverity, ResolutionReason
- AlertManager queryset methods
- Alert lifecycle: acknowledge(), resolve(), snooze(), unsnooze()
- Alert properties: is_snoozed(), is_actionable(), is_expired(), recommendations
- AlertAudit creation and related_name
- __str__ methods
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.authentication.models import User, UserRole

from .models import (
    Alert, AlertAudit,
    AlertType, AlertStatus, AlertSeverity, ResolutionReason,
)


def _make_user(role=UserRole.ASP_PHARMACIST, username='alertuser'):
    return User.objects.create_user(
        username=username, email=f'{username}@test.com',
        password='pass', role=role,
    )


def _make_alert(**kwargs):
    defaults = {
        'alert_type': AlertType.CLABSI,
        'source_module': 'test',
        'source_id': 'test-1',
        'title': 'Test Alert',
        'summary': 'Test summary',
        'severity': AlertSeverity.MEDIUM,
        'patient_mrn': 'MRN-001',
    }
    defaults.update(kwargs)
    return Alert.objects.create(**defaults)


# =============================================================================
# Enum Tests
# =============================================================================


class AlertTypeEnumTests(TestCase):
    """Test AlertType choices."""

    def test_alert_type_count(self):
        """Verify total number of alert types."""
        self.assertGreaterEqual(len(AlertType.choices), 25)

    def test_hai_types(self):
        self.assertEqual(AlertType.CLABSI, 'clabsi')
        self.assertEqual(AlertType.SSI, 'ssi')
        self.assertEqual(AlertType.CAUTI, 'cauti')
        self.assertEqual(AlertType.VAE, 'vae')
        self.assertEqual(AlertType.CDI, 'cdi')

    def test_dosing_types(self):
        self.assertEqual(AlertType.DOSING_ALLERGY, 'dosing_allergy')
        self.assertEqual(AlertType.DOSING_RENAL, 'dosing_renal')

    def test_abx_indication_types(self):
        self.assertEqual(AlertType.ABX_NO_INDICATION, 'abx_no_indication')
        self.assertEqual(AlertType.ABX_NEVER_APPROPRIATE, 'abx_never_appropriate')
        self.assertEqual(AlertType.ABX_OFF_GUIDELINE, 'abx_off_guideline')

    def test_nhsn_type(self):
        self.assertEqual(AlertType.NHSN_SUBMISSION, 'nhsn_submission')


class AlertStatusEnumTests(TestCase):
    """Test AlertStatus choices."""

    def test_status_count(self):
        self.assertEqual(len(AlertStatus.choices), 7)

    def test_status_values(self):
        self.assertEqual(AlertStatus.PENDING, 'pending')
        self.assertEqual(AlertStatus.SENT, 'sent')
        self.assertEqual(AlertStatus.ACKNOWLEDGED, 'acknowledged')
        self.assertEqual(AlertStatus.IN_PROGRESS, 'in_progress')
        self.assertEqual(AlertStatus.SNOOZED, 'snoozed')
        self.assertEqual(AlertStatus.RESOLVED, 'resolved')
        self.assertEqual(AlertStatus.EXPIRED, 'expired')


class AlertSeverityEnumTests(TestCase):
    """Test AlertSeverity — uses HIGH not WARNING."""

    def test_severity_count(self):
        self.assertEqual(len(AlertSeverity.choices), 5)

    def test_severity_values(self):
        self.assertEqual(AlertSeverity.INFO, 'info')
        self.assertEqual(AlertSeverity.LOW, 'low')
        self.assertEqual(AlertSeverity.MEDIUM, 'medium')
        self.assertEqual(AlertSeverity.HIGH, 'high')
        self.assertEqual(AlertSeverity.CRITICAL, 'critical')

    def test_no_warning_severity(self):
        """Confirm HIGH is used, not WARNING."""
        values = [v for v, _ in AlertSeverity.choices]
        self.assertNotIn('warning', values)
        self.assertIn('high', values)


class ResolutionReasonEnumTests(TestCase):
    """Test ResolutionReason choices."""

    def test_resolution_reason_count(self):
        self.assertGreaterEqual(len(ResolutionReason.choices), 20)

    def test_common_reasons(self):
        self.assertEqual(ResolutionReason.ACCEPTED, 'accepted')
        self.assertEqual(ResolutionReason.FALSE_POSITIVE, 'false_positive')
        self.assertEqual(ResolutionReason.THERAPY_CHANGED, 'therapy_changed')
        self.assertEqual(ResolutionReason.AUTO_RESOLVED, 'auto_resolved')


# =============================================================================
# AlertManager Tests
# =============================================================================


class AlertManagerTests(TestCase):
    """Test AlertManager custom querysets."""

    def setUp(self):
        self.pending = _make_alert(source_id='m-1', status=AlertStatus.PENDING)
        self.ack = _make_alert(source_id='m-2', status=AlertStatus.ACKNOWLEDGED)
        self.resolved = _make_alert(source_id='m-3', status=AlertStatus.RESOLVED)
        self.expired = _make_alert(source_id='m-4', status=AlertStatus.EXPIRED)
        self.snoozed = _make_alert(
            source_id='m-5', status=AlertStatus.SNOOZED,
            snoozed_until=timezone.now() + timedelta(hours=1),
        )
        self.critical = _make_alert(
            source_id='m-6', severity=AlertSeverity.CRITICAL,
        )
        self.high = _make_alert(
            source_id='m-7', severity=AlertSeverity.HIGH,
        )

    def test_active_excludes_resolved_and_expired(self):
        active = Alert.objects.active()
        self.assertIn(self.pending, active)
        self.assertIn(self.ack, active)
        self.assertIn(self.snoozed, active)
        self.assertNotIn(self.resolved, active)
        self.assertNotIn(self.expired, active)

    def test_actionable_excludes_snoozed_with_future_time(self):
        actionable = Alert.objects.actionable()
        self.assertIn(self.pending, actionable)
        self.assertIn(self.ack, actionable)
        self.assertNotIn(self.snoozed, actionable)  # snoozed_until is in the future
        self.assertNotIn(self.resolved, actionable)

    def test_actionable_includes_expired_snooze(self):
        self.snoozed.snoozed_until = timezone.now() - timedelta(minutes=1)
        self.snoozed.save()
        actionable = Alert.objects.actionable()
        self.assertIn(self.snoozed, actionable)

    def test_by_type(self):
        specific = _make_alert(
            source_id='m-type', alert_type=AlertType.DRUG_BUG_MISMATCH,
        )
        results = Alert.objects.by_type(AlertType.DRUG_BUG_MISMATCH)
        self.assertIn(specific, results)
        self.assertNotIn(self.pending, results)

    def test_by_severity(self):
        results = Alert.objects.by_severity(AlertSeverity.CRITICAL)
        self.assertIn(self.critical, results)
        self.assertNotIn(self.pending, results)

    def test_by_patient(self):
        specific = _make_alert(source_id='m-pat', patient_mrn='MRN-999')
        results = Alert.objects.by_patient('MRN-999')
        self.assertIn(specific, results)
        self.assertNotIn(self.pending, results)

    def test_critical(self):
        results = Alert.objects.critical()
        self.assertIn(self.critical, results)
        self.assertNotIn(self.high, results)

    def test_high_priority(self):
        results = Alert.objects.high_priority()
        self.assertIn(self.critical, results)
        self.assertIn(self.high, results)
        self.assertNotIn(self.pending, results)  # pending has MEDIUM severity


# =============================================================================
# Alert Model Tests
# =============================================================================


class AlertModelTests(TestCase):
    """Test Alert model fields and __str__."""

    def test_default_status_is_pending(self):
        alert = _make_alert(source_id='d-1')
        self.assertEqual(alert.status, AlertStatus.PENDING)

    def test_default_severity_is_medium(self):
        alert = _make_alert(source_id='d-2')
        self.assertEqual(alert.severity, AlertSeverity.MEDIUM)

    def test_str(self):
        alert = _make_alert(source_id='d-str')
        s = str(alert)
        self.assertIn('CLABSI', s)
        self.assertIn('MRN-001', s)
        self.assertIn('Pending', s)

    def test_str_no_mrn(self):
        alert = _make_alert(source_id='d-nomrn', patient_mrn=None)
        s = str(alert)
        self.assertIn('No MRN', s)


# =============================================================================
# Alert Properties Tests
# =============================================================================


class AlertPropertiesTests(TestCase):
    """Test Alert computed properties."""

    def test_recommendations_from_details(self):
        alert = _make_alert(
            source_id='p-1',
            details={'recommendations': ['Switch to narrow spectrum']},
        )
        self.assertEqual(alert.recommendations, ['Switch to narrow spectrum'])

    def test_recommendations_none_when_missing(self):
        alert = _make_alert(source_id='p-2', details={})
        self.assertIsNone(alert.recommendations)

    def test_recommendations_none_when_details_empty(self):
        alert = _make_alert(source_id='p-3', details={})
        self.assertIsNone(alert.recommendations)

    def test_is_snoozed_true(self):
        alert = _make_alert(
            source_id='p-4', status=AlertStatus.SNOOZED,
            snoozed_until=timezone.now() + timedelta(hours=1),
        )
        self.assertTrue(alert.is_snoozed())

    def test_is_snoozed_false_expired(self):
        alert = _make_alert(
            source_id='p-5', status=AlertStatus.SNOOZED,
            snoozed_until=timezone.now() - timedelta(minutes=1),
        )
        self.assertFalse(alert.is_snoozed())

    def test_is_snoozed_false_wrong_status(self):
        alert = _make_alert(source_id='p-6', status=AlertStatus.PENDING)
        self.assertFalse(alert.is_snoozed())

    def test_is_actionable_pending(self):
        alert = _make_alert(source_id='p-7', status=AlertStatus.PENDING)
        self.assertTrue(alert.is_actionable())

    def test_is_actionable_false_resolved(self):
        alert = _make_alert(source_id='p-8', status=AlertStatus.RESOLVED)
        self.assertFalse(alert.is_actionable())

    def test_is_actionable_false_expired(self):
        alert = _make_alert(source_id='p-9', status=AlertStatus.EXPIRED)
        self.assertFalse(alert.is_actionable())

    def test_is_actionable_false_snoozed(self):
        alert = _make_alert(
            source_id='p-10', status=AlertStatus.SNOOZED,
            snoozed_until=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(alert.is_actionable())

    def test_is_expired_true(self):
        alert = _make_alert(
            source_id='p-11',
            expires_at=timezone.now() - timedelta(minutes=1),
        )
        self.assertTrue(alert.is_expired())

    def test_is_expired_false_future(self):
        alert = _make_alert(
            source_id='p-12',
            expires_at=timezone.now() + timedelta(hours=1),
        )
        self.assertFalse(alert.is_expired())

    def test_is_expired_false_no_expiry(self):
        alert = _make_alert(source_id='p-13')
        self.assertFalse(alert.is_expired())


# =============================================================================
# Alert Lifecycle Tests
# =============================================================================


class AlertLifecycleTests(TestCase):
    """Test acknowledge(), resolve(), snooze(), unsnooze()."""

    def setUp(self):
        self.user = _make_user()
        self.alert = _make_alert(source_id='lc-1')

    def test_acknowledge(self):
        self.alert.acknowledge(self.user, ip_address='10.0.0.1')
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.ACKNOWLEDGED)
        self.assertIsNotNone(self.alert.acknowledged_at)
        self.assertEqual(self.alert.acknowledged_by, self.user)

    def test_acknowledge_creates_audit(self):
        # post_save signal creates a CREATED entry on alert creation
        initial_count = self.alert.audit_log.count()
        self.alert.acknowledge(self.user)
        # acknowledge() calls save() (signal fires) + create_audit_entry()
        new_audits = self.alert.audit_log.exclude(action='CREATED').exclude(action='UPDATED').exclude(action='ACKNOWLEDGED')
        manual_audit = self.alert.audit_log.filter(action='acknowledged').first()
        self.assertIsNotNone(manual_audit)
        self.assertEqual(manual_audit.old_status, AlertStatus.PENDING)
        self.assertEqual(manual_audit.new_status, AlertStatus.ACKNOWLEDGED)
        self.assertEqual(manual_audit.performed_by, self.user)

    def test_resolve(self):
        self.alert.resolve(
            self.user, reason=ResolutionReason.THERAPY_CHANGED,
            notes='Changed to cefazolin', ip_address='10.0.0.2',
        )
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.RESOLVED)
        self.assertIsNotNone(self.alert.resolved_at)
        self.assertEqual(self.alert.resolved_by, self.user)
        self.assertEqual(self.alert.resolution_reason, ResolutionReason.THERAPY_CHANGED)
        self.assertEqual(self.alert.resolution_notes, 'Changed to cefazolin')

    def test_resolve_creates_audit(self):
        self.alert.resolve(self.user, reason=ResolutionReason.FALSE_POSITIVE)
        manual_audit = self.alert.audit_log.filter(action='resolved').first()
        self.assertIsNotNone(manual_audit)
        self.assertEqual(manual_audit.details['reason'], ResolutionReason.FALSE_POSITIVE)

    def test_snooze(self):
        until = timezone.now() + timedelta(hours=2)
        self.alert.snooze(self.user, until=until)
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.SNOOZED)
        self.assertEqual(self.alert.snoozed_until, until)
        self.assertEqual(self.alert.snoozed_by, self.user)

    def test_snooze_creates_audit(self):
        until = timezone.now() + timedelta(hours=2)
        self.alert.snooze(self.user, until=until)
        manual_audit = self.alert.audit_log.filter(action='snoozed').first()
        self.assertIsNotNone(manual_audit)
        self.assertIn('snoozed_until', manual_audit.details)

    def test_unsnooze(self):
        until = timezone.now() + timedelta(hours=2)
        self.alert.snooze(self.user, until=until)
        self.alert.unsnooze()
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.PENDING)
        self.assertIsNone(self.alert.snoozed_until)

    def test_unsnooze_noop_if_not_snoozed(self):
        self.alert.unsnooze()
        self.alert.refresh_from_db()
        self.assertEqual(self.alert.status, AlertStatus.PENDING)


# =============================================================================
# AlertAudit Tests
# =============================================================================


class AlertAuditTests(TestCase):
    """Test AlertAudit model and related_name."""

    def setUp(self):
        self.user = _make_user(username='audituser')
        self.alert = _make_alert(source_id='aud-1')

    def test_create_audit_entry(self):
        audit = self.alert.create_audit_entry(
            action='test_action',
            user=self.user,
            old_status='pending',
            new_status='acknowledged',
            ip_address='192.168.1.1',
            extra_details={'note': 'test'},
        )
        self.assertEqual(audit.alert, self.alert)
        self.assertEqual(audit.action, 'test_action')
        self.assertEqual(audit.performed_by, self.user)
        self.assertEqual(audit.old_status, 'pending')
        self.assertEqual(audit.new_status, 'acknowledged')
        self.assertEqual(audit.ip_address, '192.168.1.1')
        self.assertEqual(audit.details, {'note': 'test'})

    def test_related_name_is_audit_log(self):
        """Verify related_name is 'audit_log', not 'audit_entries'."""
        # Note: a CREATED audit entry is auto-generated by the post_save signal
        initial_count = self.alert.audit_log.count()
        self.alert.create_audit_entry(action='a1', user=self.user)
        self.alert.create_audit_entry(action='a2', user=self.user)
        self.assertEqual(self.alert.audit_log.count(), initial_count + 2)

    def test_audit_str(self):
        audit = self.alert.create_audit_entry(action='created', user=self.user)
        s = str(audit)
        self.assertIn('created', s)
        self.assertIn('audituser', s)

    def test_audit_str_no_user(self):
        audit = self.alert.create_audit_entry(action='auto_created')
        s = str(audit)
        self.assertIn('System', s)

    def test_audit_ordering(self):
        """Audit entries ordered by -performed_at (newest first)."""
        self.alert.create_audit_entry(action='first', user=self.user)
        self.alert.create_audit_entry(action='second', user=self.user)
        # Filter to only our manual entries (signal also creates CREATED)
        entries = list(self.alert.audit_log.filter(action__in=['first', 'second']))
        self.assertEqual(entries[0].action, 'second')
        self.assertEqual(entries[1].action, 'first')
