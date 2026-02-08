"""
Django models for HAI Detection module.

Four custom models for the multi-stage HAI detection pipeline:
1. HAICandidate - Rule-based screening results
2. HAIClassification - LLM classification records
3. HAIReview - IP review decisions with override tracking
4. LLMAuditLog - LLM call audit trail
"""

from django.db import models

from apps.core.models import TimeStampedModel, UUIDModel


class HAIType(models.TextChoices):
    """Healthcare-Associated Infection types tracked by NHSN."""
    CLABSI = 'clabsi', 'Central Line-Associated BSI'
    SSI = 'ssi', 'Surgical Site Infection'
    CAUTI = 'cauti', 'Catheter-Associated UTI'
    VAE = 'vae', 'Ventilator-Associated Event'
    CDI = 'cdi', 'C. difficile Infection'


class CandidateStatus(models.TextChoices):
    """Workflow status for HAI candidates."""
    PENDING = 'pending', 'Pending Classification'
    CLASSIFIED = 'classified', 'Classified by LLM'
    PENDING_REVIEW = 'pending_review', 'Pending IP Review'
    CONFIRMED = 'confirmed', 'Confirmed HAI'
    REJECTED = 'rejected', 'Not HAI'
    EXCLUDED = 'excluded', 'Excluded (Failed Criteria)'


class ClassificationDecision(models.TextChoices):
    """LLM classification decisions."""
    HAI_CONFIRMED = 'hai_confirmed', 'HAI Confirmed'
    NOT_HAI = 'not_hai', 'Not HAI'
    PENDING_REVIEW = 'pending_review', 'Needs IP Review'


class ReviewQueueType(models.TextChoices):
    """Types of review queues."""
    IP_REVIEW = 'ip_review', 'IP Review'
    MANUAL_REVIEW = 'manual_review', 'Manual Review'


class ReviewerDecision(models.TextChoices):
    """IP reviewer decisions."""
    CONFIRMED = 'confirmed', 'Confirmed HAI'
    REJECTED = 'rejected', 'Not HAI'
    NEEDS_MORE_INFO = 'needs_more_info', 'Needs More Information'


class OverrideReasonCategory(models.TextChoices):
    """Structured override reason categories for LLM training feedback."""
    EXTRACTION_ERROR = 'extraction_error', 'Extraction Error'
    RULES_ERROR = 'rules_error', 'Rules Engine Error'
    CLINICAL_JUDGMENT = 'clinical_judgment', 'Clinical Judgment'
    MISSING_DOCUMENTATION = 'missing_documentation', 'Missing Documentation'
    NHSN_INTERPRETATION = 'nhsn_interpretation', 'NHSN Interpretation Difference'
    OTHER = 'other', 'Other'


class HAICandidate(UUIDModel, TimeStampedModel):
    """
    An HAI candidate identified by rule-based screening.

    Replaces SQLite hai_candidates + type-specific tables.
    Type-specific data (SSI procedure info, VAE vent params, etc.)
    stored in type_specific_data JSONField.
    """

    hai_type = models.CharField(
        max_length=10,
        choices=HAIType.choices,
        db_index=True,
    )

    # Patient information
    patient_id = models.CharField(max_length=255, db_index=True)
    patient_mrn = models.CharField(max_length=100, db_index=True)
    patient_name = models.CharField(max_length=255, blank=True, default='')
    patient_location = models.CharField(max_length=255, blank=True, default='')

    # Culture information
    culture_id = models.CharField(max_length=255)
    culture_date = models.DateTimeField()
    organism = models.CharField(max_length=500, blank=True, default='')

    # Device/catheter information
    device_info = models.JSONField(null=True, blank=True)
    device_days_at_culture = models.IntegerField(null=True, blank=True)

    # Screening criteria
    meets_initial_criteria = models.BooleanField(default=True)
    exclusion_reason = models.TextField(blank=True, default='')

    # Workflow status
    status = models.CharField(
        max_length=20,
        choices=CandidateStatus.choices,
        default=CandidateStatus.PENDING,
        db_index=True,
    )

    # Type-specific data (SSI procedure, VAE vent params, CAUTI catheter, CDI timing)
    type_specific_data = models.JSONField(default=dict, blank=True)

    # NHSN reporting
    nhsn_reported = models.BooleanField(default=False)
    nhsn_reported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'hai_candidates'
        verbose_name = 'HAI Candidate'
        verbose_name_plural = 'HAI Candidates'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['hai_type', 'culture_id'],
                name='unique_hai_type_culture',
            ),
        ]
        indexes = [
            models.Index(fields=['hai_type', 'status']),
            models.Index(fields=['patient_mrn', '-created_at']),
            models.Index(fields=['status', '-created_at']),
            models.Index(fields=['culture_date']),
        ]

    def __str__(self):
        return f"{self.get_hai_type_display()} - {self.patient_mrn} - {self.get_status_display()}"

    @property
    def latest_classification(self):
        """Get the most recent classification for this candidate."""
        return self.classifications.order_by('-created_at').first()

    @property
    def latest_review(self):
        """Get the most recent review for this candidate."""
        return self.reviews.order_by('-created_at').first()

    @property
    def pending_review(self):
        """Get the pending (unreviewed) review if any."""
        return self.reviews.filter(reviewed=False).first()


