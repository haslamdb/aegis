"""Tests for Notifications models."""

from django.test import TestCase
from django.utils import timezone

from apps.alerts.models import Alert, AlertType
from .models import NotificationLog, NotificationChannel, NotificationStatus


class NotificationLogCreationTests(TestCase):
    """Test NotificationLog model CRUD operations."""

    @classmethod
    def setUpTestData(cls):
        cls.alert = Alert.objects.create(
            alert_type=AlertType.CLABSI,
            source_module='hai_detection',
            source_id='notif-test-1',
            title='CLABSI Alert for notification',
            summary='Test notification',
        )

    def test_create_email_notification(self):
        notif = NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.EMAIL,
            recipient='doctor@cchmc.org',
        )
        self.assertEqual(notif.channel, NotificationChannel.EMAIL)
        self.assertEqual(notif.recipient, 'doctor@cchmc.org')
        self.assertEqual(notif.status, NotificationStatus.PENDING)
        self.assertIsNotNone(notif.id)

    def test_create_teams_notification(self):
        notif = NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.TEAMS,
            recipient='teams-channel-id-123',
            status=NotificationStatus.SENT,
            sent_at=timezone.now(),
        )
        self.assertEqual(notif.channel, NotificationChannel.TEAMS)
        self.assertEqual(notif.status, NotificationStatus.SENT)
        self.assertIsNotNone(notif.sent_at)

    def test_notification_without_alert(self):
        notif = NotificationLog.objects.create(
            alert=None,
            channel=NotificationChannel.SMS,
            recipient='+15135551234',
        )
        self.assertIsNone(notif.alert)

    def test_notification_failure(self):
        notif = NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.EMAIL,
            recipient='doctor@cchmc.org',
            status=NotificationStatus.FAILED,
            error_message='SMTP connection refused',
        )
        self.assertEqual(notif.status, NotificationStatus.FAILED)
        self.assertEqual(notif.error_message, 'SMTP connection refused')

    def test_notification_delivered(self):
        now = timezone.now()
        notif = NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.EMAIL,
            recipient='doctor@cchmc.org',
            status=NotificationStatus.DELIVERED,
            sent_at=now,
            delivered_at=now,
        )
        self.assertEqual(notif.status, NotificationStatus.DELIVERED)
        self.assertIsNotNone(notif.delivered_at)

    def test_notification_has_uuid_pk(self):
        notif = NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.EMAIL,
            recipient='test@test.com',
        )
        import uuid
        self.assertIsInstance(notif.id, uuid.UUID)

    def test_notification_ordering(self):
        n1 = NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.EMAIL,
            recipient='first@test.com',
        )
        n2 = NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.TEAMS,
            recipient='second@test.com',
        )
        notifications = list(NotificationLog.objects.all())
        self.assertEqual(notifications[0].pk, n2.pk)

    def test_alert_notifications_reverse_relation(self):
        NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.EMAIL,
            recipient='a@test.com',
        )
        NotificationLog.objects.create(
            alert=self.alert,
            channel=NotificationChannel.TEAMS,
            recipient='b@test.com',
        )
        self.assertEqual(self.alert.notifications.count(), 2)
