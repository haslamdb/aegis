"""
Core base models and mixins for AEGIS Django apps.

These models provide common functionality that all AEGIS apps can inherit.
"""

from django.db import models
from django.utils import timezone
import uuid


class TimeStampedModel(models.Model):
    """
    Abstract base class that adds created_at and updated_at fields.

    All AEGIS models should inherit from this to track when records
    were created and last modified.
    """
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this record was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this record was last updated"
    )

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """
    Abstract base class that uses UUID as primary key.

    Useful for models that need globally unique identifiers
    (alerts, assessments, etc.).
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False
    )

    class Meta:
        abstract = True


class SoftDeletableModel(models.Model):
    """
    Abstract base class that adds soft delete functionality.

    Records are marked as deleted but not actually removed from database.
    Important for HIPAA audit trails.
    """
    deleted_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this record was soft-deleted"
    )
    deleted_by = models.ForeignKey(
        'auth.User',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='%(class)s_deleted',
        help_text="User who soft-deleted this record"
    )

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False, hard_delete=False):
        """
        Soft delete by default. Set hard_delete=True to actually delete.
        """
        if hard_delete:
            return super().delete(using=using, keep_parents=keep_parents)
        else:
            self.deleted_at = timezone.now()
            self.save(update_fields=['deleted_at', 'deleted_by'])

    def restore(self):
        """Restore a soft-deleted record."""
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=['deleted_at', 'deleted_by'])

    @property
    def is_deleted(self):
        """Check if record is soft-deleted."""
        return self.deleted_at is not None


class PatientRelatedModel(models.Model):
    """
    Abstract base class for models related to patients.

    Provides common patient identification fields used across AEGIS.
    """
    patient_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="FHIR Patient resource ID"
    )
    patient_mrn = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Medical Record Number"
    )
    patient_name = models.CharField(
        max_length=255,
        help_text="Patient full name"
    )

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['patient_mrn']),
            models.Index(fields=['patient_id']),
        ]
