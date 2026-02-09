"""Tests for Metrics models (ProviderActivity, DailySnapshot)."""

from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone

from apps.authentication.models import User, UserRole
from .models import ProviderActivity, DailySnapshot


class ProviderActivityCreationTests(TestCase):
    """Test ProviderActivity model CRUD operations."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username='metrics_pharm', email='metrics@test.com',
            password='testpass123', role=UserRole.ASP_PHARMACIST,
        )

    def test_create_activity(self):
        activity = ProviderActivity.objects.create(
            user=self.user, action_type='review_alert',
            module='hai_detection', patient_mrn='MRN-100',
            duration_seconds=90,
        )
        self.assertEqual(activity.action_type, 'review_alert')
        self.assertEqual(activity.module, 'hai_detection')
        self.assertEqual(activity.patient_mrn, 'MRN-100')
        self.assertEqual(activity.duration_seconds, 90)

    def test_activity_timestamps(self):
        activity = ProviderActivity.objects.create(
            user=self.user, action_type='resolve',
            module='dosing', duration_seconds=30,
        )
        self.assertIsNotNone(activity.created_at)
        self.assertIsNotNone(activity.updated_at)

    def test_activity_default_duration(self):
        activity = ProviderActivity.objects.create(
            user=self.user, action_type='view',
            module='outbreak',
        )
        self.assertEqual(activity.duration_seconds, 0)

    def test_activity_json_details(self):
        activity = ProviderActivity.objects.create(
            user=self.user, action_type='review',
            module='hai', details={'alert_id': 'abc-123', 'hai_type': 'clabsi'},
        )
        self.assertEqual(activity.details['alert_id'], 'abc-123')

    def test_activity_ordering(self):
        a1 = ProviderActivity.objects.create(
            user=self.user, action_type='first', module='hai',
        )
        a2 = ProviderActivity.objects.create(
            user=self.user, action_type='second', module='hai',
        )
        activities = list(ProviderActivity.objects.all())
        self.assertEqual(activities[0].pk, a2.pk)

    def test_activity_nullable_user(self):
        activity = ProviderActivity.objects.create(
            user=None, action_type='system', module='batch',
        )
        self.assertIsNone(activity.user)

    def test_activity_nullable_mrn(self):
        activity = ProviderActivity.objects.create(
            user=self.user, action_type='review', module='hai',
        )
        self.assertIsNone(activity.patient_mrn)


class DailySnapshotTests(TestCase):
    """Test DailySnapshot model CRUD operations."""

    def test_create_snapshot(self):
        snapshot = DailySnapshot.objects.create(
            date=date.today(),
            total_alerts=15,
            alerts_by_type={'clabsi': 5, 'cauti': 10},
            alerts_by_severity={'high': 3, 'medium': 12},
            total_actions=8,
            actions_by_module={'hai': 5, 'mdro': 3},
        )
        self.assertEqual(snapshot.total_alerts, 15)
        self.assertEqual(snapshot.alerts_by_type['clabsi'], 5)

    def test_snapshot_unique_date(self):
        DailySnapshot.objects.create(date=date.today(), total_alerts=5)
        with self.assertRaises(Exception):
            DailySnapshot.objects.create(date=date.today(), total_alerts=10)

    def test_snapshot_defaults(self):
        snapshot = DailySnapshot.objects.create(date=date.today())
        self.assertEqual(snapshot.total_alerts, 0)
        self.assertEqual(snapshot.total_actions, 0)
        self.assertEqual(snapshot.alerts_by_type, {})
        self.assertEqual(snapshot.alerts_by_severity, {})
        self.assertEqual(snapshot.actions_by_module, {})

    def test_snapshot_ordering(self):
        s1 = DailySnapshot.objects.create(
            date=date.today() - timedelta(days=1),
        )
        s2 = DailySnapshot.objects.create(date=date.today())
        snapshots = list(DailySnapshot.objects.all())
        self.assertEqual(snapshots[0].pk, s2.pk)

    def test_snapshot_timestamps(self):
        snapshot = DailySnapshot.objects.create(date=date.today())
        self.assertIsNotNone(snapshot.created_at)
        self.assertIsNotNone(snapshot.updated_at)
