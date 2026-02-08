"""
MDRO Surveillance Models.

Tracks multi-drug resistant organism cases detected from culture data.
Replaces the SQLite-backed mdro_cases, mdro_reviews, and mdro_processing_log tables.
"""

from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from apps.core.models import TimeStampedModel, UUIDModel


class MDROTypeChoices(models.TextChoices):
    MRSA = 'mrsa', 'MRSA'
    VRE = 'vre', 'VRE'
    CRE = 'cre', 'CRE'
    ESBL = 'esbl', 'ESBL'
    CRPA = 'crpa', 'CRPA'
    CRAB = 'crab', 'CRAB'


class TransmissionStatusChoices(models.TextChoices):
    PENDING = 'pending', 'Pending'
    COMMUNITY = 'community', 'Community Onset'
    HEALTHCARE = 'healthcare', 'Healthcare Onset'


MDRO_TYPE_FULL_NAMES = {
    'mrsa': 'Methicillin-resistant Staph aureus',
    'vre': 'Vancomycin-resistant Enterococcus',
    'cre': 'Carbapenem-resistant Enterobacteriaceae',
    'esbl': 'Extended-spectrum Beta-lactamase',
    'crpa': 'Carbapenem-resistant Pseudomonas',
    'crab': 'Carbapenem-resistant Acinetobacter',
}


class MDROCaseManager(models.Manager):
    """Custom manager for MDROCase with common query methods."""

    def recent(self, days=30):
        """Cases from the last N days."""
        cutoff = timezone.now() - timedelta(days=days)
        return self.filter(culture_date__gte=cutoff)

    def by_type(self, mdro_type):
        """Filter by MDRO type."""
        return self.filter(mdro_type=mdro_type)

    def by_unit(self, unit):
        """Filter by unit."""
        return self.filter(unit=unit)

    def healthcare_onset(self):
        """Healthcare-onset cases only."""
        return self.filter(transmission_status=TransmissionStatusChoices.HEALTHCARE)

    def community_onset(self):
        """Community-onset cases only."""
        return self.filter(transmission_status=TransmissionStatusChoices.COMMUNITY)


class MDROCase(UUIDModel, TimeStampedModel):
    """
    Main MDRO case model.

    Represents a single MDRO detection from a culture result.
    Replaces the mdro_cases SQLite table.
    """
    # Patient information
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
        blank=True,
        default='',
        help_text="Patient full name"
    )

    # Culture information
    culture_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="FHIR DiagnosticReport ID (deduplication key)"
    )
    culture_date = models.DateTimeField(
        db_index=True,
        help_text="Date/time culture was collected"
    )
    specimen_type = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Specimen type (Blood, Urine, Respiratory, etc.)"
    )
    organism = models.CharField(
        max_length=255,
        help_text="Organism identified in culture"
    )

    # MDRO classification
    mdro_type = models.CharField(
        max_length=10,
        choices=MDROTypeChoices.choices,
        db_index=True,
        help_text="Type of MDRO"
    )
    resistant_antibiotics = models.JSONField(
        default=list,
        help_text="List of antibiotics the organism is resistant to"
    )
    susceptibilities = models.JSONField(
        default=list,
        help_text="Full susceptibility results [{antibiotic, result, mic}]"
    )
    classification_reason = models.TextField(
        blank=True,
        default='',
        help_text="Reason for MDRO classification"
    )

    # Location/timing
    location = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Facility name"
    )
    unit = models.CharField(
        max_length=100,
        blank=True,
        default='',
        db_index=True,
        help_text="Hospital unit"
    )
    admission_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Patient admission date"
    )
    days_since_admission = models.IntegerField(
        null=True,
        blank=True,
        help_text="Days between admission and culture collection"
    )

    # Transmission classification
    transmission_status = models.CharField(
        max_length=20,
        choices=TransmissionStatusChoices.choices,
        default=TransmissionStatusChoices.PENDING,
        db_index=True,
        help_text="Community vs healthcare onset"
    )

    # Status flags
    is_new = models.BooleanField(
        default=True,
        help_text="First isolation of this MDRO type for this patient"
    )
    prior_history = models.BooleanField(
        default=False,
        help_text="Patient has prior MDRO history"
    )

    # Review tracking
    reviewed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the case was reviewed"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviewed_mdro_cases',
        help_text="User who reviewed the case"
    )
    notes = models.TextField(
        blank=True,
        default='',
        help_text="Review notes"
    )

    objects = MDROCaseManager()

    class Meta:
        db_table = 'mdro_cases'
        verbose_name = 'MDRO Case'
        verbose_name_plural = 'MDRO Cases'
        ordering = ['-culture_date']
        indexes = [
            models.Index(fields=['patient_mrn', 'mdro_type']),
            models.Index(fields=['mdro_type', '-culture_date']),
            models.Index(fields=['unit', '-culture_date']),
            models.Index(fields=['transmission_status', '-culture_date']),
        ]

    def __str__(self):
        return f"{self.get_mdro_type_display()} - {self.patient_mrn} - {self.organism}"

    @property
    def mdro_type_full_name(self):
        return MDRO_TYPE_FULL_NAMES.get(self.mdro_type, self.mdro_type)

    def is_healthcare_onset(self):
        """Check if this is healthcare-onset (>48h after admission)."""
        if self.days_since_admission is not None:
            return self.days_since_admission > 2
        return False


class MDROReview(TimeStampedModel):
    """
    Review audit trail for MDRO cases.

    Tracks IP classification decisions and notes.
    """
    case = models.ForeignKey(
        MDROCase,
        on_delete=models.CASCADE,
        related_name='reviews',
        help_text="MDRO case being reviewed"
    )
    reviewer = models.CharField(
        max_length=255,
        help_text="Name of the reviewer"
    )
    decision = models.CharField(
        max_length=50,
        help_text="Review decision (confirmed, rejected, needs_info)"
    )
    notes = models.TextField(
        blank=True,
        default='',
        help_text="Review notes"
    )

    class Meta:
        db_table = 'mdro_reviews'
        verbose_name = 'MDRO Review'
        verbose_name_plural = 'MDRO Reviews'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.decision} by {self.reviewer} - {self.case.patient_mrn}"


class MDROProcessingLog(models.Model):
    """
    Deduplication tracking for culture processing.

    Records which cultures have been checked to avoid reprocessing.
    """
    culture_id = models.CharField(
        max_length=255,
        unique=True,
        help_text="FHIR DiagnosticReport ID"
    )
    processed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the culture was processed"
    )
    is_mdro = models.BooleanField(
        help_text="Whether the culture was classified as MDRO"
    )
    mdro_type = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        help_text="MDRO type if classified as MDRO"
    )
    case = models.ForeignKey(
        MDROCase,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='processing_logs',
        help_text="Created MDRO case (if applicable)"
    )

    class Meta:
        db_table = 'mdro_processing_log'
        verbose_name = 'MDRO Processing Log'
        verbose_name_plural = 'MDRO Processing Logs'
        ordering = ['-processed_at']

    def __str__(self):
        return f"{self.culture_id} - {'MDRO' if self.is_mdro else 'Not MDRO'}"
