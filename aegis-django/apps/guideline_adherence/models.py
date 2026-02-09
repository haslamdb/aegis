"""
Guideline Adherence models for AEGIS Django.

Tracks clinical guideline bundle compliance across 9 evidence-based bundles.
Replaces Flask SQLite dataclasses with Django ORM models.
"""

from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


# ============================================================================
# ENUMS
# ============================================================================

class EpisodeStatus(models.TextChoices):
    ACTIVE = 'active', 'Active'
    COMPLETE = 'complete', 'Complete'
    CLOSED = 'closed', 'Closed'


class ElementCheckStatus(models.TextChoices):
    MET = 'met', 'Met'
    NOT_MET = 'not_met', 'Not Met'
    PENDING = 'pending', 'Pending'
    NOT_APPLICABLE = 'na', 'Not Applicable'
    UNABLE_TO_ASSESS = 'unable', 'Unable to Assess'


class AdherenceLevel(models.TextChoices):
    FULL = 'full', 'Full Adherence'
    PARTIAL = 'partial', 'Partial Adherence'
    LOW = 'low', 'Low Adherence'
    NOT_APPLICABLE = 'na', 'Not Applicable'


class ReviewDecision(models.TextChoices):
    GUIDELINE_APPROPRIATE = 'guideline_appropriate', 'Guideline Appropriate'
    GUIDELINE_DEVIATION = 'guideline_deviation', 'Guideline Deviation'
    NEEDS_MORE_INFO = 'needs_more_info', 'Needs More Info'


# ============================================================================
# MODELS
# ============================================================================

class BundleEpisode(UUIDModel, TimeStampedModel):
    """
    Core episode tracking for guideline bundle monitoring.

    Represents a single instance of a patient triggering a guideline bundle,
    with tracking of all element results and adherence calculations.
    """

    # Patient identification
    patient_id = models.CharField(
        max_length=255,
        db_index=True,
        help_text="FHIR Patient resource ID",
    )
    patient_mrn = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Medical Record Number",
    )
    patient_name = models.CharField(
        max_length=255,
        blank=True,
        default='',
        help_text="Patient name (display only)",
    )
    encounter_id = models.CharField(
        max_length=255,
        help_text="FHIR Encounter resource ID",
    )

    # Bundle identification
    bundle_id = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Bundle identifier (e.g., sepsis_peds_2024)",
    )
    bundle_name = models.CharField(
        max_length=255,
        help_text="Human-readable bundle name",
    )

    # Trigger information
    trigger_type = models.CharField(
        max_length=50,
        help_text="What triggered this episode (diagnosis, order, lab)",
    )
    trigger_code = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="ICD-10, LOINC, or CPT code that triggered",
    )
    trigger_description = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Description of trigger event",
    )
    trigger_time = models.DateTimeField(
        help_text="When the bundle was triggered",
    )

    # Patient context
    patient_age_days = models.IntegerField(
        null=True,
        blank=True,
        help_text="Patient age in days at trigger time",
    )
    patient_age_months = models.FloatField(
        null=True,
        blank=True,
        help_text="Patient age in months at trigger time",
    )
    patient_unit = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Hospital unit at trigger time",
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=EpisodeStatus.choices,
        default=EpisodeStatus.ACTIVE,
        db_index=True,
        help_text="Current episode status",
    )

    # Adherence tracking
    adherence_percentage = models.FloatField(
        default=0,
        help_text="Percentage of applicable elements met (0-100)",
    )
    adherence_level = models.CharField(
        max_length=20,
        choices=AdherenceLevel.choices,
        default=AdherenceLevel.NOT_APPLICABLE,
        help_text="Adherence level classification",
    )
    elements_total = models.IntegerField(default=0)
    elements_applicable = models.IntegerField(default=0)
    elements_met = models.IntegerField(default=0)
    elements_not_met = models.IntegerField(default=0)
    elements_pending = models.IntegerField(default=0)

    # Review workflow
    review_status = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="pending_review / reviewed / not_applicable",
    )
    overall_determination = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Final determination from review",
    )

    # Clinical context (LLM assessment data)
    clinical_context = models.JSONField(
        default=dict,
        help_text="NLP assessment data (appearance, evidence)",
    )

    # Timestamps
    last_assessment_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When last LLM assessment was run",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When episode was completed/closed",
    )

    class Meta:
        db_table = 'guideline_episodes'
        verbose_name = 'Bundle Episode'
        verbose_name_plural = 'Bundle Episodes'
        ordering = ['-created_at']
        unique_together = ['patient_id', 'encounter_id', 'bundle_id', 'trigger_time']
        indexes = [
            models.Index(fields=['bundle_id', 'status']),
            models.Index(fields=['patient_mrn', 'status']),
            models.Index(fields=['status', '-created_at']),
        ]

    def __str__(self):
        return f"{self.bundle_name} - {self.patient_mrn} ({self.get_status_display()})"

    def calculate_adherence(self):
        """Recalculate adherence from element results."""
        results = self.element_results.all()
        self.elements_total = results.count()
        applicable = results.exclude(status=ElementCheckStatus.NOT_APPLICABLE)
        self.elements_applicable = applicable.count()
        self.elements_met = applicable.filter(status=ElementCheckStatus.MET).count()
        self.elements_not_met = applicable.filter(status=ElementCheckStatus.NOT_MET).count()
        self.elements_pending = applicable.filter(
            status__in=[ElementCheckStatus.PENDING, ElementCheckStatus.UNABLE_TO_ASSESS]
        ).count()

        if self.elements_applicable > 0:
            self.adherence_percentage = round(
                (self.elements_met / self.elements_applicable) * 100, 1
            )
        else:
            self.adherence_percentage = 0

        # Classify adherence level
        if self.elements_applicable == 0:
            self.adherence_level = AdherenceLevel.NOT_APPLICABLE
        elif self.adherence_percentage == 100:
            self.adherence_level = AdherenceLevel.FULL
        elif self.adherence_percentage > 50:
            self.adherence_level = AdherenceLevel.PARTIAL
        else:
            self.adherence_level = AdherenceLevel.LOW

        self.save(update_fields=[
            'elements_total', 'elements_applicable', 'elements_met',
            'elements_not_met', 'elements_pending',
            'adherence_percentage', 'adherence_level', 'updated_at',
        ])


