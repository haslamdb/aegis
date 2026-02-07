"""
Custom model managers for AEGIS Django apps.

These managers provide reusable query methods across different models.
"""

from django.db import models
from django.utils import timezone


class SoftDeletableManager(models.Manager):
    """
    Manager that filters out soft-deleted records by default.

    Usage:
        class MyModel(SoftDeletableModel):
            objects = SoftDeletableManager()
            all_objects = models.Manager()  # Includes deleted
    """

    def get_queryset(self):
        """Return only non-deleted records."""
        return super().get_queryset().filter(deleted_at__isnull=True)

    def deleted(self):
        """Return only deleted records."""
        return super().get_queryset().filter(deleted_at__isnull=False)

    def with_deleted(self):
        """Return all records including deleted."""
        return super().get_queryset()


class ActiveManager(models.Manager):
    """
    Manager for models with is_active boolean field.

    Usage:
        class MyModel(models.Model):
            is_active = models.BooleanField(default=True)
            objects = ActiveManager()
    """

    def get_queryset(self):
        """Return only active records."""
        return super().get_queryset().filter(is_active=True)

    def inactive(self):
        """Return only inactive records."""
        return super().get_queryset().filter(is_active=False)


class TimeRangeQuerySet(models.QuerySet):
    """
    QuerySet mixin for filtering by time ranges.

    Provides convenient methods for date/time filtering.
    """

    def created_after(self, datetime):
        """Filter records created after specified datetime."""
        return self.filter(created_at__gte=datetime)

    def created_before(self, datetime):
        """Filter records created before specified datetime."""
        return self.filter(created_at__lte=datetime)

    def created_between(self, start, end):
        """Filter records created between two datetimes."""
        return self.filter(created_at__gte=start, created_at__lte=end)

    def created_today(self):
        """Filter records created today."""
        today = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.filter(created_at__gte=today)

    def created_this_week(self):
        """Filter records created this week."""
        now = timezone.now()
        week_start = now - timezone.timedelta(days=now.weekday())
        week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
        return self.filter(created_at__gte=week_start)

    def created_this_month(self):
        """Filter records created this month."""
        now = timezone.now()
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        return self.filter(created_at__gte=month_start)


class TimeRangeManager(models.Manager):
    """
    Manager that includes TimeRangeQuerySet methods.
    """

    def get_queryset(self):
        return TimeRangeQuerySet(self.model, using=self._db)

    def created_after(self, datetime):
        return self.get_queryset().created_after(datetime)

    def created_before(self, datetime):
        return self.get_queryset().created_before(datetime)

    def created_between(self, start, end):
        return self.get_queryset().created_between(start, end)

    def created_today(self):
        return self.get_queryset().created_today()

    def created_this_week(self):
        return self.get_queryset().created_this_week()

    def created_this_month(self):
        return self.get_queryset().created_this_month()