class HAIClassification(UUIDModel):
    """
    LLM classification result for an HAI candidate.

    Stores the decision, confidence, evidence, and extraction data
    from the two-stage pipeline (extraction + rules engine).
    """

    candidate = models.ForeignKey(
        HAICandidate,
        on_delete=models.CASCADE,
        related_name='classifications',
    )

    # Classification result
    decision = models.CharField(
        max_length=20,
        choices=ClassificationDecision.choices,
    )
    confidence = models.FloatField()
    alternative_source = models.CharField(max_length=500, blank=True, default='')
    is_mbi_lcbi = models.BooleanField(default=False)

    # Evidence
    supporting_evidence = models.JSONField(default=list, blank=True)
    contradicting_evidence = models.JSONField(default=list, blank=True)
    reasoning = models.TextField(blank=True, default='')

    # LLM metadata
    model_used = models.CharField(max_length=200)
    prompt_version = models.CharField(max_length=50)
    tokens_used = models.IntegerField(default=0)
    processing_time_ms = models.IntegerField(default=0)

    # Extraction + rules data (for IP review)
    extraction_data = models.JSONField(null=True, blank=True)
    rules_result = models.JSONField(null=True, blank=True)
    strictness_level = models.CharField(max_length=50, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hai_classifications'
        verbose_name = 'HAI Classification'
        verbose_name_plural = 'HAI Classifications'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['candidate', '-created_at']),
            models.Index(fields=['decision']),
        ]

    def __str__(self):
        return f"{self.get_decision_display()} ({self.confidence:.0%}) - {self.candidate_id}"


class HAIReview(UUIDModel):
    """
    IP review of an HAI candidate with override tracking.

    Tracks whether the IP agreed with the LLM decision, and if not,
    captures structured reasons for LLM training feedback.
    """

    candidate = models.ForeignKey(
        HAICandidate,
        on_delete=models.CASCADE,
        related_name='reviews',
    )
    classification = models.ForeignKey(
        HAIClassification,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviews',
    )

    # Review queue
    queue_type = models.CharField(
        max_length=20,
        choices=ReviewQueueType.choices,
        default=ReviewQueueType.IP_REVIEW,
    )

    # Review status
    reviewed = models.BooleanField(default=False)
    reviewer = models.CharField(max_length=255, blank=True, default='')
    reviewer_decision = models.CharField(
        max_length=20,
        choices=ReviewerDecision.choices,
        blank=True,
        default='',
    )
    reviewer_notes = models.TextField(blank=True, default='')

    # Override tracking
    llm_decision = models.CharField(max_length=20, blank=True, default='')
    is_override = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True, default='')
    override_reason_category = models.CharField(
        max_length=30,
        choices=OverrideReasonCategory.choices,
        blank=True,
        default='',
    )
    extraction_corrections = models.JSONField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'hai_reviews'
        verbose_name = 'HAI Review'
        verbose_name_plural = 'HAI Reviews'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['candidate', '-created_at']),
            models.Index(fields=['reviewed', '-created_at']),
            models.Index(fields=['is_override']),
            models.Index(fields=['queue_type', 'reviewed']),
        ]

    def __str__(self):
        status = 'Reviewed' if self.reviewed else 'Pending'
        return f"{status} review for {self.candidate_id}"


class LLMAuditLog(models.Model):
    """
    Audit log for LLM API calls during HAI classification.

    Tracks model usage, token counts, response times, and errors
    for monitoring and cost analysis.
    """

    candidate = models.ForeignKey(
        HAICandidate,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='llm_calls',
    )

    model = models.CharField(max_length=200)
    success = models.BooleanField()
    input_tokens = models.IntegerField(default=0)
    output_tokens = models.IntegerField(default=0)
    response_time_ms = models.IntegerField(default=0)
    error_message = models.TextField(blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hai_llm_audit'
        verbose_name = 'LLM Audit Log Entry'
        verbose_name_plural = 'LLM Audit Log Entries'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['candidate', '-created_at']),
            models.Index(fields=['model']),
        ]

    def __str__(self):
        status = 'OK' if self.success else 'ERROR'
        return f"{self.model} [{status}] {self.input_tokens}+{self.output_tokens} tokens"