class ElementResult(TimeStampedModel):
    """
    Per-element status within a bundle episode.

    Tracks whether each required bundle element has been completed
    within the required time window.
    """

    episode = models.ForeignKey(
        BundleEpisode,
        on_delete=models.CASCADE,
        related_name='element_results',
    )
    element_id = models.CharField(
        max_length=100,
        help_text="Element identifier (e.g., sepsis_blood_cx)",
    )
    element_name = models.CharField(
        max_length=255,
        help_text="Human-readable element name",
    )
    element_description = models.CharField(
        max_length=500,
        blank=True,
        default='',
        help_text="Description of the element requirement",
    )

    # Status
    status = models.CharField(
        max_length=20,
        choices=ElementCheckStatus.choices,
        default=ElementCheckStatus.PENDING,
        help_text="Current check status",
    )
    required = models.BooleanField(
        default=True,
        help_text="Whether this element is required for this patient",
    )

    # Results
    value = models.TextField(
        blank=True,
        default='',
        help_text="What was found (lab value, medication name, etc.)",
    )
    notes = models.TextField(
        blank=True,
        default='',
        help_text="Notes about the check result",
    )

    # Timing
    deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this element must be completed by",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the element was completed",
    )
    time_window_hours = models.FloatField(
        null=True,
        blank=True,
        help_text="Time window in hours from trigger",
    )

    class Meta:
        db_table = 'guideline_element_results'
        verbose_name = 'Element Result'
        verbose_name_plural = 'Element Results'
        ordering = ['element_id']
        unique_together = ['episode', 'element_id']

    def __str__(self):
        return f"{self.element_name}: {self.get_status_display()}"

    @property
    def is_overdue(self):
        """Check if element is past its deadline."""
        from django.utils import timezone
        if not self.deadline:
            return False
        return (
            self.status == ElementCheckStatus.PENDING
            and timezone.now() > self.deadline
        )


