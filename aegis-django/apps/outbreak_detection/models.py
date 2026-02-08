"""
Django models for Outbreak Detection module.

Two custom models for clustering infection cases and detecting
potential outbreaks for IP investigation.
"""

from django.db import models
from django.utils import timezone

from apps.core.models import TimeStampedModel, UUIDModel


class ClusterStatus(models.TextChoices):
    """Status of an outbreak cluster."""
    ACTIVE = 'active', 'Active'
    INVESTIGATING = 'investigating', 'Under Investigation'
    RESOLVED = 'resolved', 'Resolved'


class ClusterSeverity(models.TextChoices):
    """Severity level of an outbreak cluster."""
    LOW = 'low', 'Low'
    MEDIUM = 'medium', 'Medium'
    HIGH = 'high', 'High'
    CRITICAL = 'critical', 'Critical'


class OutbreakCluster(UUIDModel, TimeStampedModel):
    """
    A potential outbreak cluster of related infection cases.

    Groups cases by infection type + unit + time window to
    detect potential outbreaks for IP investigation.
    """

    infection_type = models.CharField(
        max_length=50,
        db_index=True,
        help_text="Infection type (e.g., mrsa, vre, clabsi, cdi)",
    )
    organism = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="Primary organism if applicable",
    )
    unit = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Hospital unit where cases occurred",
    )
    case_count = models.IntegerField(
        default=0,
        help_text="Number of cases in this cluster",
    )
    first_case_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date of the first case in cluster",
    )
    last_case_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Date of the most recent case",
    )
    window_days = models.IntegerField(
        default=14,
        help_text="Time window in days for clustering",
    )

    # Status tracking
    status = models.CharField(
        max_length=20,
        choices=ClusterStatus.choices,
        default=ClusterStatus.ACTIVE,
        db_index=True,
    )
    severity = models.CharField(
        max_length=20,
        choices=ClusterSeverity.choices,
        default=ClusterSeverity.LOW,
    )

    # Resolution
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.CharField(max_length=255, blank=True, null=True)
    resolution_notes = models.TextField(blank=True, null=True)

    class Meta:
        db_table = 'outbreak_clusters'
        verbose_name = 'Outbreak Cluster'
        verbose_name_plural = 'Outbreak Clusters'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['infection_type', 'unit', 'status']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['severity', 'status']),
        ]

    def __str__(self):
        return (
            f"{self.infection_type.upper()} in {self.unit} "
            f"({self.case_count} cases, {self.get_status_display()})"
        )

    def add_case(self, case):
        """Update cluster stats after a case is added."""
        self.case_count = self.cases.count()
        if case.event_date:
            if self.first_case_date is None or case.event_date < self.first_case_date:
                self.first_case_date = case.event_date
            if self.last_case_date is None or case.event_date > self.last_case_date:
                self.last_case_date = case.event_date
        self.update_severity()
        self.save()

    def update_severity(self):
        """Update severity based on case count."""
        if self.case_count >= 5:
            self.severity = ClusterSeverity.CRITICAL
        elif self.case_count >= 4:
            self.severity = ClusterSeverity.HIGH
        elif self.case_count >= 3:
            self.severity = ClusterSeverity.MEDIUM
        else:
            self.severity = ClusterSeverity.LOW

    def resolve(self, resolved_by, notes=None):
        """Mark cluster as resolved."""
        self.status = ClusterStatus.RESOLVED
        self.resolved_at = timezone.now()
        self.resolved_by = resolved_by
        self.resolution_notes = notes
        self.save()


class ClusterCase(UUIDModel):
    """
    A case that is part of an outbreak cluster.

    Links to MDROCase or HAICandidate records via source + source_id.
    """

    cluster = models.ForeignKey(
        OutbreakCluster,
        on_delete=models.CASCADE,
        related_name='cases',
    )

    # Source tracking
    source = models.CharField(
        max_length=20,
        help_text="Data source: mdro, hai, or cdi",
    )
    source_id = models.CharField(
        max_length=255,
        help_text="ID in the source system (MDROCase or HAICandidate UUID)",
    )

    # Patient info (denormalized for display)
    patient_id = models.CharField(max_length=255)
    patient_mrn = models.CharField(max_length=100)
    event_date = models.DateTimeField()
    organism = models.CharField(max_length=255, blank=True, null=True)
    infection_type = models.CharField(max_length=50)
    unit = models.CharField(max_length=100)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'outbreak_cluster_cases'
        verbose_name = 'Cluster Case'
        verbose_name_plural = 'Cluster Cases'
        ordering = ['-event_date']
        constraints = [
            models.UniqueConstraint(
                fields=['source', 'source_id'],
                name='unique_outbreak_source_case',
            ),
        ]
        indexes = [
            models.Index(fields=['cluster', '-event_date']),
            models.Index(fields=['source', 'source_id']),
        ]

    def __str__(self):
        return f"{self.source}:{self.source_id} - {self.patient_mrn} ({self.infection_type})"