class EpisodeAssessment(TimeStampedModel):
    """
    LLM clinical analysis results for an episode.

    Stores extraction results from tiered NLP (7B triage -> 70B full).
    """

    episode = models.ForeignKey(
        BundleEpisode,
        on_delete=models.CASCADE,
        related_name='assessments',
    )
    assessment_type = models.CharField(
        max_length=100,
        help_text="Type of assessment (clinical_impression, gi_symptoms)",
    )
    primary_determination = models.CharField(
        max_length=50,
        help_text="guideline_appropriate / guideline_deviation / pending",
    )
    confidence = models.CharField(
        max_length=20,
        help_text="high / medium / low",
    )
    reasoning = models.TextField(
        blank=True,
        default='',
        help_text="LLM reasoning for determination",
    )
    supporting_evidence = models.JSONField(
        default=list,
        help_text="List of evidence items",
    )
    extraction_data = models.JSONField(
        default=dict,
        help_text="Raw extraction data (concerning_signs, reassuring_signs, appearance)",
    )
    model_used = models.CharField(
        max_length=100,
        help_text="LLM model identifier",
    )
    response_time_ms = models.IntegerField(
        null=True,
        blank=True,
        help_text="LLM response time in milliseconds",
    )

    class Meta:
        db_table = 'guideline_assessments'
        verbose_name = 'Episode Assessment'
        verbose_name_plural = 'Episode Assessments'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.assessment_type}: {self.primary_determination} ({self.confidence})"


class EpisodeReview(TimeStampedModel):
    """
    Human review with override tracking for an episode.

    Allows pharmacists/physicians to confirm or override LLM determinations.
    """

    episode = models.ForeignKey(
        BundleEpisode,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    assessment = models.ForeignKey(
        EpisodeAssessment,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='reviews',
        help_text="Assessment being reviewed",
    )

    # Reviewer
    reviewer = models.CharField(
        max_length=255,
        help_text="Reviewer name/username",
    )

    # Decision
    reviewer_decision = models.CharField(
        max_length=50,
        choices=ReviewDecision.choices,
        help_text="Reviewer's determination",
    )
    llm_decision = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="What the LLM determined (for comparison)",
    )

    # Override tracking
    is_override = models.BooleanField(
        default=False,
        help_text="Whether reviewer overrode the LLM determination",
    )
    override_reason_category = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="Category: extraction_error / element_detection_error / clinical_judgment / etc.",
    )

    # Deviation details
    deviation_type = models.CharField(
        max_length=100,
        blank=True,
        default='',
        help_text="documentation / timing / missing_element / clinical_judgment",
    )

    # Corrections
    extraction_corrections = models.JSONField(
        default=dict,
        help_text="Corrections to LLM extraction",
    )

    # Notes
    notes = models.TextField(
        blank=True,
        default='',
        help_text="Reviewer notes",
    )

    # Timestamp
    reviewed_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When the review was submitted",
    )

    class Meta:
        db_table = 'guideline_reviews'
        verbose_name = 'Episode Review'
        verbose_name_plural = 'Episode Reviews'
        ordering = ['-reviewed_at']

    def __str__(self):
        return f"Review by {self.reviewer}: {self.get_reviewer_decision_display()}"


class MonitorState(TimeStampedModel):
    """
    Polling checkpoints for the three monitoring modes.

    Tracks last poll time for trigger/episode/adherence monitors
    to enable incremental processing.
    """

    monitor_type = models.CharField(
        max_length=50,
        unique=True,
        help_text="Monitor type: trigger / episode / adherence",
    )
    last_poll_time = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this monitor last polled",
    )
    last_run_status = models.CharField(
        max_length=50,
        blank=True,
        default='',
        help_text="success / error",
    )
    state_data = models.JSONField(
        default=dict,
        help_text="Extra checkpoint data",
    )

    class Meta:
        db_table = 'guideline_monitor_state'
        verbose_name = 'Monitor State'
        verbose_name_plural = 'Monitor States'

    def __str__(self):
        return f"{self.monitor_type}: {self.last_poll_time}"
